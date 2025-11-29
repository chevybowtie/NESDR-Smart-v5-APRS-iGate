# Contributing

Thanks for your interest in contributing to NEO-RX. The project aims to be welcoming and maintainable.

How to contribute

1. Fork the repository and make a feature branch from `develop` (or `main` if you prefer).
2. Run formatting and lint checks locally:

```bash
python -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/ruff check .
.venv/bin/ruff format .
```

3. Add tests for new behavior. Use `pytest` and prefer `caplog` for logging assertions.
4. Open a PR targeting `develop` (or `master` depending on your workflow). Include a clear description and link related issues.

Coding standards

- Follow PEP 8 and the project's `ruff` configuration.
- Keep functions small and well-documented. Add unit tests for edge cases.

Communications

- For design discussions or larger changes, open an issue first to get feedback.
