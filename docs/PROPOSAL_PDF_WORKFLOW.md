---
name: proposal-pdf-workflow
description: Turn a markdown proposal into a letterpress-quality branded PDF using pandoc and WeasyPrint
---

# Proposal PDF workflow

Ship a branded, professional-looking PDF proposal from a markdown source file — no design tool, no manual reformatting, no "paste into Word and tweak for an hour." Works for proposals, contracts, reports, one-pagers, or any formal business document where the container needs to match the content.

## When to use this

- You write your proposal in markdown (probably in Obsidian or your editor of choice)
- You want a PDF that looks like a consulting firm produced it, not like a markdown export
- Your audience expects formal business register, not a startup pitch deck aesthetic
- You want the same source file to render consistently for every client without manual styling per deal

Typical use case: you're an independent consultant, a small agency, or a founder sending proposals that compete against Big 4 / boutique consultancy deliverables. Your proposal needs to survive "does this person know what they're doing" on visual signal alone.

## When NOT to use this

- You need heavy visual design (branded illustrations, custom logos, photo layouts) — use Canva or Figma
- You want something playful or marketing-flavored — this CSS is deliberately sober
- Your client expects a slide deck — this is document-format, not slide-format

## Install

```bash
brew install pandoc weasyprint
```

- **pandoc**: markdown → HTML5 conversion (~275 MB, worth it)
- **weasyprint**: HTML + CSS → PDF with real `@page` rule support (letterhead, page numbers, margins)

Verify:

```bash
pandoc --version | head -1
weasyprint --version
```

## Use

1. **Copy the CSS snippet into place.**
   - For Obsidian export: `cp templates/obsidian-snippets/proposal-letterhead.css your-vault/.obsidian/snippets/`
   - For pandoc CLI: `cp templates/obsidian-snippets/proposal-letterhead.css /tmp/proposal-print.css` (or anywhere accessible)

2. **Customize the letterhead.**
   - Open `proposal-letterhead.css`
   - Search for `{{CUSTOMIZE}}` — two places
   - Replace the placeholder `"Your Name  ·  yoursite.com"` with your actual name and site
   - Replace `"Proposal Document"` with a short doc title like `"Proposal for Acme Corp"`
   - Save

3. **Generate the PDF.**

   **Path A — Obsidian UI (easiest for one-off):**
   - Settings → Appearance → CSS snippets → toggle `proposal-letterhead` ON
   - Open the proposal note in Reading Mode
   - `Cmd+P` → "Export to PDF"
   - Page size: US Letter
   - Save to Desktop

   **Path B — Command line (repeatable, scriptable):**

   ```bash
   INPUT="path/to/proposal.md"
   OUTPUT="$HOME/Desktop/proposal.pdf"

   pandoc "$INPUT" \
     --from markdown+yaml_metadata_block \
     --to html5 \
     --standalone \
     --css /tmp/proposal-print.css \
     --metadata title="" \
     -o /tmp/proposal.html

   weasyprint /tmp/proposal.html "$OUTPUT"
   ```

   The empty `--metadata title=""` suppresses pandoc's auto-generated title block (you want your document to open with your Carta de presentación or opening letter, not with "proposal.md" as an H1).

## What the output looks like

