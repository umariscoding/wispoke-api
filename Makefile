PHONY := help setup venv install run test lint

.PHONY: $(PHONY)

PY := $(shell brew --prefix python@3.11)/bin/python3.11

help:
	@echo "Usage: make setup | make venv | make install | make run | make test"

# Install brew packages needed (libpq and python@3.11)
setup:
	@bash -lc 'brew list libpq >/dev/null 2>&1 || brew install libpq'
	@bash -lc 'brew list python@3.11 >/dev/null 2>&1 || brew install python@3.11'
	@bash -lc 'PROFILE="$${ZPROFILE:-$$HOME/.zprofile}"; echo "export PATH=\"$$(brew --prefix libpq)/bin:$$PATH\"" >> "$${PROFILE}" || true; echo "Added libpq bin to $$PROFILE (restart shell to apply)"'

# Create a Python 3.11 venv
venv:
	@if [ -x "$(PY)" ]; then \
		"$(PY)" -m venv .venv && \
		.venv/bin/python -m pip install --upgrade pip setuptools wheel && \
		echo "Created .venv with $(PY)"; \
	else \
		echo "python@3.11 not found — run 'make setup' first"; exit 1; \
	fi

# Install project requirements
install: venv
	@bash -lc '.venv/bin/python -m pip install -r requirements.txt'
	@bash -lc '.venv/bin/python -m pip install pytest'

# Run the FastAPI app
run:
	@bash -lc '.venv/bin/python -m uvicorn app.main:app --reload --port 8000'

# Run test suite
test:
	@bash -lc '.venv/bin/python -m pytest tests/ -v'
