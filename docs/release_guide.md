# Release Guide

Complete instructions for creating and publishing a new release of the Neo-RX multi-package project.

## Overview

The Neo-RX project consists of five coordinated packages that must be released together:
- `neo-core`: shared utilities, configuration, radio capture
- `neo-telemetry`: MQTT publishing and on-disk queue
- `neo-aprs`: APRS protocol, KISS/APRS-IS clients, listen command
- `neo-wspr`: WSPR decoding, calibration, scan/upload commands
- `neo-rx`: metapackage CLI entry point, pulls all subpackages

All packages must maintain synchronized versions. This guide provides two approaches:
- **Automatic**: Single `make release` command (recommended)
- **Manual**: Step-by-step commands for full control

---

## Automatic Release (Recommended)

### 1. Prepare release branch

Start from `develop` (or your active branch):

```bash
# Ensure tree is clean
git status

# Create release branch
git checkout -b release/0.2.9
```

### 2. Update CHANGELOG.md

Add release notes under `[Unreleased]` section (or create one if missing):

```markdown
## [Unreleased]

### Added
- New feature descriptions

### Changed
- Modified behavior notes

### Fixed
- Bug fixes

### Removed
- Deprecated functionality
```

Commit your changelog updates:

```bash
git add CHANGELOG.md
git commit -m "docs: update CHANGELOG for 0.2.9"
```

### 3. Verify the release

Run verification in a clean ephemeral venv:

```bash
make verify-release
```

This creates `.venv-check`, builds all five packages, installs wheels, and validates:
- Imports work for all packages
- CLI commands execute (`neo-rx --version`, `neo-rx aprs --help`, etc.)
- Package metadata is correct

Fix any errors before proceeding.

### 4. Dry-run the release

Simulate the release process without making changes:

```bash
make release VERSION=0.2.9 DRY_RUN=1
```

Review the output to confirm:
- Version numbers are correct
- Git tags will be created properly
- Build artifacts will be generated
- CHANGELOG.md date will be updated

### 5. Execute the release

Build, tag, and prepare for publishing:

```bash
make release VERSION=0.2.9
```

This will:
- **Automatically sync versions** across all five packages to 0.2.9
- Update `CHANGELOG.md` with release date
- Commit: `"Release 0.2.9"`
- Build wheels and source distributions for all five packages
- Create five annotated git tags: `neo-core-v0.2.9`, `neo-aprs-v0.2.9`, `neo-wspr-v0.2.9`, `neo-telemetry-v0.2.9`, `neo-rx-v0.2.9`
- Output artifacts to `dist/` and `src/*/dist/`

**Note**: Tags are created locally only. Push them in the next step.

### 6. Push release branch and tags

```bash
# Push the release branch
git push origin release/0.2.9

# Push all tags
git push origin --tags
```

### 7. Create pull request on GitHub

1. Navigate to https://github.com/chevybowtie/NESDR-Smart-v5-APRS-iGate
2. Create a Pull Request from `release/0.2.9` to `master`
3. Review changes and merge after approval
4. Delete the release branch after merge (GitHub can do this automatically)

### 8. Publish to PyPI (optional)

**After merging to master**, publish the release artifacts:

```bash
# Switch to master and pull merged changes
git checkout master
git pull origin master

# Upload to PyPI (requires credentials)
make release VERSION=0.2.9 SKIP=1 UPLOAD=1
```

Or use CI-based publishing (preferred for security):
- Configure GitHub Actions with `PYPI_API_TOKEN` secret
- Workflow triggers on pushed tags matching `neo-*-v*`

---

## Manual Release (Step-by-Step)

For situations requiring manual control or troubleshooting.

### 1. Prepare release branch

```bash
# Ensure working directory is clean
git status

# Create release branch from develop
git checkout develop
git pull origin develop
git checkout -b release/0.2.9
```

### 2. Sync package versions

Update version in all five `pyproject.toml` files:

```bash
# Automated sync
python scripts/sync_versions.py 0.2.9

# Verify all versions match
python scripts/sync_versions.py --show
```

