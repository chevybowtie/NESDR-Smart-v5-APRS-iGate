#!/usr/bin/env python3
"""
Release automation for multi-package neo-rx.

Handles coordinated releases of all packages:
- Validates version synchronization
- Updates CHANGELOG.md
- Creates git tags for each package
- Builds wheels for all packages
- Optionally uploads to PyPI

Usage:
    python scripts/release.py <version> [--dry-run] [--upload]

Examples:
    python scripts/release.py 0.3.0 --dry-run
    python scripts/release.py 0.3.0
    python scripts/release.py 0.3.0 --upload
"""

import argparse
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PACKAGES = [
    "neo-core",
    "neo-telemetry",
    "neo-aprs",
    "neo-wspr",
    "neo-rx",
]

PACKAGE_PATHS = {
    "neo-core": "src/neo_core",
    "neo-telemetry": "src/neo_telemetry",
    "neo-aprs": "src/neo_aprs",
    "neo-wspr": "src/neo_wspr",
    "neo-rx": ".",
}


def run_command(cmd: list[str], cwd: Path | None = None, capture: bool = True) -> str:
    """Run shell command and return output."""
    result = subprocess.run(cmd, cwd=cwd, capture_output=capture, text=True, check=True)
    return result.stdout.strip() if capture else ""


def find_project_root() -> Path:
    """Find project root by looking for pyproject.toml."""
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / "pyproject.toml").exists():
            return current
        current = current.parent
    raise RuntimeError("Could not find project root")


def check_git_clean(root: Path) -> None:
    """Verify working directory is clean."""
    status = run_command(["git", "status", "--porcelain"], cwd=root)
    if status:
        print("Error: Working directory has uncommitted changes", file=sys.stderr)
        print(status, file=sys.stderr)
        sys.exit(1)


def get_current_version(root: Path) -> str:
    """Get current version from metapackage."""
    pyproject = root / "pyproject.toml"
    content = pyproject.read_text()
    match = re.search(r'^version\s*=\s*"([^"]+)"', content, re.MULTILINE)
    if not match:
        raise RuntimeError("Could not find version in pyproject.toml")
    return match.group(1)


def validate_version_sync(root: Path, expected: str) -> None:
    """Verify all packages have same version."""
    print(f"Validating version synchronization (expecting {expected})...")
    try:
        result = run_command(
            [sys.executable, "scripts/sync_versions.py", "--show"], cwd=root
        )
    except subprocess.CalledProcessError:
        result = ""

    if ("Warning" in result) or (expected not in result):
        print(result or "Version mismatch reported by sync_versions")
        print("Auto-syncing packages to", expected, "...")
        # Align all package versions to the expected root version automatically
        run_command(
            [sys.executable, "scripts/sync_versions.py", expected], cwd=root
        )
        # Re-check for visibility
        recheck = run_command(
            [sys.executable, "scripts/sync_versions.py", "--show"], cwd=root
        )
        print(recheck)
        if "Warning" in recheck:
            raise RuntimeError("Version mismatch persists after auto-sync.")
    print("\u2713 All packages synchronized")


def update_changelog(root: Path, version: str) -> None:
    """Update CHANGELOG.md with release date."""
    changelog = root / "CHANGELOG.md"
    if not changelog.exists():
        print("Warning: CHANGELOG.md not found, skipping", file=sys.stderr)
        return

    content = changelog.read_text()
    today = datetime.now().strftime("%Y-%m-%d")

    # Replace [Unreleased] with version and date
    unreleased_pattern = r"## \[Unreleased\]"
    if not re.search(unreleased_pattern, content):
        print("Warning: No [Unreleased] section in CHANGELOG.md", file=sys.stderr)
        return

    updated = re.sub(unreleased_pattern, f"## [{version}] - {today}", content, count=1)

    changelog.write_text(updated)
    print(f"✓ Updated CHANGELOG.md: [Unreleased] → [{version}] - {today}")


def create_git_tags(root: Path, version: str, dry_run: bool) -> None:
    """Create git tags for each package."""
    print(f"\nCreating git tags for version {version}...")

    tags = [f"{pkg}-v{version}" for pkg in PACKAGES]

    if dry_run:
        print("  [DRY RUN] Would create tags:")
        for tag in tags:
            print(f"    {tag}")
        return

    for tag in tags:
        run_command(["git", "tag", "-a", tag, "-m", f"Release {tag}"], cwd=root)
        print(f"  ✓ Created tag: {tag}")

    print("\nTo push tags to remote:")
    print("  git push origin --tags")


