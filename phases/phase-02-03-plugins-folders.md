## Phase 2: Install Obsidian Plugins

**AUTO-INSTALL FIRST. Don't make the user click through Obsidian's plugin browser unless the auto-install fails.** Non-technical users miss-click in the plugin UI, install the wrong plugin, or skip the "Enable" step after "Install" — these are the top three Phase 2 support requests.

Tell the user: *"I'm going to install your Obsidian plugins in the background. These power live queries, templates, task tracking, a journal calendar, AI-powered note linking, and graph visualization. Give me a few seconds."*

Then run this Python helper, substituting `[VAULT_PATH]` with the actual vault path saved in Phase 1 step 8:

```bash
python3 - <<'PY'
import json, os, sys, urllib.request, zipfile, io, shutil
from pathlib import Path

VAULT = Path("[VAULT_PATH]")
OBSIDIAN_DIR = VAULT / ".obsidian"
PLUGINS_DIR = OBSIDIAN_DIR / "plugins"
PLUGINS_DIR.mkdir(parents=True, exist_ok=True)

# Plugin id → GitHub repo (owner/repo). The release ZIP for each contains
# main.js, manifest.json, and (sometimes) styles.css — Obsidian's plugin format.
PLUGINS = {
    "dataview":  "blacksmithgu/obsidian-dataview",
    "templater-obsidian": "SilentVoid13/Templater",
    "obsidian-tasks-plugin": "obsidian-tasks-group/obsidian-tasks",
    "calendar": "liamcain/obsidian-calendar-plugin",
    "smart-connections": "brianpetro/obsidian-smart-connections",
    "obsidian-local-rest-api": "coddingtonbear/obsidian-local-rest-api",
    "juggl": "HEmile/juggl",
    "custom-sort": "SebastianMC/obsidian-custom-sort",
}

def fetch_latest_release(repo):
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)

def install_plugin(plugin_id, repo):
    target = PLUGINS_DIR / plugin_id
    if (target / "main.js").exists() and (target / "manifest.json").exists():
        print(f"  = {plugin_id} already installed")
        return True
    try:
        rel = fetch_latest_release(repo)
        # Most plugins ship a ZIP asset; some ship loose main.js + manifest.json.
        zip_asset = next((a for a in rel.get("assets", []) if a["name"].endswith(".zip")), None)
        target.mkdir(parents=True, exist_ok=True)
        if zip_asset:
            with urllib.request.urlopen(zip_asset["browser_download_url"], timeout=60) as r:
                buf = io.BytesIO(r.read())
            with zipfile.ZipFile(buf) as z:
                for name in z.namelist():
                    if name.endswith(("main.js", "manifest.json", "styles.css")):
                        # Strip any leading directory in the zip
                        out_name = Path(name).name
                        with z.open(name) as src, open(target / out_name, "wb") as dst:
                            shutil.copyfileobj(src, dst)
        else:
            # Loose-asset plugins (rare): main.js + manifest.json + maybe styles.css
            for fname in ("main.js", "manifest.json", "styles.css"):
                asset = next((a for a in rel.get("assets", []) if a["name"] == fname), None)
                if asset:
                    with urllib.request.urlopen(asset["browser_download_url"], timeout=60) as r:
                        (target / fname).write_bytes(r.read())
        print(f"  + {plugin_id} installed")
        return True
    except Exception as e:
        print(f"  ! {plugin_id} install failed: {e}", file=sys.stderr)
        return False

# Install each plugin
installed = []
for pid, repo in PLUGINS.items():
    if install_plugin(pid, repo):
        installed.append(pid)

# Mark them as enabled by writing community-plugins.json (the file Obsidian
# reads to know which community plugins to load on startup).
cp_file = OBSIDIAN_DIR / "community-plugins.json"
existing = []
if cp_file.exists():
    try:
        existing = json.loads(cp_file.read_text())
    except Exception:
        existing = []
for pid in installed:
    if pid not in existing:
        existing.append(pid)
cp_file.write_text(json.dumps(existing, indent=2))

# Configure app.json — sort files by most recently modified (newest first).
# Merge with existing settings so we don't clobber anything the user already set.
app_file = OBSIDIAN_DIR / "app.json"
app_settings = {}
if app_file.exists():
    try:
        app_settings = json.loads(app_file.read_text())
    except Exception:
        app_settings = {}
app_settings.setdefault("fileSortOrder", "byModifiedTime")
app_file.write_text(json.dumps(app_settings, indent=2))

# Write sortspec.md for custom-sort plugin — sorts ALL folders by the most
# recently modified file inside them recursively (newest first).
# Uses "advanced recursive modified" which traverses the full folder tree,
# so folders bubble up based on the newest note anywhere inside them.
sortspec_file = VAULT_DIR / "sortspec.md"
if not sortspec_file.exists():
    sortspec_file.write_text(
        "---\nsorting-spec: |\n  target-folder: /*\n  > advanced recursive modified\n---\n"
    )
    print("sortspec.md created — folders will sort by most recently modified note (recursive).")
else:
    print("sortspec.md already exists — skipping.")

# Pre-activate custom-sort plugin by writing data.json with suspended: false.
# The plugin defaults to suspended: true on first install, which means it does
# nothing until the user manually clicks the ribbon toggle. Writing data.json
# here skips that manual step entirely.
custom_sort_data = PLUGINS_DIR / "custom-sort" / "data.json"
if "custom-sort" in installed and not custom_sort_data.exists():
    custom_sort_data.write_text(json.dumps({"suspended": False}, indent=2))
    print("custom-sort pre-activated (suspended: false written to data.json).")

print(f"\nDone. Installed {len(installed)}/{len(PLUGINS)} plugins.")
print("File explorer set to sort by most recently modified.")
print("If Obsidian is currently open, the user must reload it (Cmd/Ctrl+R) for plugins to activate.")
PY
```

