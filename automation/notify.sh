#!/bin/bash
# Show a macOS notification: notify.sh "<title>" "<message>". On other systems it just prints.
set -u
title=${1:-jobhunt}
message=${2:-}
echo "[notify] $title: $message"
if command -v osascript >/dev/null 2>&1; then
  # Pass the text as arguments, so quotes in it can't break the AppleScript
  osascript - "$title" "$message" <<'APPLESCRIPT' >/dev/null 2>&1 || true
on run argv
  display notification (item 2 of argv) with title (item 1 of argv) sound name "default"
end run
APPLESCRIPT
fi