def build_packages(root: Path, dry_run: bool) -> None:
    """Build wheels for all packages."""
    print("\nBuilding packages...")
    # Ensure required build tooling is available in the active interpreter
    try:
        import build  # type: ignore
    except ImportError:
        if not dry_run:
            print("  Installing build tooling (build, wheel)")
            run_command(
                [sys.executable, "-m", "pip", "install", "-q", "build", "wheel"],
                cwd=root,
            )
        else:
            print("  [DRY RUN] Would install build tooling (build, wheel)")

    if dry_run:
        print("  [DRY RUN] Would build all packages")
        return

    # Clean dist directory
    dist_dir = root / "dist"
    if dist_dir.exists():
        import shutil

        shutil.rmtree(dist_dir)
    dist_dir.mkdir()

    for pkg, path in PACKAGE_PATHS.items():
        print(f"  Building {pkg}...")
        pkg_path = root / path
        run_command(
            [sys.executable, "-m", "build", str(pkg_path)], cwd=root, capture=False
        )

    # List built wheels
    wheels = list(dist_dir.glob("*.whl"))
    print(f"\n✓ Built {len(wheels)} wheels:")
    for wheel in wheels:
        print(f"    {wheel.name}")


def upload_to_pypi(root: Path, dry_run: bool) -> None:
    """Upload packages to PyPI."""
    print("\nUploading to PyPI...")

    if dry_run:
        print("  [DRY RUN] Would upload to PyPI")
        return

    # Ensure twine is available
    try:
        import twine  # type: ignore
    except ImportError:
        print("  Installing upload tooling (twine)")
        run_command(
            [sys.executable, "-m", "pip", "install", "-q", "twine"],
            cwd=root,
        )

    root / "dist"
    run_command(
        [sys.executable, "-m", "twine", "upload", "dist/*"], cwd=root, capture=False
    )
    print("✓ Uploaded to PyPI")


def commit_changes(root: Path, version: str, dry_run: bool) -> None:
    """Commit version and changelog updates."""
    print("\nCommitting release changes...")

    if dry_run:
        print("  [DRY RUN] Would commit version/changelog updates")
        return

    # Stage updated files explicitly; glob patterns may not expand through subprocess
    files_to_add = [
        "CHANGELOG.md",
        "pyproject.toml",
        "src/neo_core/pyproject.toml",
        "src/neo_aprs/pyproject.toml",
        "src/neo_wspr/pyproject.toml",
        "src/neo_telemetry/pyproject.toml",
    ]
    run_command(["git", "add", *files_to_add], cwd=root, capture=False)

    # If nothing is staged, skip commit gracefully
    try:
        run_command(["git", "diff", "--cached", "--quiet"], cwd=root)
        print("  No changes staged; skipping commit")
        return
    except subprocess.CalledProcessError:
        # There are staged changes; proceed with commit
        pass

    run_command(["git", "commit", "-m", f"Release {version}"], cwd=root, capture=False)
    print(f"✓ Committed release changes for {version}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Release neo-rx packages")
    parser.add_argument("version", help="Version to release (e.g., 0.3.0)")
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be done"
    )
    parser.add_argument("--upload", action="store_true", help="Upload to PyPI")
    parser.add_argument(
        "--skip-version-check", action="store_true", help="Skip version validation"
    )
    args = parser.parse_args()

    root = find_project_root()
    version = args.version

    print(f"neo-rx release automation - version {version}")
    print(f"{'[DRY RUN MODE]' if args.dry_run else ''}\n")

    # Verify version format
    if not re.match(r"^\d+\.\d+\.\d+(?:-[a-zA-Z0-9.]+)?$", version):
        print(f"Error: Invalid version format: {version}", file=sys.stderr)
        sys.exit(1)

    # Check git status
    if not args.dry_run:
        check_git_clean(root)

    # Validate current version sync
    if not args.skip_version_check:
        current = get_current_version(root)
        if current == version:
            print(f"Error: Already at version {version}", file=sys.stderr)
            sys.exit(1)
        validate_version_sync(root, current)

        # Update versions
        print(f"\nUpdating versions: {current} → {version}")
        if not args.dry_run:
            run_command([sys.executable, "scripts/sync_versions.py", version], cwd=root)
            print("✓ Versions synchronized")
        else:
            print("  [DRY RUN] Would sync versions")

    # Update changelog
    update_changelog(root, version)

    # Commit changes
    if not args.dry_run:
        commit_changes(root, version, args.dry_run)

    # Build packages
    build_packages(root, args.dry_run)

    # Create tags
    create_git_tags(root, version, args.dry_run)

    # Upload to PyPI
    if args.upload:
        upload_to_pypi(root, args.dry_run)

    print("\n" + "=" * 60)
    print(f"✓ Release {version} completed successfully!")
    print("=" * 60)

    if not args.dry_run:
        print("\nNext steps:")
        print("  1. Review the release commit and tags")
        print("  2. Push changes: git push origin <branch>")
        print("  3. Push tags: git push origin --tags")
        if not args.upload:
            print("  4. Upload to PyPI: python scripts/release.py --upload")


if __name__ == "__main__":
    main()
