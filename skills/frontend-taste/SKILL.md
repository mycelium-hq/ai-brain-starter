---
name: frontend-taste
description: Anti-slop tactical layer for React / Next.js / Tailwind / Framer Motion frontend work. Pairs with the impeccable skill (strategic layer / register laws). Use when building or auditing UI, working on hero sections, landing pages, dashboards, components, or any frontend surface that an AI agent is generating. Carries the Dial System, the Frequency Gate, the Jane-Doe anti-slop content rules, hero discipline, Bento 2.0 motion-engine archetypes, Double-Bezel nested architecture, image-first workflow, shadow + surface recipes, a ~50-item redesign audit checklist, minimalist warm-monochrome variant, stack-specific gotchas, and anti-truncation output discipline.
license: MIT
sources:
  - Leonxlnx/taste-skill (MIT) — Dial System, Jane-Doe rules, hero discipline, Bento 2.0, Variance Engine, redesign audit checklist, minimalist variant, anti-truncation discipline
  - pbakaus/impeccable (Apache 2.0) — Register split (brand vs product), 17-font reflex-reject, aesthetic-lane reflex-reject, three-voice-words exercise, absolute bans; load impeccable for the strategic layer
  - kylezantos/design-motion-principles (MIT) — Frequency Gate, Golden Rule, duration-by-context, motion cookbook (enter recipe with blur, exit subtler than enter, easing-by-context, accessibility)
  - jshmllr/tokyn (Other) — Shadow-as-border with negative spread, natural shadow stacks, concentric border radius, macOS-style micro-shadow buttons, glass/frosted recipes, folded panel, saturated brand-tinted shadows, color strip accents
---

# Frontend Taste Engine

Anti-slop tactical layer. Sits on top of the impeccable substrate (strategy + register laws + shared design absolute bans). Adds the prescriptive recipe layer impeccable leaves under-specified.

## 1. How this layers

| Layer | Source | What it carries |
|---|---|---|
| Strategy | `impeccable` skill (Apache 2.0) | Register split (brand vs product), color strategy (Restrained / Committed / Full palette / Drenched), theme physical-scene test, 17-font reflex-reject, aesthetic-lane reflex-reject, shared absolute bans |
| Motion philosophy | `design-motion-principles` skill (MIT) | Three-designer lens (Emil / Jakub / Jhey), Frequency Gate, Golden Rule, duration-by-context, accessibility (`prefers-reduced-motion`) |
| Tactics (this skill) | This file | Dial System, Variance Engine archetype lock-in, Jane-Doe content rules, hero discipline, Bento 2.0 motion engine, Double-Bezel nested architecture, image-first workflow, shadow/surface recipes, ~50-item redesign audit checklist, minimalist variant, anti-truncation discipline |

Do not duplicate impeccable's content. Reference impeccable's `brand.md` and `product.md` for the register-specific laws.

## 2. The Dial System

Three globals at the top of any frontend-taste prompt. Default 8 / 6 / 4. Tunable per-request.

```
DESIGN_VARIANCE: 8       // 1=symmetric, 10=asymmetric/chaotic
MOTION_INTENSITY: 6      // 1=static, 10=cinematic/physics
VISUAL_DENSITY: 4        // 1=art-gallery, 10=pilot-cockpit
```

Mobile override (DESIGN_VARIANCE 4-10): asymmetric layouts above `md:` MUST collapse to `w-full px-4 py-8` single-column on `<768px`.

Register-default presets:

| Register | Variance | Motion | Density |
|---|---|---|---|
| Brand (marketing / landing / campaign) | 7-9 | 6-8 | 3-5 |
| Product UI (dashboard / admin / app) | 3-5 | 3-5 | 5-7 |
| Editorial / long-form | 6-8 | 4-6 | 4-6 |
| Data dashboard / cockpit | 4-6 | 2-4 | 7-10 |

## 3. Register split (read impeccable first)

The single biggest gain from impeccable is the register split. Brand vs product are different beasts.

### BRAND register (design IS the product)
Marketing pages, landing pages, campaign pages, portfolios, long-form content. Distinctiveness is the bar; AI-flooded average reads as mediocre.

