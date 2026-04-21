#!/usr/bin/env python3
"""
Security snapshot generator. Runs a handful of free security checks against a
prospect domain and writes a client-ready markdown report. Lead magnet for
consulting practices.

Usage:
    python3 security-snapshot.py <domain> [--company "Display Name"] [--out <path>]

Environment:
    VAULT_ROOT       Absolute path to vault. Required for default output location.
    SNAPSHOTS_DIR    Override output root. Defaults to $VAULT_ROOT/security-snapshots/.
    REPORT_SIGNATURE Free-text byline for the report footer. Optional.
    REPORT_CONTACT   Contact email for the report footer. Optional.

Checks performed:
    1. SSL Labs grade (public, no key)
    2. HTTP security headers (local HEAD request)
    3. Email auth DNS records (SPF, DMARC, MX)
    4. Server fingerprint leak (Server/X-Powered-By headers)

Writes a markdown report to:
    $SNAPSHOTS_DIR/<domain>/<YYYY-MM-DD>-snapshot.md

Designed so the output is safe to send to a prospect as-is: no hype, no FUD,
just facts plus plain-English severity ratings.
"""
import argparse
import json
import os
import re
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

VAULT = Path(os.environ.get("VAULT_ROOT", ""))
OUT_ROOT = Path(
    os.environ.get("SNAPSHOTS_DIR")
    or (VAULT / "security-snapshots" if VAULT != Path("") else "security-snapshots")
)

SSL_LABS_API = "https://api.ssllabs.com/api/v3/analyze"
POLL_MAX_SECONDS = 180
USER_AGENT = "Mozilla/5.0 (SecuritySnapshot; free lead-magnet scan)"

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4, "ok": 5}


def http_get_json(url: str, timeout: int = 30) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def http_head(url: str, timeout: int = 15, max_redirects: int = 5):
    """GET with redirect following. Returns (status, headers dict lowercased, final URL).
    Many sites redirect / to /en/ or /home; the redirect response does not carry
    security headers, only the final content page does. Follow up to max_redirects
    hops before giving up."""
    current = url
    for _ in range(max_redirects + 1):
        req = urllib.request.Request(
            current,
            method="GET",
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*"},
        )
        try:
            opener = urllib.request.build_opener(urllib.request.HTTPRedirectHandler())
            opener.addheaders = [("User-Agent", USER_AGENT)]
            with opener.open(req, timeout=timeout) as r:
                return r.status, {k.lower(): v for k, v in r.headers.items()}, r.geturl()
        except urllib.error.HTTPError as e:
            if e.code in (301, 302, 303, 307, 308):
                loc = e.headers.get("Location")
                if loc:
                    current = urllib.parse.urljoin(current, loc)
                    continue
            return e.code, {k.lower(): v for k, v in e.headers.items()}, current
    return 0, {}, current


def check_ssl_labs(domain: str) -> dict:
    """Poll SSL Labs until READY or timeout. Returns simplified result."""
    start = time.time()
    params = f"?host={domain}&all=done&fromCache=on&maxAge=24"
    last = None
    while time.time() - start < POLL_MAX_SECONDS:
        try:
            last = http_get_json(SSL_LABS_API + params, timeout=30)
        except Exception as e:
            return {"ok": False, "error": f"SSL Labs unreachable: {e}"}
        status = last.get("status")
        if status in ("READY", "ERROR"):
            break
        time.sleep(10)
    if not last or last.get("status") != "READY":
        return {"ok": False, "error": f"SSL Labs timeout, last status: {last.get('status') if last else 'none'}"}
    endpoints = last.get("endpoints") or []
    if not endpoints:
        return {"ok": False, "error": "No endpoints returned"}
    grades = [e.get("grade") for e in endpoints if e.get("grade")]
    worst = sorted(grades, key=lambda g: (g[0], len(g)))[-1] if grades else None
    return {
        "ok": True,
        "grade": worst,
        "endpoints": len(endpoints),
        "cert_expires": endpoints[0].get("details", {}).get("cert", {}).get("notAfter"),
    }


