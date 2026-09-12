# SigMap Query Context
Generated: 2026-09-12T16:07:49.162Z

## docs/release_guide.md
```
h1 Release Guide
h2 Overview
h2 Automatic Release (Recommended)
h3 1. Prepare release branch
h1 Ensure tree is clean
h1 Create release branch
h3 2. Update CHANGELOG.md
h2 [Unreleased]
h3 Added
h3 Changed
h3 Fixed
h3 Removed
h3 3. Verify the release
h3 4. Dry-run the release
h3 5. Execute the release
h3 6. Push release branch and tags
h1 Push the release branch
h1 Push all tags
h3 7. Create pull request on GitHub
h3 8. Publish to PyPI (optional)
```

## scripts/release.py
```
def run_command(cmd: list[str], cwd: Path | None, capture: bool) → str
def find_project_root() → Path
def check_git_clean(root: Path) → None
def get_current_version(root: Path) → str
def validate_version_sync(root: Path, expected: str) → None
def update_changelog(root: Path, version: str) → None
def tag_exists(root: Path, tag: str) → bool
def create_git_tags(root: Path, version: str, dry_run: bool, force: bool) → None
def build_packages(root: Path, dry_run: bool) → None
def upload_to_pypi(root: Path, dry_run: bool) → None
def commit_changes(root: Path, version: str, dry_run: bool) → None
def main() → None
```

## docs/developer.md
```
h1 Install packages in dependency order
h1 from the repo root
h1 install only the wheels built from this repo
h1 install any runtime deps reported on import
h1 quick import checks
h1 CLI smoke
h1 Dry-run for version 0.2.8
h1 Build and create tags locally (no upload)
h1 Build, create tags, and upload to PyPI (requires credentials)
code-fence bash
code-fence plain
```

## scripts/sync_versions.py
```
def find_project_root() → Path
def get_current_versions(root: Path) → dict[str, str]
def update_version_in_file(path: Path, new_version: str) → None
def sync_versions(root: Path, new_version: str) → None
def show_versions(root: Path) → None
def validate_version(version: str) → bool
def main() → None
```

## docs/diagnostics.md
```
h1 Diagnostics Command Outline
h2 Command Summary
h2 Device Discovery
h2 Checks Performed (Common)
h3 1. Environment
h3 2. Configuration Validation
h3 3. SDR Hardware
h2 ADS-B-Specific Checks
h3 4. Decoder (readsb/dump1090)
h3 5. RTL-SDR Availability
h3 6. ADS-B Exchange Integration
h2 APRS-Specific Checks
h3 7. Direwolf / KISS
h3 8. APRS-IS Uplink
h2 WSPR-Specific Checks
h3 7. Decoder Binary
h3 8. Upconverter Detection
h2 Configuration & Paths (All Modes)
h3 9. Configuration & Paths
h2 Output Schema
```