- **Typography:** reject the 17-font training-data ban list. Cross-check the aesthetic-lane reject (editorial-typographic Klim-style). Use the three-voice-words exercise. Read impeccable's `brand.md` for the full list.
- **Color:** Restrained is the floor, but brand has permission for Committed / Full palette / Drenched. Name a real reference before picking strategy.
- **Layout:** asymmetric, or rigorously gridded as voice. The failure mode is splitting the difference into a generic centered stack.
- **Imagery:** zero images is a bug on imagery-implied briefs (restaurants, hotels, food, travel, fashion, photography). Tech/dev brands are the exception. Use Unsplash for greenfield brand work with the URL shape `https://images.unsplash.com/photo-{id}?auto=format&fit=crop&w=1600&q=80` — search for the brand's physical object, not the generic category.
- **Motion:** ambitious first-load orchestration permitted when the brand invites it.

### PRODUCT register (design SERVES the product)
App UIs, dashboards, admin, settings, data tables, tools, authenticated screens. Earned familiarity is the bar.

- **Typography:** system fonts are legitimate (`-apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif`). Inter IS permitted here. One family is often right. Fixed rem scale, NOT fluid `clamp()`. Tighter ratio (1.125-1.2) between steps.
- **Color:** Restrained is the floor. Accent for primary actions + current selection + state indicators only. State-rich semantic vocabulary required.
- **Layout:** predictable grids. Standard navigation patterns are features.
- **Imagery:** placeholder via `https://picsum.photos/seed/{random}/800/600` when needed. Real product screenshots > photo decoration.
- **Motion:** 150-250ms on most transitions. Motion conveys state, not decoration. No orchestrated page-load sequences.
- **Components:** every interactive component ships default + hover + focus + active + disabled + loading + error.

## 4. The Variance Engine (archetype lock-in)

Before writing code, silently pick ONE combo and commit:

**Vibe Archetype (pick 1):** Ethereal Glass · Editorial Luxury · Soft Structuralism · Pristine Minimalism · Bold Studio Solid · Drenched

**Layout Archetype (pick 1):** Asymmetrical Bento · Z-Axis Cascade · Editorial Split · Cinematic Centered Minimalist · Floating Polaroid Scatter · Swiss Grid Discipline

**Signature Components (pick exactly 4):** diagonal staggered masonry · 3D cascading card deck · hover-accordion slice · gapless bento grid · infinite brand marquee · turning polaroid arc · vertical rhythm lines · off-grid editorial layout · product UI panel stack · split testimonial wall · layered image crop frames · Bento 2.0 motion engine

**Motion Language (pick exactly 2):** scrubbing text reveal · pinned narrative · staggered float-up · parallax image drift · smooth accordion expansion · cinematic fade-through

## 5. The Frequency Gate (motion decision)

| Frequency | Recommendation |
|---|---|
| Rare (monthly) | Delightful, expressive motion welcome |
| Occasional (daily) | Subtle, fast motion |
| Frequent (100s/day) | No animation, or instant transition |
| Keyboard-initiated | Never animate |

**Golden Rule:** "The best animation is that which goes unnoticed." If users comment "nice animation!" on every interaction, it's too prominent for production.

**Accessibility is NOT optional:** every animation handles `prefers-reduced-motion`. Wrap motion in `@media (prefers-reduced-motion: no-preference)` or pair Framer Motion's `useReducedMotion()` hook with conditional defaults.

## 6. The Jane-Doe Effect (anti-slop content)

LLMs default to filler. Override every time.

- **Names:** NO "John Doe / Sarah Chan / Jack Su." Realistic contextual names.
- **Companies:** NO "Acme / Nexus / SmartFlow / Lumina / Flowbit / Quantumly / NovaCore." Premium contextual brand names.
- **Numbers:** NO "99.99% / 50% / 100K / 1,234,567." Organic messy data (`47.2%`, `+1 (312) 847-1928`, `1,847 users`).
- **Filler words:** NO "Elevate / Seamless / Unleash / Next-Gen / Empower / Transform / Game-changer / Delve / Tapestry / In the world of."
- **Avatars:** NO standard SVG "egg" or Lucide user icons.
- **Pseudo-system labels:** NO "00 orchestration layer," "QUESTION 05," "SECTION 04," fake operator/runtime/orchestration jargon.
- **Lorem Ipsum:** banned.
- **Title Case On Every Header:** banned. Sentence case.

