# Dependency License Inventory — EdgeForge Knowledge Server (declared deps)

> **Import-gate G4 evidence.** Resolved license inventory of KS's declared
> dependencies. See [`dependencies.md`](dependencies.md) for scope and tooling.
>
> **Generated:** 2026-11-02, with **pip-licenses 5.5.5**.
> **Reference baseline:** CPython 3.11 on Ubuntu 24.04 x86_64, using the exact
> versions in `constraints.txt`.

## Notable licenses — summary

**All declared dependencies are permissive (MIT / Apache-2.0 / BSD). No copyleft (GPL / LGPL / AGPL / MPL / EPL) and no UNKNOWN-license packages are present among the declared surface.**

## Declared dependencies (resolved)

Machine-readable copy: [`dependency-licenses.csv`](dependency-licenses.csv).

| Package | Version | License | Scope |
|---|---|---|---|
| `fastmcp` | 3.4.11 | Apache-2.0 | core |
| `openpyxl` | 3.1.5 | MIT License | optional-excel |
| `pdfplumber` | 0.11.10 | MIT License | optional-pdf |
| `pydantic` | 2.13.4 | MIT | core |
| `pytest` | 9.1.1 | MIT | test |
| `pytest-asyncio` | 1.4.0 | Apache-2.0 | test |
| `python-docx` | 1.2.0 | MIT License | optional-docx |

## Scope & transitive note

Covers the **directly declared** dependencies. The resolved transitive license
scan is recorded separately in
[`transitive-dependency-licenses.md`](transitive-dependency-licenses.md). A full
adopter-side audit should rerun both scans against the approved package mirror.