**After the script runs:**
- If all plugins succeeded: tell the user *"Done — all plugins installed. If Obsidian is open right now, close and reopen it (or press Cmd+R / Ctrl+R) so they activate."*
- If any plugin failed (network error, GitHub rate limit, etc.): fall back to the manual UI walkthrough for ONLY the failed plugins. Don't make the user click through plugins that already installed successfully.
- If the auto-install fails entirely (no Python, no network, vault path wrong): fall back to the full manual UI walkthrough below.

**Manual fallback (only if auto-install failed):**

"Now let's install the plugins that make everything work. In Obsidian: Settings → Community Plugins → Turn on community plugins → Browse."

Walk them through installing and enabling each one:

1. **Dataview** — "Search 'Dataview' → Install → Enable. Powers live queries and dashboards."
2. **Templater** — "Search 'Templater' → Install → Enable. Auto-applies templates when you create notes."
3. **Tasks** — "Search 'Tasks' → Install → Enable. Tracks to-dos across your vault."
4. **Calendar** — "Search 'Calendar' → Install → Enable. Visual calendar view of your journal entries."
5. **Smart Connections** — "Search 'Smart Connections' → Install → Enable. AI-powered note linking, finds connections you'd miss."
6. **Local REST API** — "Search 'Local REST API' → Install → Enable. Lets Claude interact with your vault directly."
7. **Juggl** — "Search 'Juggl' → Install → Enable. Interactive graph visualization of your notes."

"All installed and enabled? Let's keep going."

## Phase 3: Create Folder Structure

"I'm going to create your folder structure now. This is how your vault will be organized."

**BEFORE CREATING ANYTHING — check what already exists.** The user may have already organized their vault. Scan the top-level folder first. If a folder already exists (even with a slightly different name), use it — don't create a duplicate. If a file was manually moved since setup, respect its new location. Claude's idea of "where something should go" is always subordinate to where it actually is right now. This prevents the most common setup complaint: Claude recreating files the user already moved.

