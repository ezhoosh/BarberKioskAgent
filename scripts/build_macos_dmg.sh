#!/usr/bin/env bash
set -euo pipefail

# Build a drag-and-drop DMG for BarberAgent.app with a styled Finder window (background + icon layout),
# similar to most macOS apps. Uses only built-in tools: hdiutil + osascript.
# Output: dist/BarberAgent.dmg
#
# Usage:
#   cd BarberKioskAgent
#   ./scripts/build_macos_dmg.sh
#
# Prereqs:
#   - dist/BarberAgent.app already exists (build via: pyinstaller BarberAgent.spec)

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "ERROR: This script must be run on macOS."
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="${ROOT_DIR}/dist"
APP_NAME="BarberAgent"
APP_BUNDLE="${DIST_DIR}/${APP_NAME}.app"
DMG_OUT="${DIST_DIR}/${APP_NAME}.dmg"

if [[ ! -d "${APP_BUNDLE}" ]]; then
  echo "ERROR: ${APP_BUNDLE} not found."
  echo "Build it first:"
  echo "  cd BarberKioskAgent && pyinstaller BarberAgent.spec"
  exit 1
fi

STAGING_DIR="$(mktemp -d "/tmp/${APP_NAME}-dmg.XXXXXX")"
cleanup() {
  rm -rf "${STAGING_DIR}" || true
}
trap cleanup EXIT

echo "Staging DMG contents in: ${STAGING_DIR}"
cp -R "${APP_BUNDLE}" "${STAGING_DIR}/"

# Standard Applications shortcut
ln -s /Applications "${STAGING_DIR}/Applications"

# NOTE:
# We intentionally do NOT use a DMG background image, because that requires a ".background" folder.
# If the user's Finder is configured to show hidden files, ".background" becomes visible.
# A clean drag-and-drop DMG (app + Applications shortcut) matches typical installers without exposing extra files.

# In CI (GitHub Actions), Finder scripting/mount+detach is flaky and can fail with "Resource busy".
# Create a simple compressed DMG directly without mounting/styling.
if [[ "${GITHUB_ACTIONS:-}" == "true" ]]; then
  rm -f "${DMG_OUT}" || true
  APP_SIZE_MB="$(du -sm "${APP_BUNDLE}" | awk '{print $1}')"
  DMG_SIZE_MB="$((APP_SIZE_MB + 50))"
  echo "GITHUB_ACTIONS=true -> creating DMG without mounting/styling: ${DMG_OUT}"
  hdiutil create \
    -volname "${APP_NAME}" \
    -srcfolder "${STAGING_DIR}" \
    -ov \
    -format UDZO \
    -size "${DMG_SIZE_MB}m" \
    "${DMG_OUT}"
  echo "DMG created: ${DMG_OUT}"
  exit 0
fi

# Create DMG (read-write first so we can style it)
rm -f "${DMG_OUT}" || true

# Size heuristic (adds 50MB headroom)
APP_SIZE_MB="$(du -sm "${APP_BUNDLE}" | awk '{print $1}')"
DMG_SIZE_MB="$((APP_SIZE_MB + 50))"

RW_DMG="${DIST_DIR}/${APP_NAME}-rw.dmg"
rm -f "${RW_DMG}" || true

echo "Creating RW DMG (${DMG_SIZE_MB}MB): ${RW_DMG}"
hdiutil create -ov -format UDRW -size "${DMG_SIZE_MB}m" -volname "${APP_NAME}" -srcfolder "${STAGING_DIR}" "${RW_DMG}"

MOUNT_DIR="$(mktemp -d "/tmp/${APP_NAME}-mnt.XXXXXX")"
echo "Mounting DMG to: ${MOUNT_DIR}"
hdiutil attach -readwrite -noverify -nobrowse -mountpoint "${MOUNT_DIR}" "${RW_DMG}" >/dev/null

# Style Finder window via AppleScript
echo "Styling DMG Finder window..."
osascript <<EOF || true
tell application "Finder"
  activate
  set dmgFolder to (POSIX file "${MOUNT_DIR}") as alias
  open dmgFolder
  delay 1
  set theWindow to container window of dmgFolder
  set current view of theWindow to icon view
  set viewOptions to the icon view options of theWindow
  set arrangement of viewOptions to not arranged
  set icon size of viewOptions to 128
  delay 0.5
  try
    set position of item "${APP_NAME}" of dmgFolder to {190, 250}
  end try
  try
    set position of item "${APP_NAME}.app" of dmgFolder to {190, 250}
  end try
  try
    set position of item "Applications" of dmgFolder to {610, 250}
  end try
  try
    close theWindow
  end try
end tell
EOF

sync
echo "Detaching DMG..."
detach_ok=false
for i in 1 2 3 4 5; do
  if hdiutil detach "${MOUNT_DIR}" >/dev/null 2>&1; then
    detach_ok=true
    break
  fi
  # Retry with force (Finder/Spotlight can keep the mount busy briefly)
  hdiutil detach -force "${MOUNT_DIR}" >/dev/null 2>&1 || true
  sleep 1
done
if [[ "${detach_ok}" != "true" ]]; then
  echo "WARNING: Could not detach DMG cleanly (resource busy). Trying diskutil force unmount..."
  diskutil unmount force "${MOUNT_DIR}" >/dev/null 2>&1 || true
fi
rm -rf "${MOUNT_DIR}" || true

# Convert to compressed read-only DMG
echo "Creating final compressed DMG: ${DMG_OUT}"
hdiutil convert "${RW_DMG}" -format UDZO -imagekey zlib-level=9 -ov -o "${DMG_OUT}" >/dev/null
rm -f "${RW_DMG}" || true

echo "DMG created: ${DMG_OUT}"

