---
name: block-personal-data-in-public-repo
enabled: false
event: file
action: block
conditions:
  - field: file_path
    operator: contains
    pattern: YOUR-PUBLIC-REPO-NAME
  - field: new_text
    operator: regex_match
    pattern: YOUR_NAME|YOUR_COMPANY|YOUR_CITY
---

**Personal data in public repo.** This repo is public. Never write personal names, company names, vault paths, or identifying details. Use generic/placeholder content. Remove the personal references and try again.

To use this template:
1. Replace YOUR-PUBLIC-REPO-NAME with your repo directory name
2. Replace the pattern with your actual personal identifiers (pipe-separated)
3. Set enabled: true
