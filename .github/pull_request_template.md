<!--
EdgeForge Knowledge Server pull request. See CONTRIBUTING.md for the authoritative
rules and README.md for the tool vocabulary and boundaries.
Do not disclose vulnerabilities here. Read SECURITY.md for private reporting
routes and availability guidance. Use synthetic examples and redacted diagnostics.
-->

## What

<!-- What does this PR change? -->

## Why

<!-- What problem does this solve? -->

Linked issue: <!-- Link the owning issue and confirmed scope, or explain if none applies. -->

## Validation

<!-- Record the tested revision, commands actually run, results, skips and untested
     limitations. Use relevant checks; prose-only edits need content/link checks,
     not new tests that merely assert wording. -->

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
- [ ] Contribution commits carry the contributor's DCO 1.1 Signed-off-by trailer (`git commit -s`; no CLA)
- [ ] Docs updated in the same PR if behavior changed
- [ ] No secrets, private employer/customer material or real/production data; fixtures are synthetic
- [ ] Attachments, paths and logs manually checked; no undisclosed vulnerability details

<!-- Necessary public dependency names, upstream references and attribution are
     permitted under CONTRIBUTING.md; preserve applicable permissions and notices. -->