def check_security_headers(domain: str) -> dict:
    """Grade HTTP response headers. A rough analogue of securityheaders.com."""
    results = {"protocol": None, "headers": {}, "missing": [], "present": [], "leaks": []}
    h = None
    for scheme in ("https", "http"):
        try:
            status, h, final_url = http_head(f"{scheme}://{domain}/")
            results["protocol"] = scheme
            results["status"] = status
            results["final_url"] = final_url
            break
        except Exception as e:
            results["fetch_error"] = str(e)
            continue
    if h is None:
        return {"ok": False, **results}

    required = {
        "strict-transport-security": "HSTS (forces HTTPS)",
        "content-security-policy": "CSP (mitigates XSS)",
        "x-frame-options": "X-Frame-Options (clickjacking)",
        "x-content-type-options": "X-Content-Type-Options (MIME sniffing)",
        "referrer-policy": "Referrer-Policy (privacy)",
        "permissions-policy": "Permissions-Policy (feature gating)",
    }
    for key, label in required.items():
        if key in h:
            results["present"].append({"name": key, "label": label, "value": h[key][:200]})
        else:
            results["missing"].append({"name": key, "label": label})

    for leak_key in ("server", "x-powered-by", "x-aspnet-version"):
        if leak_key in h:
            results["leaks"].append({"name": leak_key, "value": h[leak_key][:120]})

    return {"ok": True, **results}


def check_dns_email_auth(domain: str) -> dict:
    """Check SPF, DMARC, and MX records via local dig."""
    out = {"ok": True, "spf": None, "dmarc": None, "mx": []}

    def dig(name: str, record_type: str):
        try:
            r = subprocess.run(
                ["dig", "+short", record_type, name],
                capture_output=True, text=True, timeout=10,
            )
            return [line.strip() for line in r.stdout.splitlines() if line.strip()]
        except Exception:
            return []

    txt = dig(domain, "TXT")
    for record in txt:
        if "v=spf1" in record.lower():
            out["spf"] = record

    dmarc = dig(f"_dmarc.{domain}", "TXT")
    for record in dmarc:
        if "v=dmarc1" in record.lower():
            out["dmarc"] = record

    out["mx"] = dig(domain, "MX")
    return out


def grade_to_severity(grade):
    if not grade:
        return "critical"
    if grade.startswith("A"):
        return "ok"
    if grade.startswith("B"):
        return "medium"
    return "high"


def build_findings(ssl_res: dict, headers_res: dict, dns_res: dict):
    findings = []

    if ssl_res.get("ok"):
        grade = ssl_res.get("grade")
        findings.append({
            "category": "TLS/SSL",
            "title": f"SSL Labs grade: {grade}",
            "severity": grade_to_severity(grade),
            "detail": f"Certificate expires {ssl_res.get('cert_expires')}. Grade below A means outdated ciphers or config."
                      if grade and not grade.startswith("A") else
                      f"Certificate expires {ssl_res.get('cert_expires')}.",
        })
    else:
        findings.append({
            "category": "TLS/SSL",
            "title": "Could not analyze TLS",
            "severity": "high",
            "detail": ssl_res.get("error", "unknown"),
        })

    if headers_res.get("ok"):
        for m in headers_res.get("missing", []):
            sev = "high" if m["name"] in ("strict-transport-security", "content-security-policy") else "medium"
            findings.append({
                "category": "HTTP headers",
                "title": f"Missing header: {m['name']}",
                "severity": sev,
                "detail": m["label"],
            })
        for leak in headers_res.get("leaks", []):
            findings.append({
                "category": "HTTP headers",
                "title": f"Fingerprint leak: {leak['name']}",
                "severity": "low",
                "detail": f"Response exposes: {leak['value']}. Attackers use this to narrow exploits.",
            })
    else:
        findings.append({
            "category": "HTTP headers",
            "title": "Could not fetch HTTP headers",
            "severity": "medium",
            "detail": headers_res.get("fetch_error", "unknown"),
        })

    if not dns_res.get("spf"):
        findings.append({
            "category": "Email auth",
            "title": "No SPF record",
            "severity": "high",
            "detail": "SPF prevents email spoofing from your domain. Without it, anyone can send emails that look like they came from you.",
        })
    if not dns_res.get("dmarc"):
        findings.append({
            "category": "Email auth",
            "title": "No DMARC record",
            "severity": "high",
            "detail": "DMARC enforces SPF/DKIM policy and gives you visibility into spoofing attempts.",
        })

    findings.sort(key=lambda f: SEVERITY_ORDER.get(f["severity"], 99))
    return findings


