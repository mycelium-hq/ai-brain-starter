---
name: seo-substrate
description: SEO + GEO substrate for solo founders and indie creators. Covers technical SEO, on-page optimization, schema markup, AI-search-optimization (GEO), Google Search Console + GA4 wiring, bilingual routing (hreflang), and per-post Substack optimization. Use when the user says /seo-audit, /seo-fix, /geo-audit, /substack-seo, or asks to audit, fix, or optimize SEO on a single page, blog post, or whole site. Scoped for two-site stacks (consulting site + creator/Substack), not enterprise e-commerce or programmatic SEO.
---

# /seo-substrate — focused SEO + GEO for solo operators

Lean SEO substrate for a solo founder running a consulting site, a Substack newsletter, and adjacent surfaces. Trades exhaustive enterprise tooling for the slice that actually moves the needle: surface coverage > tooling depth.

Cherry-picked from `~/.claude/skills/claude-seo/` (25 sub-skills + 18 sub-agents) — kept the substrate primitives, dropped enterprise + e-commerce + DataForSEO/Firecrawl-paid extensions. Source-of-truth for why this is leaner: solo operators do not need 43 sub-modules for two sites.

## When to use

- User says `/seo-audit <url>` — full audit on a single page
- User says `/seo-fix <file-or-url>` — apply concrete fixes to a draft post or live page
- User says `/geo-audit <url>` — GEO-only pass (AI search readiness)
- User says `/substack-seo <draft.md>` — per-post Substack optimization before publish
- User asks to optimize, audit, fix, or improve SEO on a specific surface

Do NOT use for:
- Enterprise / e-commerce SEO with 10K+ SKU catalogs (use `~/.claude/skills/claude-seo/skills/seo-ecommerce/` instead)
- Paid advertising (PPC, programmatic ads)
- Programmatic SEO at scale (5K+ generated pages)
- Backlink outreach campaigns (manual relationship work, not skill territory)

## Capability surface

This substrate ships these audit + fix capabilities. Each is a self-contained section below.

| Capability | Audit pass | Fix pass |
|---|---|---|
| Technical SEO (crawlability, indexability, speed) | ✓ | ✓ |
| On-page (title, description, H-hierarchy, image alt, internal linking) | ✓ | ✓ |
| Schema markup (JSON-LD for Article, BlogPosting, Person, Organization, BreadcrumbList) | ✓ | ✓ |
| GEO (AI search optimization for ChatGPT, Claude, Perplexity, Gemini surfaces) | ✓ | ✓ |
| Bilingual routing (hreflang, lang attr, locale subdir) | ✓ | ✓ |
| Search Console + GA4 wiring (property verification, coverage report, top queries) | ✓ | ✗ (UI-only) |
| Per-post Substack optimization (slug + summary + tags + social card + internal links) | ✓ | ✓ |

What this substrate does NOT cover (handle manually or use specialist skill):
- Backlink profile audit (out: needs DataForSEO or Ahrefs paid API; not solo-operator-substrate territory)
- Crawl budget at >1000 pages (out: solo sites are sub-200 pages typically)
- E-commerce structured data for product variants (use `claude-seo/skills/seo-ecommerce/`)
- Local SEO with multi-location NAP (out: solo operators have single identity)

## Audit flow (default invocation)

1. **Detect surface type** from input:
   - `*.substack.com/p/*` → Substack post mode (use the per-post checklist below)
   - root domain or path on consulting site → general audit (technical + on-page + schema + GEO)
   - bilingual subdomain or `/es/` path → add bilingual-routing pass
2. **Pull current state** via `curl -s -L -A "Mozilla/5.0" <url>` to get rendered HTML. Parse with `python3 -c "from bs4 import BeautifulSoup; ..."`.
3. **Run audits in order** (cheap → expensive):
   1. Technical (status code, robots.txt, sitemap.xml, canonical, hreflang, x-robots-tag header)
   2. On-page (title length 30-60, description 120-158, H1 single, H-hierarchy logical, image alt coverage, internal links count + targets)
   3. Schema (presence + validity of JSON-LD, type-appropriate fields filled)
   4. GEO (TL;DR-style summary up top, fact density per paragraph, citation-friendly structure, last-updated date visible, author byline with link)
   5. Bilingual (lang attr matches content, hreflang reciprocal pairs)
4. **Output single-page report** with:
   - Quick-fix list (sub-1-hour items, prioritized by impact)
   - Deep-fix list (over 1 hour, may need code changes)
   - Pass/fail per capability
   - Specific selectors + line numbers for in-place fixes

## Technical SEO checklist

