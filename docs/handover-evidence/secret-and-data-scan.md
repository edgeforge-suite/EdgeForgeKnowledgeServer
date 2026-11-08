# Secret & Data Scan — Evidence

> **Import-gate G3.** A named, ongoing, auditable secret scan plus the
> synthetic-only-data policy. The handover-evidence index (G10) links this doc.
>
> **Last updated:** 2026-06-12.
>
> **Scope clarification (2026-09-26):** The original manual observation remains
> dated. Current CI scans the committed tree for configured secret patterns;
> this and the synthetic-only contributor policy are not proof that every item
> is synthetic or contains no sensitive data.

## Scanner

- **Tool:** [gitleaks](https://github.com/gitleaks/gitleaks) — a named, widely
  used secret scanner.
- **Version:** pinned to `8.30.1` in the CI workflow.
- **Ruleset:** gitleaks' full default ruleset (`[extend] useDefault = true` in
  [`.gitleaks.toml`](../../.gitleaks.toml)). No repository allowlist entries
  are configured; this does not establish the origin of committed content.

## How it runs (CI)

- **Workflow:** [`.github/workflows/secret-scan.yml`](../../.github/workflows/secret-scan.yml).
- **Triggers:** every `pull_request` (all branches) and every `push` to `main`.
- **What it does:** installs the pinned gitleaks CLI and runs
  `gitleaks dir . --redact --exit-code 1` over the committed tree. A match to a
  configured pattern fails the job; `--redact` keeps match values out of logs.
  This routine CI scan does not inspect the full reachable Git history.
- **Portability:** uses the pinned CLI (not a marketplace action), so it needs no
  org license and carries cleanly into an adopting organization's CI.

## Result

- At the original 2026-06-12 review, the committed tree was subject to the
  synthetic-only policy, and a bounded manual pattern review found no
  credentials, keys, or tokens. That observation is not a proof of provenance
  or exhaustive sensitive-data review.
- The **CI `Secret Scan` workflow** runs the committed-tree scan on every PR and
  push to `main`. A passing run means no configured pattern matched the tree
  scanned in that run; it does not prove that no secrets or real data exist.

## Allowlist

The config ([`.gitleaks.toml`](../../.gitleaks.toml)) extends gitleaks' default
ruleset with **no allowlist entries** today. Discipline: a justified `[allowlist]`
block is added only if CI surfaces a confirmed **non-credential** false positive;
the policy forbids silencing real or real-looking secrets.

## Synthetic-only data policy

- **Contributor requirement:** commit only fabricated fixtures, examples, and
  test data; do not commit real customer data, production data, or PII. A human
  must review provenance and content because the scanner cannot verify this.
- Sample documents, field catalogs, DDL fixtures, and ingested-document fixtures
  under `tests/` are intended as illustrative fabricated values.
- The supported KS runtime uses local stdio and transmits no ingested content to
  a network service; it returns evidence to its local MCP client. Ingestion is
  constrained to `EDGEFORGE_KS_ALLOWED_ROOTS`, and the SQLite index lives at
  `EDGEFORGE_KS_DB_PATH`. The repository's `.gitignore` covers `*.sqlite3` and
  `*.db`, not arbitrary files under allowed roots or database files with other
  names. Keep sensitive source files and the database outside the repository;
  review staged files before committing.
- Any future real or PII data must **not** be committed; contributors use
  synthetic equivalents. The secret scan checks configured patterns in the
  committed tree on every PR, while human content review remains necessary.

## Scope notes

- This scan does not establish project isolation. Generic `portfolio_reuse`
  suggestions can persist citations to other indexed projects, and their
  evidence chains can read those source projects (see [G8 §3a](../security-boundary-map.md#3-attack-surfaces-per-component)).
- This is the **secret-scan + synthetic-only contributor-policy** record (G3).
  Automated PII detection and exhaustive provenance review are outside this
  scan's scope; the policy and scan do not by themselves prove the absence of
  real data or every secret.
- SBOM + dependency-license inventory is a separate gate (G4); the
  handover-evidence **index** is G10.
