# Product Requirements Document

## LinkedIn Carousel Generator — Internal Tool

| Field | Value |
|---|---|
| **Owner** | End to End Ecommerce Pvt Ltd |
| **Audience** | Internal content team (founder + writers) |
| **Status** | Draft v0.2 |
| **Date** | May 30, 2026 |
| **Revision** | v0.2 incorporates LinkedIn carousel best practices: portrait as default format, slide count widened to 6–12, 15% mobile safe zones, RGB color profile, max-quality PDF export (compression-resistant). |

---

## 1. Background

The content team publishes ~1 LinkedIn carousel per day on SEO, e-commerce, and marketing topics. The current process is manual: a writer reads source articles, drafts copy, hands it off for design, and iterates over multiple rounds. Two problems show up consistently:

1. **Factual drift.** Drafts often editorialize beyond what the sources actually say (e.g., framing a niche feature as a major industry shift). This was the central flaw in the carousel we evaluated in the working session that led to this PRD.
2. **AI texture.** When writers use LLMs to speed up drafting, the output carries AI cadence — generic hooks, engagement bait, hollow vocabulary — that performs poorly on LinkedIn and erodes brand voice over time.

The tool's job is to compress the workflow from hours to ~15 minutes while *raising* output quality on both dimensions.

---

## 2. Goals

- **Faithful to source.** No claim in the final carousel should go beyond what the supplied source content supports.
- **Humanized voice.** Output passes Humanizer rules: no AI vocabulary, no engagement bait, no template hooks, varied sentence rhythm.
- **Visually consistent.** Output matches one of our locked design systems pixel-for-pixel.
- **LinkedIn-ready.** Final export is a PDF in either 1080×1080 or 1080×1350, ready to upload as a LinkedIn document post.
- **Fast enough for daily use.** Full generation (brief → reviewed PDF) should take under 15 minutes including human review.

## 3. Non-goals

- Multi-tenant SaaS, accounts, billing, team management
- Multi-platform export (Instagram, Twitter/X, TikTok carousels)
- AI image generation inside slides
- Analytics, A/B testing, post scheduling
- Public-facing tool for clients

---

## 4. Users

Two roles, one tool. Same UI for both — role separation happens in usage patterns, not in the product.

- **Writer.** Drafts the brief, reviews and edits the outline, exports the final PDF. Uses the tool daily.
- **Reviewer (founder).** May spot-check generated outlines before render, or pick up writer's draft for final tweaks. Uses the tool 1–2x per week for oversight.

---

## 5. User flow

Three screens, linear flow with backtracking allowed.

```
[Screen 1: Brief]  →  [Screen 2: Outline review]  →  [Screen 3: Render & export]
       ↑                       ↓                              ↓
       └───────── edit brief ──┘                       regenerate slide N
```

### Screen 1 — Brief

Single page, all fields visible. No wizard.

**Fields:**

| Field | Type | Required | Notes |
|---|---|---|---|
| Topic / working title | Single line | Yes | The post's core idea in plain English |
| Source content blocks | 3–5 textareas | At least 1 | Paste excerpts from articles; not full pages |
| Source URLs | 3–5 single lines | Optional | Used for citation footer only; never fetched |
| Audience | Dropdown | Yes | SEO pros / founders / content marketers / e-commerce ops / general business |
| Angle | Single line | Yes | The take you want — e.g., "warn brands not to overreact" |
| Writer draft | Textarea | Optional | If writer already drafted LinkedIn copy or notes, paste here |
| Design system | Radio buttons | Yes | Primary highlighted; secondary visible; tertiary in "More options" reveal |
| Output format | Radio buttons | Yes | 1080×1080 (square) or **1080×1350 (portrait, default)**. Portrait is pre-selected because it claims more vertical screen space on mobile, where most LinkedIn traffic happens. |

**One action button:** "Generate outline."

### Screen 2 — Outline review

The most important screen. Shows three blocks:

**Block A — Facts ledger.** A list of every distinct claim the LLM extracted from the source content blocks, with attribution to which source it came from. If two sources contradict each other or contradict the writer's draft, the conflict is flagged inline ("Source 2 says X, draft says Y — which is correct?").

**Block B — Slide outline.** 6–9 proposed slides (count adapts to content — see section 7). Each slide row shows:
- Slide number and job (cover, definition, mechanics, nuance, stat, list, checklist, closing, etc.)
- Headline (max 12 words)
- Body copy (1–3 sentences)
- Any stat or quote embedded in the slide
- Inline edit button per slide
- "Regenerate this slide" button per slide

**Block C — Humanizer flags.** Any AI texture detected in the proposed copy, listed with the exact phrase and a suggested rewrite. Writer can apply or dismiss each flag individually.

**Actions on this screen:**
- Edit any slide's outline directly
- Regenerate any single slide with a tweak instruction
- Send the whole outline back to Screen 1 with notes
- Approve outline → proceed to render

### Screen 3 — Render & export