- **Page 1:** no running header, clean opening page for your carta / cover letter
- **Pages 2+:** italic navy letterhead top-left ("Your Name · yoursite.com"), document title top-right, page numbers ("N / total") bottom-center
- **Section headers:** Georgia serif, deep navy (#1a365d), hairline underlines
- **Body text:** Georgia 11pt, line-height 1.55, justified with auto-hyphenation
- **Bold text:** also in navy — bold becomes a second hierarchy signal instead of shouting
- **Tables:** navy headers on pale-grey fill, hairline borders, clean business-document feel
- **Horizontal rules (`---`):** short centered hairlines, 30% width, elegant section breaks

Typography is deliberately classic — Georgia, navy accent, generous margins, justified text with auto-hyphenation. Reads as "law firm" or "senior consulting firm" rather than "SaaS startup." This is the right register for most formal business proposals.

## Customizing the accent color

Default is deep navy (`#1a365d`). To change:

1. Open `proposal-letterhead.css`
2. Find-and-replace `#1a365d` with your color

Recommended alternatives for formal business documents:

| Color | Hex | Signal |
|---|---|---|
| Burgundy | `#722f37` | Authoritative, legal-document feel |
| Forest green | `#2d4a3e` | Stability, growth |
| Charcoal | `#2d3748` | Understated, modern |
| Oxford blue | `#002147` | Very traditional |

Avoid bright accent colors (red, orange, bright blue) for formal client documents — they read as marketing, not professional services.

## Proposal structure that works with this CSS

Formal business proposals generally benefit from this section order. Your content varies; the structure is transferable:

1. **Carta de presentación / Cover letter** — warm opening, addressed to the decision-maker, includes your credibility context
2. **Resumen ejecutivo / Executive summary** — 4-6 bullets: problem, solution, timeline, investment, guarantee
3. **Antecedentes / Background** — the client's context, what makes their situation unique
4. **Problema en detalle / Problem detail** — specifics of the work today, pain points
5. **Alcance técnico / Technical scope** — what you will build / deliver, broken into components
6. **Marco normativo / Regulatory framework** — if the work touches regulated domains, cite laws + regulators explicitly (signals rigor to audit-aware clients)
7. **Estructura de operación / Operating structure** — roles of each party, especially if there are intermediaries or related entities
8. **Cronograma / Timeline** — week-by-week for pilot-scale engagements, month-by-month for longer
9. **Propuesta económica / Pricing** — simple table, USD + local currency reference
10. **Forma de pago / Payment terms** — milestones, method, tax treatment, contract basis
11. **Retorno esperado / Expected ROI** — sector references (not guarantees), explicitly defer specific-client numbers to the pilot report
12. **Garantías / Guarantees** — numbered list: result guarantee, IP ownership, confidentiality, liability cap, cancellation terms, continuity plan, backup consultant, auditability
13. **Vigencia de la oferta / Offer validity** — decision deadline (4-6 weeks typical)
14. **Sobre el consultor / About the consultant** — credentials bullets, verifiable
15. **Siguiente paso / Next step** — path to signing (call optional, not mandatory)

For a formal client unfamiliar with your work, sections 3, 6, 7, 11, 12, 13 do most of the credibility work. Skipping any of them reads as "moving fast" rather than "serious."

## Iteration tips

- Regenerate the PDF every time you change the markdown — it's fast (~1 second)
- Use `open output.pdf` on macOS to auto-launch Preview after generating
- If the PDF looks wrong, the issue is almost always the CSS, not pandoc — WeasyPrint is strict about CSS, which is a feature not a bug
- Use `weasyprint --verbose` to see which CSS rules were ignored or misinterpreted
- For version control: commit the `.md` and the `.css`, never the `.pdf` (it's the output, not the source)

## Fonts and encoding

- Default typography is Georgia — pre-installed on macOS and Windows, equivalent fallback Times New Roman
- No web fonts required, no internet connection needed after install
- Works for Spanish, French, Portuguese, German, and other Latin-script languages with diacritics (ñ, á, é, ü, etc.) out of the box
- For non-Latin scripts (Arabic, Chinese, Japanese, etc.) you'll need to add an appropriate font-family declaration and ensure the font is installed

## Troubleshooting

**The PDF has no letterhead.**
Check that the CSS snippet is enabled in Obsidian Settings → Appearance, or that `--css /path/to/proposal-letterhead.css` is passed to pandoc. The `@page` rules only apply in print context — they won't show in Obsidian's reading view.

**The first page has a letterhead.**
That's `@page :first` not working — usually a weasyprint version issue. Upgrade: `brew upgrade weasyprint`.

**Tables are splitting across pages.**
Check for `page-break-inside: avoid` on the table element. If it's there and still splitting, the table is physically too tall for one page — break it into two tables or reduce font size via `table { font-size: 9.5pt !important; }`.

**Bold text is black instead of navy.**
Make sure you're using `**bold**` (markdown) not `<b>` or `<strong>` inline HTML. The CSS targets `strong` element generated by markdown; inline HTML may bypass it.

**The PDF is 30+ pages for a 5-page document.**
Check `font-size: 11pt` and `margin: 1in`. If either got overridden somewhere, the document will blow up. Use `weasyprint --verbose` to trace.

## Credits

This workflow originated in a Colombian consulting engagement where the proposal needed to read as "senior professional services firm" rather than "solo AI consultant." Shared back to the community because the same register is useful for any founder shipping proposals into traditional industry contexts (construction, legal, financial services, professional services, manufacturing, government).

## Related

- `templates/obsidian-snippets/proposal-letterhead.css` — the actual CSS
- `docs/TOKEN_OPTIMIZATION.md` — reducing AI token spend on document iteration
- `docs/BUILD_STANDARDS.md` — general build standards for artifacts that ship to clients
