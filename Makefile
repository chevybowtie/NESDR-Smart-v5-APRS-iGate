PYTHON := python3
VENV_DIR := .venv

.PHONY: setup test lint

setup:
	$(PYTHON) -m venv $(VENV_DIR)
	$(VENV_DIR)/bin/pip install --upgrade pip
	$(VENV_DIR)/bin/pip install -e '.[dev]'

test:
	$(VENV_DIR)/bin/pytest

lint:
	$(VENV_DIR)/bin/ruff check src tests