## 7. Hero discipline (brand register)

- Headline line count: 1-3 lines. 4+ = catastrophic.
- Headline size: `clamp(3rem, 5vw, 5.5rem)` for brand.
- Hero layout (pick 1): Cinematic Centered · Artistic Asymmetry · Editorial Split.
- Button contrast: dark bg = white text, light bg = dark text.
- Banned in hero: floating stamp/badge icons · pill-tags · raw data/stats · "Scroll to explore" / bouncing chevrons · multiple competing focal points · pseudo-system labels.
- `min-h-[100dvh]` not `h-screen` (iOS Safari viewport-jump).

## 8. Bento 2.0 motion-engine archetypes

White cards on `#f9fafb`, `rounded-[2.5rem]`, 1px `border-slate-200/50`, diffusion shadow `shadow-[0_20px_40px_-15px_rgba(0,0,0,0.05)]`, `p-8`-`p-10` padding, titles + descriptions OUTSIDE the cards.

Spring physics: `type: "spring", stiffness: 100, damping: 20`. No linear easing in Bento. Wrap dynamic lists in `<AnimatePresence>`. Memoize all perpetual animations and isolate each in its own microscopic Client Component.

Five card archetypes:
1. **Intelligent List** — vertical stack with infinite auto-sorting via `layoutId`.
2. **Command Input** — multi-step typewriter cycling through prompts.
3. **Live Status** — breathing status indicators + overshoot-spring notification badge.
4. **Wide Data Stream** — horizontal infinite carousel `x: ["0%", "-100%"]`.
5. **Contextual UI (Focus Mode)** — staggered text-block highlight + float-in toolbar.

## 9. Motion cookbook (recipes)

### Enter animation recipe
The "materializing" effect — opacity + translateY + blur.

```jsx
initial={{ opacity: 0, translateY: "calc(-100% - 4px)", filter: "blur(4px)" }}
animate={{ opacity: 1, translateY: 0, filter: "blur(0px)" }}
transition={{ type: "spring", duration: 0.45, bounce: 0 }}
```

For non-container reveals: opacity 0→1, translateY ~8px→0, blur 4px→0px.

### Exit subtler than enter

```jsx
exit={{ translateY: "-12px", opacity: 0, filter: "blur(4px)" }}
```

Exception: user-initiated dismissal, error clearing, item deletion, page transitions with directional continuity.

### Easing by context

| Easing | Good for |
|---|---|
| `ease-out` | Entering view |
| `ease-in` | Leaving view |
| `ease-in-out` | Changing state while visible |
| `linear` | Continuous loops, progress indicators |
| `spring` (bounce: 0) | Interactive elements, professional UI |
| `spring` (bounce > 0) | Playful contexts only |

Context rule: "You wouldn't use 'Elastic' for a bank's website, but it might work for a children's site."

Custom Bézier > built-in CSS easing. `ease` and `ease-in-out` lack strength.

### Duration by context

| Context | Guideline |
|---|---|
| Product UI | Under 300ms — 180ms ideal |
| Production polish | 200-500ms |
| Brand / creative / kids | Whatever serves the effect |

### Stagger
`animation-delay` only applies once. Use:
1. Different delays with finite iterations
2. Pad keyframes within the animation (`0%, 50% { rotate: 0; } 100% { rotate: 360deg; }`)
3. CSS cascade via custom-property index (`animation-delay: calc(var(--index) * 80ms)`)

### Fill mode
Use `animation-fill-mode: backwards` to prevent flash-at-full-opacity-before-delayed-fade-in.

## 10. Shadow + surface recipes

### Shadow-as-border with negative spread

