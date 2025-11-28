PYTHON := python3
VENV_DIR := .venv
PACKAGES := neo_core neo_telemetry neo_aprs neo_wspr neo_rx

.PHONY: setup test lint format lint-fix build clean verify-release sync-versions

setup:
	$(PYTHON) -m venv $(VENV_DIR)
	$(VENV_DIR)/bin/pip install --upgrade pip
	# Install in dependency order
	$(VENV_DIR)/bin/pip install -e ./src/neo_core[dev]
	$(VENV_DIR)/bin/pip install -e ./src/neo_telemetry[dev]
	$(VENV_DIR)/bin/pip install -e ./src/neo_aprs[dev,direwolf]
	$(VENV_DIR)/bin/pip install -e ./src/neo_wspr[dev]
	$(VENV_DIR)/bin/pip install -e .[dev,all]

test:
	PYTHONPATH=src $(VENV_DIR)/bin/pytest

lint:
	$(VENV_DIR)/bin/ruff check src tests
	@echo "✓ Lint checks passed"

format:
	$(VENV_DIR)/bin/ruff format src tests
	@echo "✓ Code formatted"

lint-fix:
	$(VENV_DIR)/bin/ruff check src tests --fix
	$(VENV_DIR)/bin/ruff format src tests
	@echo "✓ Lint issues fixed and code formatted"

build:
	@echo "Building all packages..."
	@rm -rf dist build src/*/*.egg-info *.egg-info
	@$(VENV_DIR)/bin/pip install --upgrade build
	@for pkg in $(PACKAGES); do \
		if [ "$$pkg" = "neo_rx" ]; then \
			echo "Building $$pkg (metapackage)..."; \
			$(VENV_DIR)/bin/python -m build .; \
		else \
			echo "Building $$pkg..."; \
			$(VENV_DIR)/bin/python -m build src/$$pkg; \
		fi \
	done
	@echo "✓ Built $(shell ls -1 dist/*.whl | wc -l) wheels"

clean:
	rm -rf dist build src/*/*.egg-info *.egg-info
	rm -rf .pytest_cache src/*/.pytest_cache tests/.pytest_cache
	rm -rf .venv-check
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete

verify-release:
	@echo "Running full verification suite..."
	@bash scripts/verify_release.sh

sync-versions:
	@if [ -z "$(VERSION)" ]; then \
		echo "Usage: make sync-versions VERSION=0.3.0"; \
		exit 1; \
	fi
	@$(VENV_DIR)/bin/python scripts/sync_versions.py $(VERSION)

release:
	@if [ -z "$(VERSION)" ]; then \
		echo "Usage: make release VERSION=0.3.0 [DRY_RUN=1] [UPLOAD=1] [SKIP=1] [FORCE=1]"; \
		exit 1; \
	fi
	@$(VENV_DIR)/bin/python scripts/release.py $(VERSION) \
	    $(if $(DRY_RUN),--dry-run,) \
		$(if $(UPLOAD),--upload,) \
		$(if $(SKIP),--skip-version-check,) \
		$(if $(FORCE),--force-tags,)
