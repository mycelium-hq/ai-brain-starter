---
name: block-em-dash
enabled: true
event: file
action: block
conditions:
  - field: file_path
    operator: regex_match
    pattern: \.(md|txt)$
  - field: file_path
    operator: regex_match
    pattern: /(Substack|LinkedIn|Pitch|Investor|Sales|Marketing|Press|Newsletter|Deck)/
  - field: new_text
    operator: regex_match
    pattern: \u2014
---

**Em dash detected in external-facing content.** Never use em dashes in publishable output. Use commas, colons, periods, or parentheses instead. Rewrite without the em dash and try again.

Scope: only `.md` / `.txt` files inside a publish folder (`/Substack/`, `/LinkedIn/`, `/Pitch/`, `/Investor/`, `/Sales/`, `/Marketing/`, `/Press/`, `/Newsletter/`, `/Deck/`). Code files (`.html`, `.py`, `.ts`, `.json`, etc.), internal notes, journals, scripts, and memory files are not affected.

Customize the publish-folder list to match your vault. The capitalized, slash-anchored pattern prevents stray substring matches like `feedback_no_em_dash.md` or `marketing-automation.py`.