```css
.card {
  background: #ffffff;
  border-radius: 0.75rem;
  background-clip: padding-box;
  box-shadow:
    0 0 0 1px rgba(15, 23, 42, 0.08),
    0 1px 1px -1px rgba(15, 23, 42, 0.10),
    0 3px 6px -3px rgba(15, 23, 42, 0.15);
}
```

### Natural shadow stacks

```css
.elevated {
  --shadow-color: rgb(0 0 0 / 0.06);
  box-shadow:
    0 0 0 1px var(--shadow-color),
    0 1px 1px -0.5px var(--shadow-color),
    0 3px 3px -1.5px var(--shadow-color),
    0 6px 6px -3px var(--shadow-color),
    0 12px 12px -6px var(--shadow-color),
    0 24px 24px -12px var(--shadow-color);
}
```

### Inner highlights for dark containers

```css
.dark-card {
  background: #020617;
  border-radius: 1rem;
  box-shadow:
    inset 0 0 0 1px rgba(255, 255, 255, 0.05),
    0 12px 40px rgba(0, 0, 0, 0.75);
}
```

### Concentric border radius
Outer 12px + padding 2px → inner 10px.

```css
.outer { border-radius: 12px; padding: 2px; }
.inner { border-radius: 10px; }
```

### macOS-style micro-shadow buttons

```css
button.mac {
  all: unset;
  font: 13px -apple-system, BlinkMacSystemFont, system-ui, sans-serif;
  color: #262626;
  background: #ffffff;
  border-radius: 5px;
  height: 20px;
  padding: 0 10px;
  box-shadow:
    0 0 0 0.5px rgba(0, 0, 0, 0.076),
    0 0.5px 0 rgba(0, 0, 0, 0.035),
    0 -1px 1px 0.3px rgba(0, 0, 0, 0.0255),
    0 1px 1px rgba(0, 0, 0, 0.01),
    -1px 1px 1px 0.3px rgba(0, 0, 0, 0.05),
    1px 1px 1px 0.3px rgba(0, 0, 0, 0.05);
}
```

### Glass / frosted panels

```css
.glass {
  background: rgba(15, 23, 42, 0.35);
  border: 1px solid rgba(255, 255, 255, 0.18);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  box-shadow: 0 18px 45px rgba(15, 23, 42, 0.6);
}
```

`backdrop-filter` ONLY on fixed/sticky elements.

### Folded panel

```css
.folded {
  border-radius: 1.25rem;
  background: linear-gradient(135deg, #020617, #0f172a);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.16),
    inset 0 -1px 0 rgba(15, 23, 42, 0.9),
    0 18px 50px rgba(0, 0, 0, 0.7);
}
```

### Saturated brand-tinted shadows

```css
.button-primary {
  background: #2563eb;
  box-shadow: 0 10px 20px rgba(37, 99, 235, 0.35);
}
```

### Color strip accents

```css
.card-accent::before {
  content: "";
  position: absolute;
  inset: 0;
  height: 6px;
  background: linear-gradient(to right, #06b6d4, #6366f1);
}
```

## 11. Double-Bezel (Doppelrand) nested architecture

Never place a premium card flatly. Nest enclosures for machined-hardware feel.

- **Outer shell:** subtle bg (`bg-black/5`), hairline border (`ring-1 ring-black/5`), padding (`p-1.5`-`p-2`), large outer radius (`rounded-[2rem]`).
- **Inner core:** distinct bg, inner highlight (`shadow-[inset_0_1px_1px_rgba(255,255,255,0.15)]`), concentric radius (`rounded-[calc(2rem-0.375rem)]`).
- **Nested CTA:** trailing arrow in own circular wrapper.
- **Magnetic button physics:** `active:scale-[0.98]` on press; nested icon `group-hover:translate-x-1 group-hover:-translate-y-[1px]` and scale `1.05`. NEVER `useState` — Framer Motion `useMotionValue` + `useTransform`.

## 12. Image-first workflow

