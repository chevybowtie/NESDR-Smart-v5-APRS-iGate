# Release Guide

This guide explains how to prepare and publish a release using the `Makefile` commands.

## Prerequisites

- Clean working tree: `git status --porcelain` should be empty
- Active virtual environment with dev dependencies: `source .venv/bin/activate`
- PyPI credentials configured (for upload step)

## Release Process

### 1. Prepare release branch

Create a release branch from `develop`:

```bash
git checkout develop
git pull origin develop
git checkout -b release/0.2.9
```

### 2. Sync versions across all packages

Use the `sync-versions` target to update version numbers in all `pyproject.toml` files:

```bash
make sync-versions VERSION=0.2.9
```

This updates:
- Root `pyproject.toml`
- All subpackage `pyproject.toml` files (`neo_core`, `neo_telemetry`, `neo_aprs`, `neo_wspr`)

Review and commit the version changes:

```bash
git add pyproject.toml src/*/pyproject.toml
git commit -m "chore(release): bump version to 0.2.9"
```

### 3. Update CHANGELOG.md

Move items from `[Unreleased]` to a new versioned section:

```markdown
## [0.2.9] - 2025-11-28

(copy content from [Unreleased] section)

## [Unreleased]

(leave empty or add placeholder entries)
```

Commit the changelog:

```bash
git add CHANGELOG.md
git commit -m "docs: update CHANGELOG for 0.2.9"
```

### 4. Run verification suite

Verify tests, linting, and builds pass:

```bash
make verify-release
```

This runs `scripts/verify_release.sh`, which creates an ephemeral venv and runs:
- `ruff check` (linting)
- `pytest` (full test suite)
- `python -m build` (wheel builds for all packages)

### 5. Dry-run the release

Simulate the release to verify everything is ready:

```bash
make release VERSION=0.2.9 DRY_RUN=1
```

This will show:
- What tags would be created
- What artifacts would be built
- Any warnings (e.g., missing `[Unreleased]` section)

### 6. Build and tag (no upload)

Perform the actual release build and create Git tags:

```bash
make release VERSION=0.2.9 SKIP=1 FORCE=1
```

Flags explained:
- `SKIP=1` — Skip version equality check (allows re-running for same version)
- `FORCE=1` — Force tag recreation if tags already exist

This will:
- Build all package wheels and sdists
- Create tags: `neo-core-v0.2.9`, `neo-telemetry-v0.2.9`, `neo-aprs-v0.2.9`, `neo-wspr-v0.2.9`, `neo-rx-v0.2.9`

### 7. Push branch and tags

Push the release branch and tags to GitHub:

```bash
git push origin release/0.2.9
git push origin --tags
```

### 8. Open pull request

Open a PR from `release/0.2.9` to `master` for review. After approval and merge:

```bash
git checkout master
git pull origin master
```

### 9. Publish to PyPI (optional)

**Option A: CI-based publish (recommended)**

Configure GitHub Actions to publish on pushed tags automatically.

**Option B: Manual publish**

Upload the built artifacts to PyPI:

```bash
make release VERSION=0.2.9 SKIP=1 FORCE=1 UPLOAD=1
```

⚠️ **Warning**: The `UPLOAD=1` flag will publish to PyPI using `twine`. Ensure:
- You have PyPI credentials configured (`~/.pypirc` or `TWINE_*` env vars)
- You understand the consequences of publishing
- You're on the correct branch/commit

### 10. Post-release cleanup

```bash
# Remove ephemeral venvs
rm -rf .venv-check .venv-smoke

# Tag master with version tag if not already done
git checkout master
git tag -s v0.2.9 -m "Release v0.2.9"
git push origin v0.2.9
```

## Makefile Targets Reference

| Target | Description |
|--------|-------------|
| `make sync-versions VERSION=X.Y.Z` | Sync version across all package `pyproject.toml` files |
| `make verify-release` | Run full verification suite (lint, test, build) |
| `make release VERSION=X.Y.Z DRY_RUN=1` | Simulate release (safe, read-only) |
| `make release VERSION=X.Y.Z SKIP=1 FORCE=1` | Build artifacts and create tags locally |
| `make release VERSION=X.Y.Z SKIP=1 FORCE=1 UPLOAD=1` | Build, tag, and upload to PyPI |

## Release Flags

| Flag | Effect |
|------|--------|
| `DRY_RUN=1` | Simulate the release without making changes |
| `SKIP=1` | Skip the "already at version" guard |
| `FORCE=1` | Force recreation of existing tags |
| `UPLOAD=1` | Upload artifacts to PyPI (requires credentials) |

## Smoke Testing (optional but recommended)

After building wheels, verify them in an isolated environment:

```bash
# Create ephemeral venv
rm -rf .venv-smoke
python3 -m venv .venv-smoke
.venv-smoke/bin/pip install --upgrade pip wheel setuptools

# Install built wheels (no deps)
.venv-smoke/bin/pip install --no-deps dist/*.whl src/*/dist/*.whl

# Install runtime dependencies
.venv-smoke/bin/pip install tomli_w numpy pyrtlsdr aprslib

# Verify imports
.venv-smoke/bin/python -c "import neo_rx; print('neo_rx OK')"

# CLI smoke test
.venv-smoke/bin/neo-rx --version
```

## Additional Documentation

- `docs/developer.md` — Developer setup and smoke-test instructions
- `docs/release_guide.md` — Expanded release examples and troubleshooting