Renders the approved outline against the selected design system template at the selected format.

**Actions:**
- View live carousel (in-browser, navigable like the prototype)
- Regenerate any single slide's copy without touching the rest
- Edit slide copy directly (in-place text edit, no LLM call)
- Export to PDF

PDF download is a single button. File is named `[topic-slug]-[date].pdf`.

---

## 6. Inputs and outputs by stage

### Stage 1: Brief → Outline (one LLM call)

**Input:**
- Topic
- Source excerpts (1–5 blocks)
- Audience (enum)
- Angle (free text)
- Writer draft (optional)

**Output:**
- Facts ledger: list of claims, each with source attribution
- Slide outline: 6–9 slides, each with job, headline, body, optional stat
- Humanizer flags: list of phrases to revise

### Stage 2: Outline → Final copy (per-slide LLM calls, parallelizable)

**Input per slide:**
- Slide job + headline + body draft
- Design system constraints (max chars per field, tone notes)
- Humanizer rules
- Brand voice notes (E2E Ecommerce house voice)

**Output:**
- Final humanized headline + body for that slide

### Stage 3: Final copy + design system + format → HTML

Deterministic. No LLM call. Renders against pre-compiled HTML template (see section 8).

### Stage 4: HTML → PDF

Headless Chrome via Playwright. CSS `@page` size matches chosen format. Each slide becomes one PDF page.

---

## 7. Slide structure and adaptive count

Carousel length adapts to content density. The LLM is instructed to use exactly as many slides as the source material supports — no filler.

**Slide jobs (template-agnostic):**

| Job | Purpose | Typical position |
|---|---|---|
| Cover | Hook + topic | Slide 1 |
| Definition | "What is X" | Slide 2 |
| Mechanics | "How it works" | Slide 3 |
| Nuance / fact-check | Correct a common misframing | Mid-deck |
| Stat | One key number with context | Mid-deck |
| Who benefits | Audience scoping | Mid-deck |
| Action / checklist | What to do now | Late |
| Closing | Bottom line + citation + brand | Last |