Commit the version changes:

```bash
git add src/neo_core/pyproject.toml \
        src/neo_telemetry/pyproject.toml \
        src/neo_aprs/pyproject.toml \
        src/neo_wspr/pyproject.toml \
        pyproject.toml
git commit -m "chore: sync versions to 0.2.9"
```

### 3. Update CHANGELOG.md

Edit `CHANGELOG.md` and move `[Unreleased]` content to a new versioned section:

```markdown
## [0.2.9] - 2025-11-29

### Added
- Feature descriptions here

### Changed
- Change descriptions here

### Fixed
- Bug fixes here

## [Unreleased]
<!-- Keep this section for future changes -->
```

Commit the changelog:

```bash
git add CHANGELOG.md
git commit -m "docs: update CHANGELOG for 0.2.9"
```

### 4. Run tests and lint

```bash
# Activate development venv
source .venv/bin/activate

# Run linting
make lint

# Run full test suite
make test

# Or use the combined verification script
bash scripts/verify_release.sh
```

Fix any failures before continuing.

### 5. Build all packages

Build wheels and source distributions:

```bash
# Build metapackage
python -m build

# Build each subpackage
python -m build src/neo_core
python -m build src/neo_telemetry
python -m build src/neo_aprs
python -m build src/neo_wspr
```

Artifacts appear in:
- `dist/` (metapackage: `neo_rx-0.2.9-*.whl`, `neo_rx-0.2.9.tar.gz`)
- `src/neo_core/dist/` (neo_core wheels and tarball)
- `src/neo_telemetry/dist/` (neo_telemetry wheels and tarball)
- `src/neo_aprs/dist/` (neo_aprs wheels and tarball)
- `src/neo_wspr/dist/` (neo_wspr wheels and tarball)

### 6. Create git tags

Create annotated tags for each package:

```bash
git tag -a neo-core-v0.2.9 -m "neo-core 0.2.9"
git tag -a neo-telemetry-v0.2.9 -m "neo-telemetry 0.2.9"
git tag -a neo-aprs-v0.2.9 -m "neo-aprs 0.2.9"
git tag -a neo-wspr-v0.2.9 -m "neo-wspr 0.2.9"
git tag -a neo-rx-v0.2.9 -m "neo-rx 0.2.9"
```

### 7. Smoke test the release

Create an isolated environment and test the built wheels:

```bash
# Create ephemeral venv
python -m venv .venv-smoke
source .venv-smoke/bin/activate

# Install runtime dependencies first (not in wheels)
pip install tomli-w numpy pyrtlsdr aprslib

# Install all built wheels
pip install dist/neo_rx-0.2.9-py3-none-any.whl

# Verify installation
neo-rx --version  # Should output: neo-rx 0.2.9
neo-rx aprs --help
neo-rx wspr --help

# Test imports
python -c "import neo_core; import neo_aprs; import neo_wspr; import neo_telemetry; import neo_rx"

# Cleanup
deactivate
rm -rf .venv-smoke
```

If any smoke tests fail, fix the issues, rebuild, and re-test.

### 8. Push branch and tags

```bash
# Push release branch
git push origin release/0.2.9

# Push all tags
git push origin --tags
```

### 9. Create GitHub pull request

1. Go to https://github.com/chevybowtie/NESDR-Smart-v5-APRS-iGate
2. Create PR: `release/0.2.9` → `master`
3. Add release notes from CHANGELOG.md to PR description
4. Request review and merge after approval
5. Delete release branch after merge

### 10. Publish to PyPI

After merge to master:

```bash
# Switch to master
git checkout master
git pull origin master

# Upload all distributions to PyPI
python -m twine upload dist/*.whl dist/*.tar.gz
python -m twine upload src/neo_core/dist/*
python -m twine upload src/neo_telemetry/dist/*
python -m twine upload src/neo_aprs/dist/*
python -m twine upload src/neo_wspr/dist/*
```

Requires PyPI credentials in `~/.pypirc` or `TWINE_USERNAME`/`TWINE_PASSWORD` environment variables.

