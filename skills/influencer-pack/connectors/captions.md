# Connector: Captions / VEED

Captions and VEED are AI-assisted video editors used by creators for caption overlays, talking-head editing, and long-form-to-short-form cuts. The connector covers both tools (they have similar workflows) plus other AI editors that follow the same pattern.

## API surface

- Captions: https://www.captions.ai/. No public API as of pack publication date. Workflow integration only.
- VEED: https://www.veed.io/. Has an API in beta at https://www.veed.io/api but most creator workflows use the web app.
- Auth: web-app login. Both tools allow video import via URL or upload.

## Resources mapped to typed-memory categories

| Asset | Substrate category | Sync direction |
|---|---|---|
| Edited final cuts (caption-overlaid Reels, trimmed clips) | `content-piece` enrichment with `production_assets: [<path>]` | manual (creator exports + drops into vault folder) |
| Source recordings (the original talking-head video before editing) | `content-source` with `subtype: raw-recording` | manual upload to vault |

## Operator workflow

1. Creator records talking-head content (phone, webcam, or studio).
2. Source file lands at `External Inputs/Captions/Source/<YYYY-MM-DD>-<slug>.mp4` (or VEED equivalent).
3. Creator opens Captions or VEED, imports the source, applies template (Eye-Contact / Talking-Head / Reels-Cut depending on output), exports.
4. Edited cuts land at `External Inputs/Captions/Edited/<YYYY-MM-DD>/<slug>-final.mp4`.
5. The `/content-engine` skill picks up the edited cuts and links them to the relevant scheduled `content-piece` records.

## Caption-template metadata

Both tools support custom caption templates (font, color, animation). The pack init step asks the creator to save their default template name so `/content-engine` can reference it consistently in the editor.

## Privacy + retention

- Source recordings can contain sensitive content (off-camera audio, brand-deal NDA material). Retention defaults to 60 days unless the creator extends.
- Edited final cuts get linked into `content-piece` records and follow the same retention as the published piece.
- Both tools store creator content on their own servers as part of the editing workflow. The substrate does not control that retention; the creator is on whatever the tool's data-retention policy is.

## Alternatives the pack supports interchangeably

- CapCut (free, cross-platform)
- Adobe Premiere with Auto-Caption
- Descript
- Riverside.fm (also includes recording)
- Submagic

Same workflow pattern: source recording into vault, tool-edit, export, cuts back into vault. The init step asks which editor the creator uses and configures the folder names.