**Adaptive rules:**
- Minimum 6 slides (cover + 4 content + closing)
- Maximum 12 slides (aligned with top-performing LinkedIn carousel range; LinkedIn's hard limit is 300 pages but engagement drops sharply beyond ~15)
- If sources don't support a stat slide, drop it — never invent
- If sources don't support a nuance slide, drop it — don't manufacture controversy
- Closing slide is always present and always includes source URLs from Screen 1

---

## 8. Design system handling

**Approach: pre-compiled HTML templates (Option A from brainstorm).**

Each design.md gets translated once into a parameterized HTML template. The template accepts a JSON payload (slide-by-slide content) and produces the rendered HTML.

**Template responsibilities:**
- Accept variable slide count (6–12)
- Accept variable slide jobs and route each to the right layout (cover layout, list layout, stat layout, etc.)
- Support both 1080×1080 and 1080×1350 via CSS variable swap
- Encode all design system tokens (palette, fonts, spacing, shape language)
- **Enforce 15% mobile safe zones.** All critical text, numbers, logos, and CTAs must sit within the inner 70% of the slide (15% padding on every edge). Decorative elements (background patterns, geometric accents, oversized typography used as visual texture) can extend into the safe zone, but nothing the reader needs to *read* should. This protects against mobile cropping in LinkedIn's feed preview.

**Initial scope:**
- **Primary system 1**: warm editorial (rust/sand/ink palette — the one we built together)
- **Primary system 2**: TBD (you mentioned uploading more design.mds)
- **Tertiary systems**: 1–3 additional, behind a "More options" reveal

**Template maintenance rule:** changes to a design.md require a template update. This is intentional friction — it keeps brand voice stable.

---

## 9. Output format specifications

### Aspect ratios

| Format | Dimensions | Use case |
|---|---|---|
| Portrait (default) | 1080×1350 | Recommended for most posts; claims more vertical mobile screen space, which correlates with higher dwell time |
| Square | 1080×1080 | Use when content is naturally tight or when a square composition serves the design better |

The format selection is per-post, not per-design-system. Each design template must support both. Portrait is pre-selected on Screen 1.

### PDF export

- One slide per PDF page
- Page size matches selected format (exact pixel dimensions, no margins)
- Fonts embedded
- Text remains text (not rasterized) for accessibility and crispness
- **Render at 1× device pixel ratio.** No downsampling, no upscaling. The HTML is laid out at the target pixel dimensions and captured at the same scale.
- **RGB color profile only.** Never CMYK — LinkedIn renders on screens, and CMYK output causes color shifts. Playwright defaults to RGB; this is documented here to prevent future drift.
- **Highest quality export preset.** LinkedIn compresses uploaded PDFs to speed up feed loading, which degrades quality. Defense: export at maximum quality with no image compression. Our PDFs are small enough (well under 1 MB) that file-size optimization is unnecessary.
- Filename: `[topic-slug]-[YYYY-MM-DD].pdf`

LinkedIn requirement: PDF documents up to 100 MB, up to 300 pages. Our 8-page 1080×1350 PDFs will be well under 1 MB.

---

## 10. Architecture overview

**Stack (recommended):**
- Frontend: simple server-rendered HTML + minimal JS (no SPA framework needed for internal tool)
- Backend: Python (FastAPI) — handles the 3 screens, talks to Claude API, runs Playwright for PDF export
- LLM: Claude API directly
- Storage: filesystem for now — each generation gets a folder with brief.json, outline.json, slides.json, output.html, output.pdf
- Hosting: TBD (see open questions)

**Why this stack:**
- Internal tool, no scale concerns
- Server-rendered HTML is faster to build and debug than a React app
- Filesystem storage is enough for ~365 generations/year; revisit if archive needs grow
- Playwright runs anywhere

---

## 11. Humanizer integration

The Humanizer rules from `the-humanizer.md` are applied at two points:

1. **During outline generation** (Stage 1). The system prompt instructs the LLM to avoid AI vocabulary, engagement bait, and template structures from the start. Flagged phrases appear in Block C of Screen 2.

2. **During final copy generation** (Stage 2). Per-slide rewrite enforces channel-specific LinkedIn rules: no one-line-per-paragraph formatting, no arrow chains, no "Here's what nobody tells you...", no engagement bait closers.

**Voice profile:** E2E Ecommerce house voice. Calibrated once via writing samples (3–5 paragraphs from past posts that "sound like us"), stored alongside the design templates. The voice profile is shared across all generations.

---

## 12. Out of scope (v1)

Explicit list of things this tool does NOT do:

- URL fetching of source articles
- Image generation
- Logo or brand kit upload (E2E is hard-coded)
- Versioning or revision history beyond filesystem snapshots
- Multi-user collaboration in real time
- Comment threads on outlines or slides
- Publishing directly to LinkedIn via API
- Analytics on which posts performed well
- Mobile UI optimization (assumed desktop use by internal team)
- Authentication or access control

---

## 13. Phasing

**v0.1 — Single happy path (target: week 1)**
- All 3 screens functional
- One design system (warm editorial)
- One format option (1080×1080)
- PDF export working
- No per-slide regeneration; full-deck regen only
- Manual review of 3–5 generations to validate the outline-approval flow

**v0.2 — Daily-use ready (target: week 2–3)**
- Add second design system
- Add 1080×1350 format support
- Per-slide regeneration on Screen 3
- Humanizer flags surfaced on Screen 2
- Inline outline edits

**v0.3 — Maturity (target: as needed)**
- Additional design systems (3rd, 4th, 5th)
- Writer draft import path improved (smarter extraction when writer pastes a full LinkedIn post)
- Light templates for common post types (trend explainer, fact-check, tactical guide)
- Generation history view

---

## 14. Open decisions

Before v0.1 build can start, three things need to be locked:

1. **Hosting.** Local FastAPI app run from a laptop, or deployed to a cheap VM (Render, Fly.io, ~$5–10/month)? Local is simpler; deployed means writers don't need to set anything up.

2. **Additional design.md uploads.** When will systems 2–5 be available? v0.1 only needs one; v0.2 needs at least two. Shape of v0.2 templates depends on how similar/different the systems are.

3. **Voice profile capture.** Should the voice profile be a static file you write once, or should the tool collect it via a one-time onboarding flow? Static file is simpler and probably correct.

---

## 15. Success criteria

Internal tool, so the metrics are qualitative:

- Writers prefer the tool over the manual process within 2 weeks of v0.2
- Output quality at parity with or better than current manual carousels (judged by founder review)
- Zero factual errors in the first 20 published posts using the tool (no claims unsupported by sources)
- Generation time from brief to approved PDF averages under 15 minutes including human review

If these hold, the tool stays. If not, we kill it.

---

## 16. Risks and mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| LLM hallucinates beyond source content | Medium | Fact-checking step on Screen 2 catches before render; system prompt is strict |
| Design templates drift from design.md over time | Medium | Templates are version-controlled; design.md changes are explicit |
| Writers bypass Screen 2 review and ship bad outlines | Low | Screen 2 is mandatory; can't skip to render |
| PDF rendering inconsistent across runs | Low | Playwright + locked Chrome version + embedded fonts |
| Voice profile becomes generic over time | Medium | Quarterly review of voice samples; refresh from latest best-performing posts |

---

## Appendix A: Reference materials

- `design.md` (warm editorial system — built in working session)
- `the-humanizer.md` (v2.4 — AI pattern detection rules)
- Sample output: `google-preferred-sources-carousel.html`
- Source case study: Google Preferred Sources LinkedIn carousel evaluation (May 2026)
- LinkedIn carousel best practices: PostNitro guide (Jan 2026) — source for safe zones, format defaults, slide count range, and compression handling in v0.2