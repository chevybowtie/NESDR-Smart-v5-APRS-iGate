#!/bin/bash
# Install script for wsprd binary from WSJT-X
# Downloads, extracts, and installs wsprd binary for bundling with neo-igate

set -e

VERSION="2.7.0"
REPO_URL="https://sourceforge.net/projects/wsjt/files/wsjtx-${VERSION}"
TAR_URL="${REPO_URL}/wsjtx_${VERSION}_amd64.deb/download"
TAR_FILE="wsjtx_${VERSION}_amd64.deb"
INSTALL_DIR="$(pwd)/src/neo_igate/wspr/bin"

echo "Downloading WSJT-X v${VERSION}..."

# Download
curl -L "${TAR_URL}" -o "${TAR_FILE}"

# Extract deb
ar x "${TAR_FILE}"
tar -xzf data.tar.gz

# Copy wsprd
mkdir -p "${INSTALL_DIR}"
cp -f ./usr/bin/wsprd "${INSTALL_DIR}/"

echo "wsprd binary installed to ${INSTALL_DIR}/wsprd"

# Cleanup all downloaded and extracted files
rm -rf "${TAR_FILE}" data.tar.gz control.tar.gz debian-binary usr

echo "wsprd installed successfully."