Create these CORE folders in their vault (emojis are important — they make the sidebar scannable):

```
📓 Journals/
📓 Journals/Monthly Summaries/
📓 Journals/Weekly Insights/
📓 Journals/Monthly Insights/
🏠 Home/
👤 CRM/
📝 Notes/
⚙️ Meta/
⚙️ Meta/scripts/
```

**Conditional folders — only create if relevant based on what they told you in Phase 1. These are BLOCKING conditionals, not suggestions. If the user did not explicitly opt in, DO NOT create the folder, DO NOT add it to the vault map, DO NOT reference it in their CLAUDE.md or RESOLVER files.**

- `✍️ Writing/` — **ONLY if `WRITES_PUBLICLY = true` from Phase 1 question 5.** Journaling does NOT count (that's `📓 Journals/`). This folder is for content written with an audience in mind: blog posts, book drafts, newsletters, Substack, essays. If the user said no or was unclear, **skip this folder entirely**. Do not create `Writing/Drafts/`, do not add "Writing/" to the Notes RESOLVER.md decision tree, do not add writing-related rules to the Phase 4 CLAUDE.md template, do not reference Writing/ anywhere downstream. The default state for a new user is: no Writing folder.
- `📚 Books/` — **ONLY if they read books and highlight/annotate.** Ask in Phase 1 or infer from their answer about existing notes. If they mention Kindle, Readwise, book notes, or reading habits, create it. Otherwise skip. Most people don't need an empty Books folder sitting in their sidebar.
- `🧠 Psychology/` — **ONLY if they explicitly mention inner work, therapy, self-help, psychology, behavioral patterns, or personal development as a focus area.** This is a niche folder. Most people's reflections live naturally in Journals/ and Notes/. Don't create it by default.
- `💼 Business/` — only if they have a business, startup, or side project
- `🚀 [Project Name]/` — if they have an active project/startup, give it its own emoji folder
- `🏫 School/` — only if they're a student
- `🌱 Curiosities/` — for people who want a catch-all for random interests

**Why this matters:** previously, Writing/ was created by default for almost everyone because the conditional was too weak. The result was vaults with empty Writing folders for users who don't write, and Claude trying to create drafts in folders that shouldn't exist. Fix: require explicit opt-in.

Tell them: "Done — you should see the folders in your Obsidian sidebar now. The emojis help you scan quickly. If you have a specific area of your life that needs its own folder (a creative project, school, etc.), tell me and I'll add it."

**Add any custom folders they request. Always use emojis.**

After creating folders, create a RESOLVER.md in each key directory. This is a short decision tree answering "does X live here?" — it prevents the vault from decaying into ambiguity as it grows.

**👤 CRM/RESOLVER.md:**
```markdown
# Does this live in CRM/?

1. Is this a real person you've interacted with or plan to? → YES: create [Name].md here
2. Is it a company, org, or brand (not a specific person)? → NO: Business/ or Notes/
3. Is it a public figure you've never met? → NO: Notes/ or Books/
4. Is it a group you have a relationship with as a whole? → YES, if you interact with them as a unit
```

**📝 Notes/RESOLVER.md:**
```markdown
# Does this live in Notes/?

1. Is this from a book you read and the user has a 📚 Books/ folder? → NO: 📚 Books/. (Omit this line if no Books/ folder exists.)
2. Is this a psychology/behavioral concept and the user has a 🧠 Psychology/ folder? → Maybe: 🧠 Psychology/. (Omit this line if no Psychology/ folder exists.)
3. Is this an article, course, or how-to you learned from? → YES: create here
4. Is this a concept that belongs to a specific project? → NO: that project's folder
5. Is this your own original framework or thesis? → If short/raw, it can stay here or in a journal. If you're developing it into something longer, put it wherever your creative work lives. (Only mention `Writing/` here if the user has a `✍️ Writing/` folder — otherwise omit the whole sentence about drafts. Don't reference folders that don't exist in this user's vault.)
```
