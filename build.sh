#!/bin/bash
set -e

APP_NAME="AutoResponder"
DIST_DIR="dist"
DMG_TMP="$DIST_DIR/dmg_tmp"
DMG_OUT="$DIST_DIR/$APP_NAME.dmg"

echo ">>> Building $APP_NAME.app..."
rm -rf build "$DIST_DIR/$APP_NAME.app" "$DMG_OUT"
.venv/bin/python3 setup.py py2app 2>&1

echo ">>> Creating DMG..."
rm -rf "$DMG_TMP"
mkdir -p "$DMG_TMP"
cp -r "$DIST_DIR/$APP_NAME.app" "$DMG_TMP/"
ln -s /Applications "$DMG_TMP/Applications"

hdiutil create \
    -volname "$APP_NAME" \
    -srcfolder "$DMG_TMP" \
    -ov \
    -format UDZO \
    "$DMG_OUT"

rm -rf "$DMG_TMP"

echo ""
echo "Done! Installer at: $DMG_OUT"
