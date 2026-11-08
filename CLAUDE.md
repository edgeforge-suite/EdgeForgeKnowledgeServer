# EdgeForge Knowledge Server — Claude

EdgeForge **Knowledge Server (KS / KA)** — a separate **local stdio MCP server**
for project-scoped document ingestion, **deterministic SQLite FTS5 / BM25**
retrieval, evidence lookup, and **suggestion-only** manifest guidance. No LLM, no
network transport, no auth — deterministic and evidence-first.

## Start here

- **Authoritative rules — read before changing anything:**
  [`CONTRIBUTING.md`](CONTRIBUTING.md)
- **What KS is, the MCP tool vocabulary, and boundaries:** [`README.md`](README.md)
- **Suite orientation ("where do I go for X?"):** the Engine repository's
  `docs/suite-architecture.md`.
- **Branch / PR conventions:** see [`CONTRIBUTING.md`](CONTRIBUTING.md)
  (`<agent>/{feature|fix|docs|chore}/<short-desc>`; PR title prefix
  `[FEATURE]` / `[FIX]` / `[DOCS]` / `[CHORE]`).

## Invariants (do not break)

- **Suggestion-only, deterministic.** KS suggests candidates and cites evidence;
  Studio owns human review and decisions; Engine consumes only approved Studio
  artifacts. No LLM reasoning or generation; same input → same suggestions.
- **Local stdio MCP only** — no network / SSE transport and no auth surface.
- **Project-isolated, evidence-first**; ingestion roots are constrained by
  `EDGEFORGE_KS_ALLOWED_ROOTS`.
- **No secrets or real/production data** committed — synthetic fixtures only.

---

*This file is a thin, tool-specific pointer. The canonical rules live in
[`CONTRIBUTING.md`](CONTRIBUTING.md) — keep it in sync, don't fork it.*