---

## Makefile Flags Reference

### `make release` flags

- `VERSION=x.y.z` **(required)**: Target version for release
- `DRY_RUN=1`: Simulate release without making changes
- `SKIP=1`: Bypass version-already-released guard (for rebuilds)
- `FORCE=1`: Recreate git tags if they exist
- `UPLOAD=1`: Upload to PyPI via twine after building

Examples:

```bash
# Safe dry-run
make release VERSION=0.2.9 DRY_RUN=1

# Build and tag (no upload)
make release VERSION=0.2.9

# Rebuild without version bump (force overwrite tags)
make release VERSION=0.2.9 SKIP=1 FORCE=1

# Full release with PyPI upload
make release VERSION=0.2.9 UPLOAD=1
```

### `make sync-versions` flags

- `VERSION=x.y.z` **(required)**: Version to sync across all packages

Example:

```bash
make sync-versions VERSION=0.2.9
```

### `make verify-release`

No flags. Creates `.venv-check`, builds packages, installs wheels, runs smoke tests.

```bash
make verify-release
```

---

## Troubleshooting

### Version already exists

If you need to rebuild the same version:

```bash
make release VERSION=0.2.9 SKIP=1 FORCE=1
```

### Tags already exist

Delete tags locally and remotely, then recreate:

```bash
# Delete local tags
git tag -d neo-core-v0.2.9 neo-telemetry-v0.2.9 neo-aprs-v0.2.9 neo-wspr-v0.2.9 neo-rx-v0.2.9

# Delete remote tags
git push origin --delete neo-core-v0.2.9 neo-telemetry-v0.2.9 neo-aprs-v0.2.9 neo-wspr-v0.2.9 neo-rx-v0.2.9

# Recreate
make release VERSION=0.2.9 FORCE=1
```

### Build failures

Common issues:

1. **Missing dependencies**: Ensure dev environment is activated and up-to-date:
   ```bash
   source .venv/bin/activate
   pip install --upgrade pip build twine
   ```

2. **Lint errors**: Fix with `make format` then `make lint`

3. **Test failures**: Run `make test` and address failures before releasing

4. **Version sync issues**: Check all versions match:
   ```bash
   python scripts/sync_versions.py --show
   ```

### Smoke test failures

If wheels don't install or CLI fails:

1. Check for missing runtime dependencies (tomli-w, numpy, pyrtlsdr, aprslib)
2. Verify all five wheels were built correctly
3. Test imports individually to isolate the problem package
4. Review build logs for warnings about missing files

---

## Post-Release Checklist

After successful release and PyPI upload:

- [ ] Verify packages are live on PyPI (https://pypi.org/project/neo-rx/)
- [ ] Test installation in fresh environment: `pip install neo-rx==0.2.9`
- [ ] Close any GitHub milestone for this release
- [ ] Create new `[Unreleased]` section in CHANGELOG.md for future work
- [ ] Clean up ephemeral venvs: `rm -rf .venv-check .venv-smoke`
- [ ] Update any documentation referencing old version numbers
- [ ] Announce release (if applicable)

---

## CI/CD Integration

For automated releases via GitHub Actions:

1. Store `PYPI_API_TOKEN` as GitHub repository secret
2. Configure workflow to trigger on tag push: `neo-*-v*`
3. Workflow should:
   - Checkout code at tag
   - Build all packages
   - Run smoke tests
   - Upload to PyPI using `PYPI_API_TOKEN`

This is preferred over manual upload for security (no local credential exposure).

---

## Reference: Package Dependencies

Build-time dependencies:
- `setuptools>=69`
- `build>=1.0`

Runtime dependencies (not in wheels, install separately for smoke tests):
- `tomli-w>=1.1`
- `numpy>=2.0`
- `pyrtlsdr>=0.3.0`
- `aprslib>=0.7.2,<0.9`

Development dependencies:
- `pytest`, `pytest-cov`, `pytest-mock`
- `ruff` (format and lint)
- `pyright` (type checking)
- `twine` (PyPI upload)
