# Security Policy

This policy belongs to `edgeforge-suite/EdgeForgeKnowledgeServer`. Report
suspected vulnerabilities through an available private route below. Publication
operators must verify reporting routes under the
[public-cutover requirements](docs/publication-preparation.md#remaining-maintainer-decisions);
listing an address or form is not evidence of its operation.

## Reporting a vulnerability

- **Do not** open a public issue or pull request for an undisclosed
  vulnerability.
- Use GitHub Private Vulnerability Reporting (PVR), **when available**:
  <https://github.com/edgeforge-suite/EdgeForgeKnowledgeServer/security/advisories/new>.
  Confirm that the destination opens a private report before submitting details.
- The designated security email is **`security@edgeforgesuite.com`**.
- If neither route is available, request a private maintainer channel without
  including vulnerability details in a public issue or PR. Share reproduction
  material and sensitive details only through an available private route.
- Include: affected component (an MCP tool, the storage/index layer, a document
  parser), version/baseline or commit, reproduction steps, and impact.

The maintainer must identify an accountable responder and document coordinated
disclosure handling. No acknowledgement deadline or response SLA is promised.
Maintainer publication authorization is separate from technical acceptance and
reporting-route selection.

## Supported versions

Security fixes target the **current suite baseline** (see [`README.md`](README.md)
for the current KS baseline). Older tags are not separately maintained.

## Scope notes

- **Local stdio MCP server.** KS runs as a local stdio process with **no network
  / SSE transport and no auth surface** — it is not a hosted service. The primary
  trust boundary is the local MCP client and the document roots allowed via
  `EDGEFORGE_KS_ALLOWED_ROOTS`.
- **Deterministic, suggestion-only.** KS performs deterministic SQLite FTS5 / BM25
  retrieval and evidence citation. It has **no LLM** and does not generate code or
  mutate manifests. A vulnerability report should say which tool/path reproduces.
- **No secrets or real/production data** should ever be committed to this
  repository (synthetic-only-data policy). If you find any, follow the private
  routing guidance above without reproducing the value publicly. Secret scanning
  runs in CI on every PR and push to `main`; it checks configured patterns and
  does not prove that all content is synthetic or safe to publish.
- This repository is part of a multi-repo suite (Engine, Studio, Knowledge
  Server). Report an issue against the repository where it reproduces; cross-repo
  issues can be noted in the report.
