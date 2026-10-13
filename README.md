# Intent Judge

Intent Judge helps customers turn a natural-language purchasing request into explicit, approved requirements, checks a proposed purchase against those requirements, and records any specific exceptions they accept.

The product builds on Mastercard's open-source Verifiable Intent (VI). VI already supports cryptographic authorization and structured constraint verification. Our proposed contribution is conversational requirement capture, reusable domain profiles, and application-specific enforcement against trustworthy merchant offer data.

**Status: researched documentation and proposed architecture, October 13, 2026. This branch does not yet contain an application.** Upstream SDK research results are recorded separately from future project acceptance tests. No commercial integration, certification, live payment, or measured reduction in chargebacks is claimed.

## Start here

1. [Problem and positioning](docs/01-problem-and-positioning.md): the omission failure and the business value.
2. [Research and contradictions](docs/02-research-and-claims.md): what VI already does and where our assumptions needed correction.
3. [Product workflow](docs/03-product-workflow.md): clarification, approval, checks, exceptions, and evidence.
4. [Architecture](docs/04-architecture.md): reusable core, task profiles, VI adapter, and separate demo commerce.
5. [Domain profiles](docs/05-domain-profiles.md): adapting flights, hotels, and general requests without rewriting the workflow.
6. [VI integration](docs/06-verifiable-intent-integration.md): real SDK responsibilities and custom-constraint composition.

[All documentation](docs/00-index.md) includes the demo, acceptance criteria, security, decisions, sources, and reproducible SDK observations.

## The product promise

> Before an agent spends, make the customer's requirements explicit. Before checkout proceeds, check the actual offer. Afterward, preserve what was approved and accepted.

The first demonstrator uses synthetic flights. The core should work across configured domains; a second hotel profile should demonstrate reuse. A general mode can capture and clarify arbitrary requests, but checkout remains held when a requirement lacks a supported deterministic validator or trustworthy offer data.

## Boundaries

- AI drafts requirements, asks questions, and explains results. It never authorizes a purchase or produces the authoritative PASS/HOLD/BLOCK.
- Customer-approved requirements, carried in signed authorization, are the decision source. The original conversation supplies review context and provenance.
- Merchant-signed offers supply purchase facts. Agent descriptions supply no authority.
- Backend enforcement is mandatory. Confirmation records alone do not bypass invalid credentials, unsupported rules, or VI constraints.
- Commerce discovery and execution sit behind an adapter. Demo fixtures and fake purchases remain separate from the core.
- Evidence supports human dispute review. It does not determine liability or remove customer rights.

## Research baseline

VI was inspected at commit [`356c29635f1c44df7de02edb58699ca9f29bece6`](https://github.com/agent-intent/verifiable-intent/tree/356c29635f1c44df7de02edb58699ca9f29bece6). The package is 0.1.0 and the specification remains 0.1-draft at that snapshot. See [research results](docs/research/vi-sdk-probes.md) for 135 passing focused upstream tests and the important limits of those results.