When the task is visual website work and image generation is available:
1. Generate the design image(s) first.
2. One section = one image. Don't compress into a giant collage.
3. Regenerate as fresh standalone image if unclear; never crop from a previous larger image.
4. Deeply analyze: headline wording, type-scale relationships, spacing, button shape + radius + hierarchy, color palette, background treatment, icon mood, grid logic.
5. Implement faithfully. Don't drift to generic coded layout.
6. Multi-image consistency: same brand world across all generated images.

## 13. The Redesign Audit Checklist

Run against any frontend surface to surface every generic AI pattern in one pass.

### Typography
- [ ] Inter everywhere in BRAND register → swap to non-banned font. (Product register: Inter fine.)
- [ ] Headlines lack presence → increase size, tighten letter-spacing, reduce line-height.
- [ ] Body text too wide → cap at ~65 characters.
- [ ] Only Regular (400) and Bold (700) weights → introduce Medium (500) and SemiBold (600).
- [ ] Numbers in proportional font → monospace or `font-variant-numeric: tabular-nums`.
- [ ] All-caps subheaders everywhere → lowercase italics / sentence case / small-caps.
- [ ] Orphaned single words on last line → `text-wrap: balance`.

### Color and surfaces
- [ ] Pure `#000000` background → off-black / charcoal / tinted dark.
- [ ] Oversaturated accents (>80% saturation) → desaturate.
- [ ] More than one accent color → pick one.
- [ ] Mixing warm and cool grays → one family.
- [ ] Purple/blue "AI gradient" → neutral + single considered accent.
- [ ] Generic black `box-shadow` → tint to background hue.
- [ ] Empty flat sections → background imagery / subtle patterns / ambient gradients.

### Layout
- [ ] Everything centered and symmetrical → offset margins / mixed aspect ratios / left-aligned.
- [ ] Three equal card columns as feature row → 2-column zig-zag / asymmetric grid / horizontal scroll / masonry.
- [ ] `height: 100vh` → `min-height: 100dvh` (iOS Safari).
- [ ] Complex flexbox percentage math → CSS Grid.
- [ ] No max-width container → ~1200-1440px with auto margins.
- [ ] Cards forced to equal height by flexbox → variable heights or masonry.
- [ ] Uniform border-radius everywhere → vary.
- [ ] Missing whitespace → double the spacing.
- [ ] Buttons not bottom-aligned in card groups → pin to bottom.

### Interactivity and states
- [ ] No hover states → add bg shift / scale / translate.
- [ ] No active/pressed feedback → `scale(0.98)` or `translateY(1px)`.
- [ ] Instant transitions → 150-300ms (Frequency Gate).
- [ ] Missing focus ring → visible keyboard-nav indicator.
- [ ] Generic circular spinner → skeleton loader matching layout.
- [ ] No empty state → composed "getting started" view.
- [ ] No error state → clear inline messages; never `window.alert()`.
- [ ] Dead links (`href="#"`) → link real or visually disable.
- [ ] Anchor clicks jump instantly → `scroll-behavior: smooth`.
- [ ] Animating `top` / `left` / `width` / `height` → `transform` and `opacity` only.
- [ ] Animations without `prefers-reduced-motion` handling → wrap all motion.

### Content
- [ ] Generic names ("John Doe") → diverse realistic.
- [ ] Fake round numbers (`99.99%`) → organic messy.
- [ ] Placeholder companies ("Acme") → contextual believable.
- [ ] AI copy clichés → plain specific.
- [ ] Exclamation marks in success messages → remove.
- [ ] "Oops!" error messages → direct.
- [ ] Lorem Ipsum → real draft copy.
- [ ] Title Case On Every Header → sentence case.

### Component patterns
- [ ] Generic card (border + shadow + white) → remove or repurpose.
- [ ] One filled + one ghost button always → add text links / tertiary.
- [ ] 3-card carousel testimonials with dots → masonry wall / single quote.
- [ ] Modals for everything → inline / slide-over / expandable.

### Iconography
- [ ] Lucide / Feather exclusively → Phosphor / Heroicons / Radix / custom.
- [ ] Inconsistent stroke widths → standardize.
- [ ] Missing favicon → always include.

