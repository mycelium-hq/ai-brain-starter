#!/usr/bin/env python3
"""
rename-contacts.py  (macOS only)

After sync.mjs runs, files for unsaved numbers land as +1234567890.md.
This script cross-references macOS Contacts to rename them to real names
and updates the frontmatter + message sender lines inside each file.

Requirements:
  - macOS
  - Terminal must have Contacts permission:
    System Settings › Privacy & Security › Contacts › Terminal (enable)

Usage:
  VAULT_ROOT=/path/to/vault python3 rename-contacts.py
  python3 rename-contacts.py --vault /path/to/vault
  python3 rename-contacts.py --vault /path/to/vault --output "Notes/WhatsApp"
"""

from __future__ import annotations

import os
import re
import sys
import subprocess
import tempfile
import argparse
from pathlib import Path

# ── Args ──────────────────────────────────────────────────────────────────────

parser = argparse.ArgumentParser()
parser.add_argument("--vault",  default=os.environ.get("VAULT_ROOT", ""),
                    help="Vault root path (or set VAULT_ROOT env var)")
parser.add_argument("--output", default="🤖 AI Chats/WhatsApp",
                    help="Subfolder within vault (default: 🤖 AI Chats/WhatsApp)")
args = parser.parse_args()

if not args.vault:
    # Auto-detect: walk up 2 levels from this script (scripts/whatsapp/ → scripts/ → vault)
    script_dir  = Path(__file__).resolve().parent
    args.vault  = str(script_dir.parent.parent)
    print(f"Auto-detected vault root: {args.vault}")

WA_DIR = Path(args.vault) / args.output
if not WA_DIR.exists():
    print(f"Error: {WA_DIR} not found. Run sync.mjs first.")
    sys.exit(1)

# ── Export contacts from macOS Contacts via Swift ─────────────────────────────

SWIFT = """
import Contacts
import Foundation

let store = CNContactStore()

func emit() {
    let keys = [CNContactGivenNameKey, CNContactFamilyNameKey,
                CNContactOrganizationNameKey, CNContactPhoneNumbersKey] as [CNKeyDescriptor]
    var out = ""
    do {
        let req = CNContactFetchRequest(keysToFetch: keys)
        try store.enumerateContacts(with: req) { c, _ in
            var name = "\\(c.givenName) \\(c.familyName)".trimmingCharacters(in: .whitespaces)
            if name.isEmpty { name = c.organizationName }
            if name.isEmpty { return }
            for ph in c.phoneNumbers { out += "\\(name)\\t\\(ph.value.stringValue)\\n" }
        }
    } catch {
        fputs("Error: \\(error)\\n", stderr)
        exit(1)
    }
    print(out, terminator: "")
}

// A plain `swift` script has no app bundle / NSContactsUsageDescription of its own,
// so macOS TCC attributes Contacts access to the responsible parent (your terminal).
// requestAccess therefore shows the one-click "allow Contacts for <terminal>" prompt
// on first run; a Developer-ID-signed helper would prompt as itself. A denied or
// restricted state can't be re-prompted, so exit 2 and let the caller explain the
// manual grant. Exit 2 = access unavailable, distinct from exit 1 = a real fetch error.
let status = CNContactStore.authorizationStatus(for: .contacts)
switch status {
case .authorized:
    emit()
case .notDetermined:
    let sema = DispatchSemaphore(value: 0)
    var granted = false
    store.requestAccess(for: .contacts) { ok, _ in granted = ok; sema.signal() }
    if sema.wait(timeout: .now() + 120) == .timedOut {
        fputs("CONTACTS_ACCESS_UNAVAILABLE status=prompt-timeout\\n", stderr)
        exit(2)
    }
    if granted {
        emit()
    } else {
        fputs("CONTACTS_ACCESS_UNAVAILABLE status=denied\\n", stderr)
        exit(2)
    }
default:
    fputs("CONTACTS_ACCESS_UNAVAILABLE status=\\(status.rawValue)\\n", stderr)
    exit(2)
}
"""

print("Reading macOS Contacts...")
with tempfile.NamedTemporaryFile(suffix=".swift", mode="w", delete=False) as f:
    f.write(SWIFT)
    swift_path = f.name

result = subprocess.run(["swift", swift_path], capture_output=True, text=True)
os.unlink(swift_path)

if result.returncode == 2 or "CONTACTS_ACCESS_UNAVAILABLE" in result.stderr:
    print("\nCould not read Contacts: access was not granted.")
    print("On the first run macOS shows a prompt to allow Contacts for your terminal")
    print("app -- click Allow. If it was denied, or your Mac restricts it:")
    print("  1. Open System Settings > Privacy & Security > Contacts")
    print("  2. Enable access for the terminal app you ran this from (Terminal, iTerm, ...)")
    print("  3. Re-run this script.")
    print("(This step only maps phone numbers to names; skipping it keeps the")
    print("phone-number filenames and does not affect the rest of the export.)")
    sys.exit(1)

if result.returncode != 0:
    print(f"\nCould not read Contacts: {result.stderr.strip()}")
    sys.exit(1)

# ── Phone → name lookup ───────────────────────────────────────────────────────

def normalize(phone: str) -> str:
    return re.sub(r"\D", "", phone)

phone_map: dict[str, str] = {}
for line in result.stdout.splitlines():
    if "\t" not in line:
        continue
    name, phone = line.split("\t", 1)
    d = normalize(phone)
    if len(d) < 7:
        continue
    phone_map[d] = name
    if d.startswith("1") and len(d) == 11:
        phone_map[d[1:]] = name          # US: without country code
    if d.startswith("57") and len(d) == 12:
        phone_map[d[2:]] = name          # Colombia: without country code

print(f"Loaded {len(phone_map):,} phone entries")

def lookup(digits: str) -> str | None:
    return (phone_map.get(digits)
         or phone_map.get(digits[1:]  if digits.startswith("1")  else "")
         or phone_map.get("1" + digits)
         or phone_map.get(digits[2:]  if digits.startswith("57") else "")
         or phone_map.get("57" + digits))

# ── Rename and update files ───────────────────────────────────────────────────

def sanitize(name: str) -> str:
    return re.sub(r'[/\\?%*:|"<>\[\]]', "-", name).strip()

matched, unmatched = 0, 0

for filepath in sorted(WA_DIR.glob("+*.md")):
    digits = normalize(filepath.stem)
    name   = lookup(digits)

    if not name:
        unmatched += 1
        continue

    new_stem = sanitize(name)
    dst      = WA_DIR / (new_stem + ".md")

    if dst.exists() and dst != filepath:
        dst = WA_DIR / f"{new_stem} ({digits[-4:]}).md"

    filepath.rename(dst)

    content = dst.read_text(encoding="utf-8")
    content = re.sub(r'^contact: "?\+?\d+"?',   f'contact: "{name}"',     content, flags=re.MULTILINE)
    content = re.sub(r'^# WhatsApp: \+\d+',      f'# WhatsApp: {name}',   content, flags=re.MULTILINE)
    content = re.sub(r'(\*\*\d+:\d+ [AP]M\*\* )\+\d+:', rf'\g<1>{name}:', content)
    dst.write_text(content, encoding="utf-8")

    matched += 1

total = matched + unmatched
print(f"\nRenamed:     {matched} / {total}")
print(f"Unmatched:   {unmatched}  (not in Contacts — international or unsaved numbers)")
