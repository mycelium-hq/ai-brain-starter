# Obsidian Rules

*Wikilink hygiene, naming conventions, and import safety. These rules prevent the most common vault corruption patterns discovered during a 5,900-file audit.*

1. **Always wikilink.** First occurrence per file. Use alias syntax: `[[Commitment|committed]]`. **Bare filenames only, never paths.** Write `[[Colombia]]`, never `[[Folder/Colombia]]`. Obsidian resolves bare names globally. Path-form wikilinks break graph canonicalization (duplicate god nodes) and leak folder structure into shared docs.
2. **Block references for quotes.** Never copy-paste. Use `^block-id` at end of source paragraph + `![[File#^block-id]]` embed.
3. **Optimize for navigation.** Dense links in, dense links out. Every note navigable.
4. **Right folder for concepts.** Keep concept notes in the folder that matches their domain. No duplicates across folders.
5. **New concepts get own note.** In the right folder with: description, connected concepts, dataview query.
6. **YAML frontmatter.** Minimum: `creationDate`. Add `type:` (concept/journal/company/article/person) where applicable.
7. **Aliases in frontmatter** for inline linking: `aliases: [vulnerable, vulnerabilities]`. If you write in multiple languages, both map to the same concept note. Never create parallel translated notes.
8. **No pipe aliases in tables.** `[[Note|alias]]` inside table rows breaks the `|` column separator. Use `[[Note\|alias]]` (escaped pipe) or list format instead.
9. **Block IDs at END of paragraph.** Followed by blank line. Never mid-paragraph.
10. **Never `.md` in display text.** Use `**[[File Name]]**`.
11. **Descriptive file names on import.** Rename cryptic filenames (hashes, UUIDs) to descriptive ones before adding to vault.
12. **Wikilink new content on import.** Add wikilinks inline from external sources. No source prefixes in filenames (no "Slack -", "Google Drive -").
13. **CRM on import.** When importing transcripts/meeting notes mentioning people: update CRM entries. Preserve dataview blocks in CRM files, never replace them with narratives.
14. **Log decisions.** Use a decision template: What / Why / Stakes / Speed / Outcome / Pattern. Append to a decision log, never edit the log directly.
15. **Capture original thinking verbatim.** Exact phrasing, never paraphrase. Place in the right location.
16. **Check before creating.** No new folders/files without verifying they don't exist. Grep first. If manually moved, respect the new location.
17. **Fresh-Read before Edit.** Any edit more than ~5 min after last read of that file requires re-reading first. Prevents lost-update races with Obsidian edits or concurrent sessions.
18. **Never wikilink inside URLs.** If text is part of a URL (`http...` to next whitespace), do NOT insert `[[wikilinks]]` into it. Auto-linking scripts and manual linking must skip URL spans entirely. A URL like `https://www.linkedin.com/in/someone` must never become `https://www.[[Networking|linkedin]].com/in/someone`.
19. **No em dashes in filenames.** Use ` - ` (space-hyphen-space) instead of ` — ` in all note titles. Em dashes break Obsidian anchor links, TOC slugs, and cross-vault wikilink resolution.
20. **Heading links use wikilink syntax.** Within-file TOC links must use `[[#Exact Heading Text|display]]`, never markdown anchor syntax `[display](#slug)`. Obsidian's slug generation differs from standard markdown, especially with emojis, special characters, and non-ASCII text. Markdown anchors silently break.
21. **No Roam artifacts.** Wikilinks starting with `[[//` or `![[//` are Roam Research export leftovers and will never resolve in Obsidian. On import or discovery: extract display text for references, comment out image embeds, delete template refs.
