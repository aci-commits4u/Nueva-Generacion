# Intent Judge — Context Pack

> **Mastercard's Verifiable Intent proves an AI agent was *allowed* to buy. Intent Judge makes sure it bought what the person *meant*.**

This folder is the complete project context for building **Intent Judge** at **LEAD ASPIRE (October 12, 2026, NYC)** — a one-day Microsoft Cloud & AI challenge for client **Mastercard**, hosted by LEAD and HOLA (Hispanic & Latinx at Microsoft), with EY partners reviewing strategy.

Drop the contents of this folder into the root of the GitHub repo. IDE agents (GitHub Copilot, Claude Code, Cursor, etc.) read `AGENTS.md` first; it points to everything else.

## What we are building (one paragraph)

A small web app + backend that sits between an AI shopping agent and payment for **airline bookings**. It (1) uses an Azure AI Foundry model to turn a traveler's request into explicit requirements and ask about anything missing, (2) has the traveler **approve** those requirements, which are stored as a signed constraint inside a Mastercard **Verifiable Intent** (VI) credential, (3) checks the **merchant-signed** flight offer against the approved requirements with **deterministic code** (a rules engine) — any violation or missing data is a **HOLD**, (4) lets the traveler cancel or accept a **specific, recorded exception**, and (5) if a purchase is disputed, assembles a one-page **evidence packet** with a *recommended* responsibility call for a human analyst. **The AI never approves a purchase.**

## Read order

| # | File | Why |
|---|---|---|
| 1 | `AGENTS.md` | Rules for any coding agent working in this repo |
| 2 | `docs/04-solution-design.md` | What the product does, end to end |
| 3 | `docs/05-architecture.md` | Repo layout, components, API, data flow |
| 4 | `docs/07-rules-engine-spec.md` | The core logic (the part that decides) |
| 5 | `docs/06-verifiable-intent-sdk.md` | How to use Mastercard's open-source SDK |
| 6 | `docs/08-foundry-agent.md` | Prompts, JSON schemas, how to call the model |
| 7 | `docs/10-test-plan.md` | 12 scenarios that must pass |
| 8 | `docs/13-build-plan-and-roles.md` | Order of work, owners, checkpoints |

Everything else (event rules, client discovery, research data, pitch, security, decisions, glossary, sources) is in `docs/00-index.md`.

## Team

Jossue (project lead, demo), Victor (lead AI builder), Alex (strategy & business case), Ryan (evidence & standards), Barbara (risk, process & responsible AI).

## Status

- Discover: done (3 Mastercard representatives; chose agent trust)
- Strategize: done — **approved by the EY partner**
- Build: **in progress** ← this repo
- Pitch: 5 min + 2 min Q&A, submit deck + optional demo link
