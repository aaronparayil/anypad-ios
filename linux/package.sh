#!/usr/bin/env bash
# Makes the two Linux downloads from the last commit: AnyPad-Linux-iOS.tar.gz and
# AnyPad-Linux-Android.tar.gz. They hold the same files; the Android one also has a file
# named "phone" that says android.   bash package.sh [output folder, default ../dist]
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")/.."
out="$(readlink -f "${1:-dist}")"
mkdir -p "$out"
stamp=$(git log -1 --format=%ct)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
for phone in iOS Android; do
  name=AnyPad-Linux-$phone
  mkdir "$work/$name"
  git archive HEAD:linux | tar -x -C "$work/$name" --exclude=tests --exclude=package.sh
  git show HEAD:LICENSE > "$work/$name/LICENSE"
  [ "$phone" = Android ] && echo android > "$work/$name/phone"
  touch -d "@$stamp" "$work/$name"/* "$work/$name"
  tar --sort=name --mtime="@$stamp" --owner=0 --group=0 --numeric-owner -C "$work" -cf - "$name" |
    gzip -n -9 > "$out/$name.tar.gz"
  echo "$out/$name.tar.gz"
done
