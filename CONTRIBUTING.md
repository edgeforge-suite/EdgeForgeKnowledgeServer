# Contributing to EdgeForge Knowledge Server

> **This is the authoritative rules home for the EdgeForge Knowledge Server
> (KS / KA) repository.** The tool-specific entry files — [`CLAUDE.md`](CLAUDE.md)
> and [`AGENTS.md`](AGENTS.md) — are thin pointers to this file and favor no
> single tool.

Read these before making meaningful changes:

- [`README.md`](README.md) — what KS is, the 16-tool MCP vocabulary, supported doc
  types, boundaries, and setup.
- [`docs/README.md`](docs/README.md) — documentation map, onboarding overview,
  module guide, and handover evidence.
- The Engine repository's `docs/suite-architecture.md` — suite orientation and the
  "where do I go for X?" routing table.

## What KS is

KS is a separate **local stdio MCP server** for project-scoped document ingestion,
**deterministic SQLite FTS5 / BM25** retrieval, evidence lookup, and
**suggestion-only** manifest guidance. It is intentionally **deterministic**,
**local-stdio-only** and **evidence-first**. Ordinary tools scope records by
project; intentional cross-project reuse paths are described below.

## Non-Negotiable Invariants

- **Deterministic.** The same project corpus and query produce the same results.
  No LLM reasoning or generation, no embeddings/vector search as the primary
  retrieval path, no name inference, no non-deterministic ranking.
- **Suggestion-only boundary.** KS suggests candidates and provides evidence with
  citations. **Studio** owns human review, decisions, in-session state, and
  manifest/package mutation. **Engine** consumes only approved Studio artifacts.
  KS neither produces nor consumes `app-definition.yaml`, never mutates a
  manifest and never generates code. Studio Knowledge Assist is a separate
  feature that can use KS; it is not another name for the KS process.
- **Local stdio only.** No network / SSE transport, no auth surface, no web
  fetching. KS is not a hosted service.
