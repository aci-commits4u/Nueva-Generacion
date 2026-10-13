# Self-explaining UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Make Intent Judge explain its value and workflow before asking a visitor to operate it.
**Architecture:** Local landing and walkthrough ES modules join the existing static frontend. Existing APIs retain approval and enforcement authority.
**Tech Stack:** FastAPI, vanilla JS, CSS, local Geist Sans, Playwright CLI.
**Spec:** docs/superpowers/specs/2026-10-13-self-explaining-ui.md

## Global Constraints
- FastAPI + static ES modules; no frontend framework/build migration.
- No backend, AI-budget, signature, approval, or exception-rule changes.
- Tutorial uses illustrative synthetic facts and performs no inference or purchasing calls.
- Root overview; explicit intent URLs resume; quality URL loads quality.
- Minimum primary touch targets 44px; visible focus; 390px mobile and 1280px laptop.

## Review Focus
- A returning visitor opens root: overview must appear, without automatically resuming or mutating their existing draft.
- Switching domains after starting a draft: state must reset consistently and tutorial must not imply approval.
- Tutorial final CTA: opens unapproved live-mode intake, without authorizing or booking anything.
- Missing optional fields: visible review remains explicit, never silently defaults to no preference.
- Browser navigation/reload: root, quality, and explicit intent links remain understandable and functional.

### Task 1: Explain and guide
**Files:** web/index.html, web/app.js, web/views/overview.js, web/views/walkthrough.js, web/styles.css, web/fonts/, .stitch/DESIGN.md, scripts/browser_product.js.
**Interfaces:** Consumes existing api(), conversationMarkup(), stage 1–6 renderers. Produces stage 0 overview, stage 7 walkthrough, startDemo(domain), renderWalkthrough(step); existing stages keep identical API payloads.
- [ ] Write browser_product.js: overview heading, all 5 tutorial steps, previous/replay, zero POST requests during tutorial, final CTA opens intake, no horizontal overflow at 390/1280, quality deep link, explicit existing intent resume.
- [ ] Run against current app. Expected: FAIL missing overview heading.
- [ ] Generate and inspect separate hero and walkthrough references; implement modules/navigation/styles faithful to references.
- [ ] Run browser_product.js and existing browser_mobile.js adapted for navigation. Expected: PASS tutorial + real offline approval/check/purchase/evidence flow.
- [ ] Run MOCK_LLM=1 .venv/bin/pytest -q and JS syntax checks. Expected: all tests pass.
- [ ] Commit source, tests, design record.

### Task 2: Review and release
**Files:** docs/16-product-walkthrough.md, DESIGN.md, docs/implementation-status.md, README.md.
**Interfaces:** Consumes Task 1 UI and tests. Produces a reviewed public Vercel deployment on the existing stable alias.
- [ ] Fresh review focuses on consent, misleading tutorial claims, navigation, and responsive/accessibility issues. Correct material findings and verify affected cases.
- [ ] Deploy existing Vercel project; verify public overview, tutorial, explicit offline flow, health, quality, and artifact loading.
- [ ] Update documentation with actual verification and limitations. Commit and push victor/perfected.
Expected: production Ready, browser checks PASS, CI succeeds.