- [ ] Status code 200 on canonical URL; 301 (not 302) for redirects
- [ ] `robots.txt` exists, allows crawl on production paths, blocks staging
- [ ] `sitemap.xml` exists, lists canonical URLs, last-modified accurate, no 404 entries
- [ ] `<link rel="canonical">` on every page; canonical is self-referential or points at the correct primary
- [ ] `<meta name="robots" content="...">` present where non-default (noindex on tag pages, etc.)
- [ ] HTTPS-only, valid cert, no mixed content
- [ ] Mobile viewport meta tag (`<meta name="viewport" content="width=device-width, initial-scale=1">`)
- [ ] Largest Contentful Paint under 2.5s on 4G mobile (test via PageSpeed Insights)
- [ ] Cumulative Layout Shift under 0.1
- [ ] Interaction-to-Next-Paint under 200ms
- [ ] No render-blocking resources >150KB without async/defer
- [ ] Static assets fingerprinted (cache-busting for deploys)

## On-page checklist

- [ ] `<title>` 30-60 chars, primary keyword in first 50 chars, brand suffix optional
- [ ] `<meta name="description">` 120-158 chars, includes primary keyword, written for human click-through not keyword stuffing
- [ ] Single `<h1>` per page (not zero, not two)
- [ ] H-hierarchy logical (no h3 before h2 inside same section)
- [ ] All images have `alt=""` (decorative) or descriptive alt text (informative)
- [ ] At least 3 internal links per content page, pointing at other content pages (not just nav)
- [ ] No orphan pages (every content page is reachable from at least one other content page)
- [ ] URL is short, hyphen-separated, lowercase, no stop words
- [ ] Content has at least 300 words on landing pages, 600+ on cornerstone content
- [ ] Reading-level scan (Flesch-Kincaid) — match audience; if technical, denser is fine

## Schema markup (JSON-LD)

Minimum required schema per page type:

### Blog post / Substack article
```json
{
  "@context": "https://schema.org",
  "@type": "BlogPosting",
  "headline": "<title>",
  "description": "<meta description>",
  "author": {"@type": "Person", "name": "<author>", "url": "<author-page>"},
  "datePublished": "<ISO date>",
  "dateModified": "<ISO date>",
  "image": "<canonical-image-url>",
  "publisher": {"@type": "Organization", "name": "<brand>", "logo": {"@type": "ImageObject", "url": "<logo-url>"}},
  "mainEntityOfPage": {"@type": "WebPage", "@id": "<canonical-url>"}
}
```

### Person profile / about page
```json
{
  "@context": "https://schema.org",
  "@type": "Person",
  "name": "<full name>",
  "url": "<canonical>",
  "image": "<headshot>",
  "jobTitle": "<role>",
  "worksFor": {"@type": "Organization", "name": "<company>"},
  "sameAs": ["<linkedin>", "<x-or-twitter>", "<github>", "<substack>"]
}
```

### Organization (consulting site / company page)
```json
{
  "@context": "https://schema.org",
  "@type": "Organization",
  "name": "<brand>",
  "url": "<canonical>",
  "logo": "<logo-url>",
  "founder": {"@type": "Person", "name": "<founder>"},
  "contactPoint": {"@type": "ContactPoint", "email": "<contact-email>", "contactType": "customer support"},
  "sameAs": ["<linkedin>", "<x-or-twitter>"]
}
```

### Breadcrumb (any page below root)
```json
{
  "@context": "https://schema.org",
  "@type": "BreadcrumbList",
  "itemListElement": [
    {"@type": "ListItem", "position": 1, "name": "Home", "item": "<root>"},
    {"@type": "ListItem", "position": 2, "name": "<section>", "item": "<section-url>"},
    {"@type": "ListItem", "position": 3, "name": "<page>", "item": "<page-url>"}
  ]
}
```

Validate every schema block with `https://validator.schema.org/` before publish.

## GEO (AI search optimization)

GEO is what gets cited by AI search engines (ChatGPT browsing, Claude with web tool, Perplexity, Gemini, Grok). Different from classic SEO because the consumer is an LLM doing extractive QA, not a human running a query and clicking blue links.

Checklist for GEO readiness:

- [ ] **TL;DR or summary at the top** in 2-4 sentences. LLMs grab this for the citation snippet.
- [ ] **Specific verifiable facts** in the first 200 words: dates, named entities, numbers, exact quotes. Vague intro paragraphs lose to specific ones.
- [ ] **Last-updated date visible** in the HTML (not just `dateModified` schema). LLMs prefer fresh content; a 2024 date hurts visibility against a 2026 page.
- [ ] **Author byline with link to author page** (LLMs use author authority as a citation signal).
- [ ] **Citations to primary sources** in-line where claims are made. LLMs follow the chain.
- [ ] **Q&A blocks where relevant** (format: `## Question` followed by direct answer). LLMs match on question structure.
- [ ] **No login walls or paywalls on cited content.** Blocked content gets dropped from training and citation pools.
- [ ] **Stable URLs over months.** LLMs cache; URL changes break citation continuity.
- [ ] **Brand consistency** in entity names. "Mycelium AI" everywhere, not "the consultancy" or "my AI work" or other paraphrases.
- [ ] **`llms.txt` at root** if you want to direct LLM crawlers (analogous to robots.txt for AI). Format: list of canonical content URLs the site owner wants LLMs to prioritize.