def render_report(domain, company, ssl_res, headers_res, dns_res, findings):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    sev_counts = {}
    for f in findings:
        s = f["severity"]
        if s != "ok":
            sev_counts[s] = sev_counts.get(s, 0) + 1
    top_issues = sev_counts.get("critical", 0) + sev_counts.get("high", 0)

    headline = (
        f"{top_issues} high-priority issues"
        if top_issues else
        "No high-priority issues found. Nice hygiene."
    )

    lines = [
        "---",
        f"creationDate: {today}",
        "type: security-snapshot",
        f"domain: {domain}",
        f"company: {company}",
        f"ssl_grade: {ssl_res.get('grade') or 'n/a'}",
        f"high_priority_findings: {top_issues}",
        "---",
        "",
        f"# Security hygiene snapshot: {company}",
        "",
        f"*Run on {today} against `{domain}`. This is a passive, unauthenticated scan of publicly visible configuration. It is not a penetration test.*",
        "",
        "## Summary",
        "",
        f"**{headline}**",
        "",
        "| Severity | Count |",
        "|---|---|",
    ]
    for sev in ("critical", "high", "medium", "low"):
        lines.append(f"| {sev.title()} | {sev_counts.get(sev, 0)} |")
    lines.extend([
        "",
        "## Findings",
        "",
    ])

    if not findings:
        lines.append("No findings. Unusual, please double check that the domain is live.")
    else:
        current_cat = None
        for f in findings:
            if f["category"] != current_cat:
                current_cat = f["category"]
                lines.append(f"### {current_cat}")
                lines.append("")
            badge = f["severity"].upper()
            lines.append(f"**[{badge}] {f['title']}**")
            lines.append("")
            lines.append(f["detail"])
            lines.append("")

    lines.extend([
        "## What we checked",
        "",
        "1. **TLS/SSL configuration** via SSL Labs public API. Grades the certificate chain, protocol support, and cipher suites.",
        "2. **HTTP security headers** via a live request to the homepage. Checks for HSTS, CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy.",
        "3. **Email authentication** via DNS lookup. Checks SPF and DMARC records that prevent domain spoofing.",
        "4. **Server fingerprint leaks** in HTTP response headers. Attackers use `Server` and `X-Powered-By` to narrow exploit targets.",
        "",
        "## What this does NOT cover",
        "",
        "- Application-layer vulnerabilities (SQL injection, XSS in specific endpoints, auth flaws)",
        "- Cloud infrastructure misconfigurations (S3 buckets, IAM policies)",
        "- Credential exposure in past breaches (separate check, requires Have I Been Pwned paid tier)",
        "- Internal network posture",
        "- Employee security training gaps",
        "",
        "A full security review covers all of the above. This snapshot is a 15-minute conversation starter, not a complete audit.",
    ])

    signature = os.environ.get("REPORT_SIGNATURE")
    contact = os.environ.get("REPORT_CONTACT")
    if signature or contact:
        footer_parts = []
        if signature:
            footer_parts.append(f"Prepared by {signature}.")
        if contact:
            footer_parts.append(f"Questions: {contact}.")
        lines.extend(["", "---", "", f"*{' '.join(footer_parts)}*"])

    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("domain", help="Prospect domain, e.g. acme.com")
    ap.add_argument("--company", help="Display name for the report (defaults to domain)")
    ap.add_argument("--out", help="Override output path")
    ap.add_argument("--json", action="store_true", help="Dump raw JSON instead of markdown")
    args = ap.parse_args()

    raw = args.domain.strip().lower().rstrip("/")
    for prefix in ("https://", "http://"):
        if raw.startswith(prefix):
            raw = raw[len(prefix):]
            break
    domain = raw
    company = args.company or domain

    print(f"Running security snapshot for {domain}...", file=sys.stderr)
    print("  [1/3] SSL Labs (can take 60-120s)...", file=sys.stderr)
    ssl_res = check_ssl_labs(domain)
    print(f"        grade={ssl_res.get('grade')} ok={ssl_res.get('ok')}", file=sys.stderr)

    print("  [2/3] HTTP security headers...", file=sys.stderr)
    headers_res = check_security_headers(domain)
    print(f"        missing={len(headers_res.get('missing', []))} leaks={len(headers_res.get('leaks', []))}", file=sys.stderr)

    print("  [3/3] DNS email auth...", file=sys.stderr)
    dns_res = check_dns_email_auth(domain)
    print(f"        spf={bool(dns_res.get('spf'))} dmarc={bool(dns_res.get('dmarc'))}", file=sys.stderr)

    findings = build_findings(ssl_res, headers_res, dns_res)

    if args.json:
        print(json.dumps({
            "domain": domain,
            "ssl": ssl_res,
            "headers": headers_res,
            "dns": dns_res,
            "findings": findings,
        }, indent=2, ensure_ascii=False))
        return 0

    report = render_report(domain, company, ssl_res, headers_res, dns_res, findings)

    if args.out:
        out_path = Path(args.out)
    else:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        out_dir = OUT_ROOT / domain
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{today}-snapshot.md"

    out_path.write_text(report)
    print(f"Report saved: {out_path}", file=sys.stderr)
    print(str(out_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