### Code quality
- [ ] Div soup → semantic HTML.
- [ ] Hardcoded pixel widths → relative units.
- [ ] Missing alt text → describe content.
- [ ] Arbitrary z-index (`9999`) → clean z-index scale.
- [ ] Missing meta tags → `<title>`, `description`, `og:image`.

### Strategic omissions
- [ ] No privacy policy / terms of service in footer.
- [ ] No "back" navigation — dead ends.
- [ ] No custom 404 page.
- [ ] No form validation.
- [ ] No "skip to content" link.

### Fix priority
1. Font swap (biggest impact, lowest risk)
2. Color palette cleanup
3. Hover and active states
4. Layout and spacing
5. Replace generic components
6. Add loading / empty / error states
7. Polish typography scale and spacing

## 14. Minimalist warm-monochrome variant

When the brief is editorial / clean / quiet premium:

- Canvas: `#FFFFFF` or warm bone `#F7F6F3` / `#FBFBFA`.
- Cards: exactly `1px solid #EAEAEA`, 8-12px border-radius max, 24-40px internal padding.
- Accents: highly desaturated pastels only (Pale Red `#FDEBEC` text `#9F2F2D`, Pale Blue `#E1F3FE` text `#1F6C9F`, Pale Green `#EDF3EC` text `#346538`, Pale Yellow `#FBF3DB` text `#956400`).
- Body text: never `#000000`. Off-black `#111111` or `#2F3437` with line-height `1.6`.
- Buttons: solid `#111111` with `#FFFFFF` text, 4-6px radius, no shadow.
- Tags: pill, `text-xs`, uppercase wide tracking `0.05em`, muted pastel bg.
- Section padding: `py-24` to `py-32` minimum.

## 15. Stack-specific gotchas

| Symptom | Fix |
|---|---|
| Hero jumps on iOS Safari scroll | NEVER `h-screen`. ALWAYS `min-h-[100dvh]`. |
| `staggerChildren` only fires for first child | Parent + children MUST be in identical Client Component tree. |
| Magnetic hover collapses performance on mobile | Framer Motion `useMotionValue` + `useTransform`, NOT `useState`. |
| Tailwind v4 syntax in v3 project | Check `package.json` first. v4: `@tailwindcss/postcss` or Vite plugin. |
| Layout jumps from animating top/left/width/height | EXCLUSIVELY `transform` + `opacity`. |
| Framer Motion `x`/`y`/`scale` props drop frames under load | These shorthands run on rAF/main thread, NOT the GPU. Use the full string: `animate={{ transform: "translateX(100px)" }}`, not `animate={{ x: 100 }}`. CSS animations stay smooth when the main thread is busy; Framer shorthands don't. |
| Grain/noise filters tank scroll FPS | Filters EXCLUSIVELY on fixed `pointer-events-none` overlays. |
| `'use client'` everywhere | Default Server Components. Extract interactive leaves. |
| `backdrop-blur` everywhere kills scroll FPS | ONLY fixed/sticky elements. |
| `window.addEventListener('scroll')` | NEVER. `IntersectionObserver` / `whileInView` / `useScroll`. |
| Mixing GSAP and Framer Motion in same component tree | Don't. Framer Motion for UI/Bento. GSAP for isolated scrolltelling. |
| `prefers-reduced-motion` not handled | Wrap motion in media query or use `useReducedMotion()`. |

## 16. Font + color bans (brand register only)

Product register permits Inter, system fonts, and pragmatic defaults. Brand register applies these bans.

- Inter banned in brand. Use `Geist`, `Outfit`, `Cabinet Grotesk`, or `Satoshi`. Read impeccable's 17-font reflex-reject list for the full ban.
- Editorial-typographic aesthetic lane (Klim-influenced display serif + italic + mono labels) banned in brand unless brief literally requires it.
- Lila banned. Use Emerald / Electric Blue / Deep Rose neutral-base.
- Pure `#000000` banned. Use Off-Black, Zinc-950, or Charcoal.
- Roboto / Open Sans / Helvetica / Arial banned for premium contexts.
- Standard thick-stroke Lucide / FontAwesome / Material Icons banned. Use Phosphor Light / Remix Line / Radix.
- Custom mouse cursors banned (accessibility).
- Text-fill gradients on large headers banned.