- **Project-scoped and root-constrained.** Ingestion is limited to the roots
  allowed by `EDGEFORGE_KS_ALLOWED_ROOTS`; documents are namespaced per project.
  `search_across_projects` and generic `portfolio_reuse` suggestions and their
  persisted evidence can access other indexed projects. A caller-selected
  `project_id` is not tenant authorization; use separate database/process
  boundaries for trust-separated corpora. See the
  [security boundary map](docs/security-boundary-map.md#3a-mcp-stdio-interface).
- **Forward-compatible decisions.** Suggestion write-back validates known scopes
  and degrades to warning-only for unknown future types; it never persists fake
  suggestions.

## Repository Workflow Rules

- do not push or merge directly to `main`; all changes go through pull requests.
- expect parallel review branches from multiple AI agents.
- keep examples synthetic and exclude secrets and private employer/customer
  material. Necessary public dependency names, upstream references and attribution
  are permitted for accurate documentation and supported examples. Preserve the
  applicable source/distribution permissions, notices and modification disclosures;
  public attribution does not authorize private material.
- **no secrets and no real/production data** — fixtures and examples are
  synthetic only. Secret scanning runs in CI on every PR and push to `main`.

Recommended branch naming (`<agent>` is `claude`, `codex`, `devin`, or a human
name):

- `<agent>/feature/<short-description>` — new capability
- `<agent>/fix/<short-description>` — bug fix
- `<agent>/docs/<short-description>` — documentation
- `<agent>/chore/<short-description>` — maintenance

Recommended PR title prefixes: `[FEATURE]`, `[FIX]`, `[DOCS]`, `[CHORE]`.

## PR lifecycle and ownership

GitHub Issues are authoritative for task ownership and progress. The Engine-owned
Suite roadmap sets direction; the tracker is a dated documentation view, not an
assignment board. A Project board is optional and does not replace issue ownership.

1. Before substantial work, comment on the owning issue with the proposed scope
   and obtain maintainer confirmation of ownership.
2. Open a focused draft PR linked to that issue. Explain the problem, resulting
   change, relevant validation and compatibility risks.
3. Mark the PR ready when implementation and relevant checks are complete.
   **Ready for review does not mean approved.**
4. Record review findings and their resolution in the PR. Identify the reviewed
   revision and review subsequent changes; an earlier approval does not
   automatically cover a new revision.
5. Maintainers retain merge control. Before merging, confirm applicable checks
   passed, required findings are resolved and the latest changes have been reviewed.
6. After merging, check applicable main-branch results and update the linked issue
   with the outcome; close it only when its work is complete. Delete completed
   branches only when they are no longer needed.

Recorded Claude/Codex review reports are review evidence, not formal GitHub
approvals. Identify the actual reviewer and reviewed revision. When the maintainer
also authored the PR, record their merge decision as a maintainer decision, not an
independent human approval. Preserve the existing independent-review approach and
any task-specific repair/re-review limits; this process adds no universal second
review, new release gate or reset of an existing allowance.

## Reporting And Proposing Work

See [project intent and community](README.md#project-intent-and-community) for
ordinary questions, feedback and the maintainer's service boundaries.

Use the repository's bug or feature issue template for non-security work. Search
existing issues and the relevant Suite backlog before proposing a duplicate.
For a bug, include the commit/version, Python and OS, installed extras, expected
and actual results, and a minimal synthetic reproduction. For a feature, explain
the user need, KS ownership, scope exclusions and observable completion criteria.

Use fabricated examples and redacted diagnostics only. Inspect attachments,
paths, screenshots and logs yourself; do not upload original customer documents,
SQLite stores, secrets or production data. Redacting a filename does not sanitize
its contents. KS ingestion does not sanitize submitted documents.

**Undisclosed vulnerabilities must not go into public issues or PRs.** Follow
[SECURITY.md](SECURITY.md); GitHub PVR and `security@edgeforgesuite.com` are selected
but activation and operational verification remain pending. Do not treat route
selection as proof that a reporting channel works.

## License And Sign-Off

KS uses [Apache-2.0](LICENSE), with copyright Santosh Hommaradi and a short
[NOTICE](NOTICE). Contributions use the
[Developer Certificate of Origin 1.1](https://developercertificate.org/), not a
CLA. Read the DCO and sign off each contribution only if you can certify it:

```bash
git commit -s -m "Describe the scoped change"
```

This adds a `Signed-off-by: Your Name <your-email>` trailer using your configured
identity. Do not sign for someone else or rewrite historical commits as part of
this preparation. These terms are selected under EF-V5-RELEASE-SCOPE-RESET rev3;
maintainer publication authorization and public cutover remain pending.
See [publication preparation](docs/publication-preparation.md) for those gates.

## Setup, Build, Test

Python **3.11+** is required for v5 (on macOS the system `python3` may be 3.9 — use
`python3.11`, Homebrew Python, or pyenv).

```bash
python3.11 -m venv .venv
.venv/bin/pip install --constraint constraints.txt -e ".[all,test]"
.venv/bin/python -m pytest -q
```

The committed constraints are the reference dependency graph used by CI and
handover evidence. They target CPython 3.11 on Ubuntu 24.04 x86_64 without
changing the SQLite support floor. The approved v5 Python minimum is 3.11.

The [earlier Python 3.10 proof](docs/handover-evidence/mcp-correction-2026-10-15.md#python-310-proof)
is dated historical evidence, not v5 support. Pillow 13 requires Python 3.11;
the approved revision2 amendment preserves PDF support by raising the Python
floor, not replacing the parser. Unconstrained installation is not the same
reproducible/audited graph. Keep parser extras optional.

The MCP server is launched per [`README.md`](README.md) ("MCP Server Launch").

## Guidance For Reviews And Changes

- prefer small, reviewable changes.
- preserve determinism and the suggestion-only boundary above all.
- if a change could affect the suggestion/evidence contract Studio depends on,
  call that out explicitly.
- keep optional parser extras (`excel` / `pdf` / `docx`) optional — core install
  must not require them.
- include the problem, scope, relevant issue/backlog, tests or documentation
  checks actually run, and any unverified environment in the PR description.
  Use synthetic regression fixtures for behavior changes; documentation edits
  need link/content checks, not tests that simply assert prose.
- reviewers check claims against source and tests, inspect changed fixtures and
  diagnostics for sensitive content, and distinguish dated evidence from new
  acceptance. A secret scan cannot replace that review.
- request review of the final commit. Address blockers with scoped fixes and
  obtain re-review after changes. Required checks must pass on the proposed
  commit; a green documentation PR is not fresh runtime or release acceptance.
  Maintainers own merge and release decisions; an agent verdict is not approval
  to publish.
