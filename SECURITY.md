# Security Policy

> **Selected routes; operation not yet verified.** GitHub Private Vulnerability
> Reporting (PVR) is the primary public reporting route selected for v5.
> `security@edgeforgesuite.com` is the selected email route. PVR enablement at
> public cutover and email activation/testing remain pending. Selection is not
> proof that either route works; these are
> [publication gates](docs/publication-preparation.md#remaining-maintainer-decisions).

This policy belongs to the private
`edgeforge-suite/EdgeForgeKnowledgeServer` release-preparation repository.
Its existence does not establish an operational vulnerability-reporting route.

## Reporting a vulnerability

- **Do not** open a public issue or pull request for an undisclosed
  vulnerability.
- The selected primary destination is
  <https://github.com/edgeforge-suite/EdgeForgeKnowledgeServer/security/advisories/new>.
  Use it only after PVR is enabled and verified at public cutover. Its current
  availability is not asserted.
- The selected email address is `security@edgeforgesuite.com`; activation and
  delivery/reply testing have not been verified. Do not send sensitive material
  to an unverified route.
- Until an operational route is confirmed, withhold exploit details, credentials,
  sensitive files and reproduction material from public issues and PRs. If you
  already have a verified private maintainer channel, use it to request routing;
  otherwise wait for this policy to identify a working channel. Do not place
  vulnerability details in a public request for contact information.
- Include: affected component (an MCP tool, the storage/index layer, a document
  parser), version/baseline or commit, reproduction steps, and impact.

The maintainer must confirm an accountable responder and document disclosure
expectations when the routes are operational. No acknowledgement deadline or
response SLA is promised. Maintainer publication authorization remains pending;
this private preparation does not authorize public exposure.

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
