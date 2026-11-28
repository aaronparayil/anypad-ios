#!/usr/bin/env bash
# Adds AnyPad to your applications menu (for you only).
#   bash install-app.sh             AnyPad for iPhone and iPad
#   bash install-app.sh --android   AnyPad for Android
#   bash install-app.sh --remove    removes both
# A file named "phone" holding "android" next to this one makes --android the default.
set -euo pipefail
HERE="$(dirname "$(readlink -f "$0")")"
APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
IOS="$APPS/io.github.aaronparayil.anypad.desktop"
ANDROID="$APPS/io.github.aaronparayil.anypad-android.desktop"
phone=ios
[ "$(cat "$HERE/phone" 2> /dev/null)" = android ] && phone=android
case "${1:-}" in
  --remove) rm -f "$IOS" "$ANDROID"; echo "Removed AnyPad from the menu."; exit 0 ;;
  --android) phone=android ;;
  --ios) phone=ios ;;
  "") ;;
  *) echo "usage: bash install-app.sh [--ios | --android | --remove]"; exit 2 ;;
esac
mkdir -p "$APPS"
if [ "$phone" = android ]; then
  file=$ANDROID name="AnyPad for Android" what="your Android phone or tablet" words="android;"
else
  file=$IOS name="AnyPad for iPhone and iPad" what="your iPhone or iPad" words="iphone;ipad;"
fi
cat > "$file" <<END
[Desktop Entry]
Type=Application
Name=$name
Comment=Use any gamepad with $what
Exec=/usr/bin/python3 "$HERE/anypad.py" --$phone
Icon=$HERE/anypad.png
Categories=Game;Utility;
Keywords=gamepad;controller;bluetooth;$words
END
echo "$name is in your applications menu. Keep this folder where it is: $HERE"
