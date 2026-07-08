# Project Context: LinkedIn Carousel Creator

This document serves as the source of truth for the architecture, progress, recent changes, and future pipeline of the **LinkedIn Carousel Creator** project. Any agent working on this repository should read this file first.

---

## 1. Project Overview & Architecture
The **LinkedIn Carousel Creator** is an internal web application designed for content writers and editors to generate high-converting, factually accurate, and brand-aligned LinkedIn carousels from source materials (articles, transcripts, notes). 

It is built with a lightweight, server-rendered stack:
- **Backend Framework**: FastAPI (Python)
- **Database**: SQLite with SQLAlchemy (for persisting user profiles, brand kits, and carousel states)
- **Templates**: Jinja2 HTML templates
- **Styling**: Pure CSS (no Tailwind, using custom variables for theme options)
- **PDF Generation**: Playwright (headless Chromium) emulating screen media to print high-resolution, multi-page PDFs matching standard aspect ratios (Square 1:1, Portrait 4:5, Portrait 3:4)
- **Deployment**: Deployed as a Dockerized app on Hugging Face Spaces

---

## 2. The Core Workflow
1. **Screen 1 (Brief Creation)**: 
   - User inputs a topic/working title, target audience, angle, and writer draft notes.
   - User pastes source material (separated into blocks) and provides citation URLs.
   - User selects the LLM models (Stage 1 for outline generation, Stage 2 for humanization), design system (E2E Premium, Sage & Charcoal, Teal & Tangerine), and aspect ratio (1080x1440, 1080x1350, 1080x1080).
2. **Screen 2 (Review & Refine Slide Outline)**:
   - **Facts Ledger**: Displays all claims extracted by the Stage 1 model and flags any conflicting statements between sources.
   - **Humanizer Scanner**: Audits initial copy against `the-humanizer-v2.5.md` guidelines, highlighting generic AI patterns with proposed rewrites.
   - **Slide Editor**: Allows manual edits of headlines, bodies, and stats, with per-slide automated LLM regeneration.
3. **Screen 3 (Render & Download)**:
   - Renders slides dynamically in the browser showing mobile-safe zones.
   - Converts the rendered page to a multi-page PDF using a local print route.

---

## 3. What Has Been Done So Far (Completed Work)

### Core Features
- Full end-to-end integration with OpenRouter for outline extraction and copy humanization.
- Support for three design templates (`e2e_premium`, `sage_charcoal`, `teal_tangerine`) and three output formats.
- Persistent SQLite database mapping carousels, brand kits, and profiles.

### Recent Enhancements & Bug Fixes
1. **E2E Logo Render Fix (Runtime Generation)**:
   - **Problem**: The E2E logo was stored as a massive base64 string (~420 KB) in `logo_base64.txt`. Inlining it 15 times inside the template made the HTML 6.3 MB, causing rendering timeouts and blank spaces in the PDF. Hugging Face also rejects commits with raw binary PNG files.
   - **Solution**: We untracked `static/logo.png` from Git and added it to `.gitignore`. On server startup, `main.py` checks if `static/logo.png` exists; if not, it dynamically decodes `logo_base64.txt` and saves it. This keeps the Git history clean of binary files while ensuring the app serves the logo as a fast, cached static URL (`/static/logo.png`).
2. **Playwright Print Settle Timeout**:
   - **Problem**: Playwright printed the PDF immediately on `networkidle`, which occurred before the browser finished rendering fonts and decoding the logo image.
   - **Solution**: Updated `pdf_generator.py` to evaluate image loading (`img.complete`) and add a `1000ms` layout settle delay before executing `page.pdf()`.
3. **Dynamic Kickers and CTAs**:
   - **Problem**: The cover slide kicker (`Query Fan-Out`) and the closing slide CTA (`Want a fan-out audit? DM "FANOUT"`) were hardcoded in the templates.
   - **Solution**: Created two Jinja2 filters (`short_kicker` and `dynamic_cta`) in `main.py` and passed the carousel `topic` to the templates. The Cover slide kicker now reflects the working topic, and the Closing slide CTA dynamically changes (e.g., `"Want an SEO audit? DM 'SEO'"` or `"Want a conversion audit? DM 'AUDIT'"`) depending on keywords in the topic.

---

## 4. Current Pipeline & Future Roadmap

### Short-term Backlog (v0.2 - v0.3 Improvements)
- **Writer Draft Import Path**: Build a smarter extraction algorithm for when a writer pastes a full, pre-written LinkedIn post instead of notes.
- **Common Post Type Templates**: Add structured templates/prompts for specific carousel frameworks (e.g., trend explainer, tactical guide, myth buster).
- **Generation History View**: Build an archive dashboard where users can view, search, and duplicate past carousel generations.
- **Multi-user Authentication**: Upgrade the simple "admin" session cookies to fully secure, multi-user authentication and access control.
- **Mobile UI Polish**: Improve responsiveness of the creator workspace (Screen 1 & 2) for writers accessing the tool via mobile or tablet.

### Future Scale (v1.0+)
- **Direct Publishing**: Integrate with LinkedIn APIs to schedule or publish approved carousels directly from the app.
- **Performance Analytics**: Fetch and display post metrics directly in the history view to understand what templates and styles perform best.
