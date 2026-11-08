<!--
EdgeForge Knowledge Server pull request. See CONTRIBUTING.md for the authoritative
rules and README.md for the tool vocabulary and boundaries.
Do not disclose vulnerabilities here. Read SECURITY.md; selected private routes
await operational verification. Use synthetic examples and redacted diagnostics.
-->

## What

<!-- What does this PR change? -->

## Why

<!-- Why is this change needed? Link the roadmap item / issue if any. -->

## Validation

<!-- Commands run and their results (e.g. python -m pytest, real stdio MCP
     round-trip). Paste real output where it matters. -->

## Suggestion/evidence contract risk

<!-- Does this affect the suggestion or evidence-chain contract Studio depends on,
     a tool's parameters/return shape, or the storage schema? Call out any
     backward-compatibility risk explicitly, or state "none". -->

## Checklist

- [ ] PR-only — not pushed or merged directly to `main`
- [ ] Branch follows `<agent>/{feature|fix|docs|chore}/<short-desc>`
- [ ] PR title uses a prefix: `[FEATURE]` / `[FIX]` / `[DOCS]` / `[CHORE]`
- [ ] Deterministic — no LLM/inference, no non-deterministic ranking introduced
- [ ] Suggestion-only boundary preserved (KS suggests; Studio decides; no manifest mutation, no generated code)
- [ ] Local stdio only — no network/SSE transport or auth surface added
- [ ] Relevant validation results and limitations are recorded; behavior changes
      have regression coverage, docs-only changes have content/link checks
- [ ] Required checks pass for the proposed commit; review covers that commit
- [ ] Contribution commits carry a DCO 1.1 Signed-off-by trailer (no CLA)
- [ ] Docs updated in the same PR if behavior changed
- [ ] No secrets, real/production data, or domain-specific/third-party names in committed content
- [ ] Attachments, paths and logs manually checked; no undisclosed vulnerability details
