## Release checklist

This is a concise checklist for producing a release from this repository.

1. Verify the tree is clean and tests/lint/build pass (local quick check):

```bash
# run the project's verification script (creates ephemeral venv, runs ruff/pytest/build)
bash scripts/verify_release.sh
```

2. Choose branch and prepare release branch:

```bash
# create a release branch from the branch you're preparing (e.g. develop)
git checkout -b release/0.1.0
```

3. Bump version in `pyproject.toml` (if not already set to release version).
   - Update `version = "X.Y.Z"` and commit with message `chore(release): X.Y.Z`.

4. Run verification again to ensure package metadata matches and artifacts build:

```bash
bash scripts/verify_release.sh
```

5. Push the release branch and open a PR against `master` (or push directly if you prefer):

```bash
# add remote (only if not already configured)
git remote add origin https://github.com/chevybowtie/NESDR-Smart-v5-APRS-iGate.git
git push -u origin release/0.1.0
```

6. After review & merge into `master`, tag the release and push tag:

```bash
git checkout master
git pull origin master
git tag -s v0.1.0 -m "Release v0.1.0"
git push origin v0.1.0
```

7. Publish artifacts (two options):
   - CI-based publish: configure GH Actions to publish on pushed tags (preferred).
   - Manual publish: in a clean venv install `build` and `twine` and run:

```bash
# build artifacts locally
python -m build
# upload to TestPyPI or PyPI
python -m twine upload --repository testpypi dist/*
```

8. Post-release housekeeping:
   - Create or update `CHANGELOG.md` with release notes.
   - Close any milestone or issues associated with the release.
   - Remove ephemeral venvs used for verification (e.g., `.venv-check`).

Notes
- Use `scripts/verify_release.sh` to automate verification steps locally.
- Prefer CI for publish to avoid leaking credentials from your local machine.
