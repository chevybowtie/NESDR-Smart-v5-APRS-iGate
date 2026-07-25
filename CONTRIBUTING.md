# Contributing

Thanks for your interest in contributing to NEO-RX. The project aims to be welcoming and maintainable.

How to contribute

1. Fork the repository and make a feature branch from `develop` (or `master` if you prefer).
2. Set up a development environment. Neo-RX is split into several packages under `src/`, each with its own `pyproject.toml`, so the simplest path is the Makefile helper:

```bash
make setup
```

This creates `.venv` and installs all packages in dependency order with the `dev` extras. See `DEVELOPER_NOTES.md` for the manual, step-by-step install if you need finer control.

3. Run formatting, lint, and type checks locally:

```bash
make format
make lint
make mypy
```

4. Add tests for new behavior and run the suite. Use `pytest` and prefer `caplog` for logging assertions.

```bash
make test
```

5. Open a PR targeting `develop` (or `master` depending on your workflow). Include a clear description and link related issues.

Coding standards

- Follow PEP 8 and the project's `ruff` configuration.
- Keep functions small and well-documented. Add unit tests for edge cases.
- See `DEVELOPER_NOTES.md` for CLI, logging, and packaging conventions.

Communications

- For design discussions or larger changes, open an issue first to get feedback.
