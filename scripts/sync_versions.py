#!/usr/bin/env python3
"""
Version synchronization tool for multi-package neo-rx.

Updates version numbers across all package pyproject.toml files:
- neo-rx (metapackage)
- neo-core
- neo-aprs
- neo-wspr
- neo-adsb
- neo-telemetry

Usage:
    python scripts/sync_versions.py <new_version>
    python scripts/sync_versions.py --show

Examples:
    python scripts/sync_versions.py 0.3.0
    python scripts/sync_versions.py --show
"""

import re
import sys
from pathlib import Path

# Package locations relative to project root
PACKAGES = {
    "neo-rx": "pyproject.toml",
    "neo-core": "src/neo_core/pyproject.toml",
    "neo-aprs": "src/neo_aprs/pyproject.toml",
    "neo-wspr": "src/neo_wspr/pyproject.toml",
    "neo-adsb": "src/neo_adsb/pyproject.toml",
    "neo-telemetry": "src/neo_telemetry/pyproject.toml",
}

VERSION_PATTERN = re.compile(r'^version\s*=\s*"([^"]+)"', re.MULTILINE)
DEPENDENCY_PATTERN = re.compile(
    r"(neo-(?:core|aprs|wspr|adsb|telemetry)(?:\[[^\]]+\])?)==([0-9.]+)"
)


def find_project_root() -> Path:
    """Find project root by looking for pyproject.toml."""
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / "pyproject.toml").exists():
            return current
        current = current.parent
    raise RuntimeError("Could not find project root with pyproject.toml")


def get_current_versions(root: Path) -> dict[str, str]:
    """Extract current version from each package."""
    versions = {}
    for package, rel_path in PACKAGES.items():
        path = root / rel_path
        if not path.exists():
            print(f"Warning: {path} not found", file=sys.stderr)
            continue
        content = path.read_text()
        match = VERSION_PATTERN.search(content)
        if match:
            versions[package] = match.group(1)
        else:
            print(f"Warning: No version found in {path}", file=sys.stderr)
    return versions


def update_version_in_file(path: Path, new_version: str) -> None:
    """Update version field in a pyproject.toml file."""
    content = path.read_text()

    # Update version field
    updated = VERSION_PATTERN.sub(f'version = "{new_version}"', content)

    # Update dependency versions (neo-core==X.Y.Z -> neo-core==new_version)
    updated = DEPENDENCY_PATTERN.sub(rf"\1=={new_version}", updated)

    path.write_text(updated)


def sync_versions(root: Path, new_version: str) -> None:
    """Update all package versions to new_version."""
    print(f"Updating all packages to version {new_version}...")

    for package, rel_path in PACKAGES.items():
        path = root / rel_path
        if not path.exists():
            print(f"Skipping {package}: {path} not found", file=sys.stderr)
            continue

        update_version_in_file(path, new_version)
        print(f"  ✓ {package}: {rel_path}")

    print(f"\nAll packages synchronized to version {new_version}")


def show_versions(root: Path) -> None:
    """Display current versions for all packages."""
    versions = get_current_versions(root)
    print("Current package versions:")
    for package, version in versions.items():
        print(f"  {package:20s} {version}")

    # Check for version mismatches
    unique_versions = set(versions.values())
    if len(unique_versions) > 1:
        print("\n⚠ Warning: Version mismatch detected!", file=sys.stderr)
        sys.exit(1)
    else:
        print("\n✓ All packages synchronized")


def validate_version(version: str) -> bool:
    """Validate semantic version format."""
    pattern = re.compile(r"^\d+\.\d+\.\d+(?:-[a-zA-Z0-9.]+)?$")
    return bool(pattern.match(version))


def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        sys.exit(1)

    arg = sys.argv[1]
    root = find_project_root()

    if arg == "--show":
        show_versions(root)
    else:
        new_version = arg
        if not validate_version(new_version):
            print(
                f"Error: Invalid version format '{new_version}'. "
                "Expected: X.Y.Z or X.Y.Z-suffix",
                file=sys.stderr,
            )
            sys.exit(1)

        sync_versions(root, new_version)


if __name__ == "__main__":
    main()