GEO does NOT replace SEO; it layers on top. Pages that pass classic SEO and add the GEO checklist tend to win both surfaces.

## Bilingual routing

If the site publishes EN + ES (or any other language pair):

- [ ] `<html lang="en">` matches actual content language (not always "en" by default)
- [ ] Language switcher visible above the fold; routes to `/es/` or `es.<domain>` consistently
- [ ] `<link rel="alternate" hreflang="en" href="<en-url>" />` AND `<link rel="alternate" hreflang="es" href="<es-url>" />` AND `<link rel="alternate" hreflang="x-default" href="<default-url>" />` on every page
- [ ] Hreflang pairs are reciprocal: EN page lists ES alternate, ES page lists EN alternate
- [ ] Translation is FULL not auto-translated (Google Translate output kills SEO; counts as duplicate content)
- [ ] Per-language sitemap (or one sitemap with hreflang annotations)

## Search Console + GA4

Audit-only (these are configured in the platform UI, not by code):

- [ ] Property verified in Google Search Console for both root and `www` versions, both `http` and `https`
- [ ] Sitemap submitted; coverage report shows >95% indexed
- [ ] No manual actions in Security & Manual Actions section
- [ ] Top 10 queries pulled monthly; map to existing pages or content gaps
- [ ] GA4 property installed; Conversions tracking the right events (newsletter-signup, contact-form-submit, demo-booking, etc.)
- [ ] PageSpeed Insights passes Core Web Vitals on >75% of measured visits

## Per-post Substack optimization

For every Substack post draft before publish, run this checklist:

- [ ] Title 50-60 chars; primary keyword in the first 50 chars; specific not generic
- [ ] Subtitle 100-150 chars; benefit-led, expands the title
- [ ] First paragraph hooks AND contains a verifiable specific fact (date, named entity, number)
- [ ] Slug is short, hyphen-separated, lowercase, includes the keyword (Substack auto-generates from title; check + edit if needed)
- [ ] Cover image set; aspect ratio appropriate for social cards (1.91:1 or 1:1 depending on platform)
- [ ] At least 2 internal links to other Substack posts on adjacent topics
- [ ] At least 1 outbound link to a primary source where you make a non-trivial claim
- [ ] Tags set (Substack uses these for discovery; max 5, specific over generic)
- [ ] Custom social card image and description set under post settings
- [ ] CTA at the end (subscribe, share, restack) — pick ONE
- [ ] Cross-post link to the EN or ES sibling post if running bilingual

## Output format

Audit reports always print:
```
## SEO + GEO audit: <url>
- Surface type: <substack-post | consulting-page | landing | bilingual-pair>
- Audit date: <ISO>

### Quick fixes (under 1 hour, prioritized by impact)
1. <specific fix> — selector: <css-or-line>
2. ...

### Deep fixes (over 1 hour, may need code changes)
1. <specific fix> — touches: <file-or-system>
2. ...

### Pass/fail per capability
- Technical SEO: <pass | partial | fail> + 1-line reason
- On-page: <pass | partial | fail>
- Schema: <pass | partial | fail>
- GEO: <pass | partial | fail>
- Bilingual: <pass | partial | fail | n/a>
- Substack post (if applicable): <pass | partial | fail>

### Next step
<single concrete action the user takes after reading this report>
```

## Source

Cherry-pick from [AgriciDaniel/claude-seo](https://github.com/AgriciDaniel/claude-seo) (MIT, 6,276 stars). Their bundle is comprehensive but heavy for solo-operator surfaces; this substrate keeps the surface coverage at 80% and trims the depth at the long tail. Specific extensions skipped from upstream:

- `seo-dataforseo` (paid API — out)
- `seo-firecrawl` (paid API — out, we have own scraping path)
- `seo-image-gen` (image generation — covered by `nano-banana` in our stack)
- `seo-flow` (FLOW framework integration — out, not used)
- `seo-ecommerce` (multi-SKU shop — out for solo operators)
- `seo-cluster` (semantic topic clustering at scale — out, manual is sufficient under 200 pages)

Per `⚙️ Meta/rules/repo-evaluation.md` cherry-pick rule: extract the substrate primitives at our quality bar, credit upstream, do not install the whole bundle.
