# EdgeForge Knowledge Server — developer convenience targets.
# KS v5 requires Python 3.11+ (use an approved interpreter, not macOS system Python).

PY ?= python3.11
VENV ?= .venv

.PHONY: help setup install test test-ci lint format sbom lock audit clean

help:         ## show available developer targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "%-12s %s\n", $$1, $$2}'

setup:        ## create venv and install KS with all extras + test deps
	$(PY) -m venv $(VENV)
	$(VENV)/bin/pip install --constraint constraints.txt -e ".[all,test]"

install:      ## install KS with all extras + test deps into the active interpreter
	$(PY) -m pip install --constraint constraints.txt -e ".[all,test]"

test:         ## run the test suite
	$(VENV)/bin/python -m pytest -q

test-ci:      ## run the CI-style test suite output
	$(PY) -m pytest -v --tb=short

lint:         ## run Ruff lint checks
	$(PY) -m ruff check .

format:       ## run Ruff formatter
	$(PY) -m ruff format .

sbom:         ## regenerate G4 dependency evidence (SBOM + license inventory)
	PY=$(PY) scripts/generate-dependency-evidence.sh

lock:         ## regenerate resolved constraints.txt for all extras + test deps
	PY=$(PY) scripts/generate-constraints.sh

audit:        ## run the blocking live audit against the resolved constraints
	PY=$(PY) scripts/check-dependency-audit.sh

clean:        ## remove local Python/tooling caches
	find . -type d \( -name __pycache__ -o -name .pytest_cache -o -name .ruff_cache \) -prune -exec rm -rf {} +
