# Knowledge Server Docs

This directory is the local documentation map for EdgeForge Knowledge Server
(KS / KA). Start here when onboarding, reviewing enterprise handover evidence, or
finding the module that owns a behavior.

## Start Here

- [Architecture overview](architecture-overview.md) — what KS does, boundaries,
  data flow, and persistence model.
- [Module guide](module-guide.md) — where ingestion, parsing, storage, tools,
  and server registration live.
- [Compliance and portability](compliance-and-portability.md) — import-gate
  answers for license posture, data handling, dependency hygiene, and portability.
- [Security boundary map](security-boundary-map.md) — local-stdio boundary,
  parser/input surfaces, storage posture, and explicit caveats.
- [Handover evidence](handover-evidence/README.md) — dated SBOM, license/audit,
  secret-scan and CI records for maintainers, contributors, users and adopters.
- [Publication preparation](publication-preparation.md) — pending maintainer
  decisions, bounded starter-issue drafts and the scope of this preparation.

## Repo-Level References

- [README](../README.md) — current tool vocabulary, setup, and suite posture.
- [CONTRIBUTING](../CONTRIBUTING.md) — authoritative contributor rules.
- [CHANGELOG](../CHANGELOG.md) — suite-aligned baseline history.
- [SECURITY](../SECURITY.md) — selected private routes await operational verification; do not disclose
  vulnerabilities through public issues or PRs.

## Suite References

Cross-repo source-of-truth design docs live in the sibling EdgeForge repository.
Use the imported organization/remote that owns the suite checkout.
