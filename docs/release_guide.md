RELEASE GUIDE

This file complements `RELEASE.md` with Makefile-driven examples and safety notes.

Quick commands

```bash
# Dry-run (simulate):
make release VERSION=0.2.8 DRY_RUN=1

# Build and tag locally (no upload):
make release VERSION=0.2.8 SKIP=1 FORCE=1

# Build, tag, and upload to PyPI (requires credentials):
make release VERSION=0.2.8 SKIP=1 FORCE=1 UPLOAD=1
```

Push steps (after build & tagging locally)

```bash
# push branch
git push origin develop
# push tags
git push origin --tags
```

Verification & smoke tests

- Use `.venv-smoke` approach documented in `docs/developer.md` to install wheels and verify imports/CLI.
- Prefer CI-based publishing (GH Actions) to avoid exposing credentials locally.

Notes about flags

- `DRY_RUN` shows what would happen without changing the repo or uploading.
- `SKIP` bypasses the script check that disallows releasing the same version twice.
- `FORCE` allows the script to recreate tags.
- `UPLOAD` triggers the twine upload step; make sure you have `~/.pypirc` or `TWINE_*` environment variables set.

ChangeLog

- Add an `[Unreleased]` section to `CHANGELOG.md` to keep upcoming changes and to silence the release script notice.