## 17. Icons + shadcn

- Exactly `@phosphor-icons/react` OR `@radix-ui/react-icons`. One stroke weight globally.
- `shadcn/ui` fine BUT NEVER default state. Customize radii, colors, shadows.

## 18. Anti-truncation output discipline

When the deliverable is a full implementation, do not ship a skeleton.

**Banned in code:** `// ...`, `// rest of code`, `// implement here`, `// TODO`, `/* ... */`, `// similar to above`, `// continue pattern`, bare `...`.

**Banned in prose:** "Let me know if you want me to continue," "for brevity," "the rest follows the same pattern," "similarly for the remaining," "I'll leave that as an exercise."

If approaching the token limit, write at full quality up to a clean breakpoint and end with:

```
[PAUSED — X of Y complete. Send "continue" to resume from: next section name]
```

## 19. Pre-flight checklist

- [ ] Register identified (brand or product)
- [ ] Variance Engine archetype combo selected
- [ ] Dial values declared
- [ ] Frequency Gate applied per animation
- [ ] `prefers-reduced-motion` handled
- [ ] Mobile collapse guaranteed for high-variance designs
- [ ] Full-height sections use `min-h-[100dvh]`
- [ ] All `useEffect` animations have cleanup
- [ ] Empty + loading + error states (product register)
- [ ] Cards omitted where spacing serves
- [ ] Perpetual animations isolated + memoized
- [ ] Brand: no banned fonts; product: Inter / system fonts fine
- [ ] No banned filler words (Elevate / Seamless / Unleash)
- [ ] No Jane Doe, no Acme, no 99.99%
- [ ] Hero (brand): 1-3 line headline, button contrast legible
- [ ] If Bento 2.0: spring `stiffness: 100, damping: 20`
- [ ] If Double-Bezel: outer shell + inner core, concentric radii
- [ ] `backdrop-blur` only on fixed/sticky
- [ ] No `window.addEventListener('scroll')`
- [ ] No animating `top` / `left` / `width` / `height`
- [ ] No mixing GSAP + Framer Motion in same component tree
- [ ] No `// rest of code` placeholders

## Source comparison

Built by everything-comparison across all comparable sources:

| Source | License | Net-new content used |
|---|---|---|
| [Leonxlnx/taste-skill](https://github.com/Leonxlnx/taste-skill) | MIT | Dial System, Jane-Doe rules, Bento 2.0 archetypes, hero discipline, anti-truncation, archetype lock-in, Variance Engine, redesign audit checklist, minimalist variant, Double-Bezel |
| [pbakaus/impeccable](https://github.com/pbakaus/impeccable) | Apache 2.0 | Register split (brand vs product), color strategy ladder, theme physical-scene test, 17-font reflex-reject, aesthetic-lane reflex-reject, absolute bans |
| [kylezantos/design-motion-principles](https://github.com/kylezantos/design-motion-principles) | MIT | Frequency Gate, Golden Rule, duration-by-context, motion cookbook (enter recipe, exit subtler, easing-by-context, stagger, fill mode), accessibility |
| [jshmllr/tokyn](https://github.com/jshmllr/tokyn) | Other | Shadow-as-border, shadow stacks with negative spread, inner highlights, concentric radius, macOS micro-shadow, glass, folded panel, saturated shadows, color strip accents |

Install all four for the full ecosystem:

```bash
# This skill (frontend-taste) is part of ai-brain-starter
# Strategic layer:
npx skills add pbakaus/impeccable --skill frontend-design

# Motion philosophy:
git clone https://github.com/kylezantos/design-motion-principles ~/.claude/skills/design-motion-principles

# Source bundle (cherry-pick reference):
npx skills add Leonxlnx/taste-skill --skill design-taste-frontend
```

## License

MIT. Source attributions above. This skill is a derivative cherry-pick under MIT (taste-skill) + Apache 2.0 (impeccable) + MIT (design-motion-principles) compatible licensing. Attribution preserved in `sources:` frontmatter.
