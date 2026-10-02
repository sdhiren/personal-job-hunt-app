#!/bin/bash
# Daily "your TODO list is empty" reminder for macOS. It doesn't use Claude.
#
#   automation/reminder.sh install     # set it up (a LaunchAgent; runs at login and every 15 minutes)
#   automation/reminder.sh uninstall   # remove it
#   automation/reminder.sh status      # show pending items and when you were last reminded
#   automation/reminder.sh run         # what the LaunchAgent runs: remind at most once a day
#
# macOS doesn't let background jobs read the Desktop/Documents folders, so `install` copies this script to
# ~/Library/Application Support/jobhunt/ and keeps a small read-only clone of the repository there, updated
# from GitHub with your existing git/SSH access.
set -u

LABEL=com.jobhunt.todo-reminder
SUPPORT="$HOME/Library/Application Support/jobhunt"
MIRROR="$SUPPORT/repo"
STAMP="$SUPPORT/reminder-last-date"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$HOME/Library/Logs/jobhunt-reminder.log"
HERE="$(cd "$(dirname "$0")" && pwd)"

# Pending items in a TODO.md, ignoring the template inside ``` code blocks
count_pending() {
  awk '/^```/ { fence = !fence; next } !fence && /^- \*\*Status:\*\* *pending/ { n++ } END { print n + 0 }' "$1"
}

notify() { "$SUPPORT/notify.sh" "$1" "$2"; }

refresh_mirror() {
  git -C "$MIRROR" fetch -q --depth 1 origin main 2>>"$LOG" && git -C "$MIRROR" reset -q --hard origin/main 2>>"$LOG"
}

run() {
  local today
  today=$(date +%F)
  [ "$(cat "$STAMP" 2>/dev/null)" = "$today" ] && exit 0  # already reminded today
  if ! refresh_mirror; then
    echo "$(date '+%F %T') couldn't update the TODO list from GitHub; using the last copy" >>"$LOG"
  fi
  if [ ! -f "$MIRROR/TODO.md" ]; then
    echo "$(date '+%F %T') no TODO.md yet" >>"$LOG"
    exit 0
  fi
  local pending
  pending=$(count_pending "$MIRROR/TODO.md")
  echo "$(date '+%F %T') pending items: $pending" >>"$LOG"
  if [ "$pending" -eq 0 ]; then
    notify "jobhunt: TODO list is empty" "Add items to TODO.md so the 1 PM run has something to work on."
    echo "$today" >"$STAMP"
  fi
}

install() {
  local repo origin
  repo="$(cd "$HERE/.." && pwd)"
  origin=$(git -C "$repo" remote get-url origin) || { echo "No git remote 'origin' in $repo"; exit 1; }
  mkdir -p "$SUPPORT" "$HOME/Library/LaunchAgents" "$(dirname "$LOG")"
  cp "$HERE/reminder.sh" "$HERE/notify.sh" "$SUPPORT/"
  chmod +x "$SUPPORT/reminder.sh" "$SUPPORT/notify.sh"
  if [ ! -d "$MIRROR/.git" ]; then
    git clone -q --depth 1 --branch main "$origin" "$MIRROR" || { echo "Couldn't clone $origin"; exit 1; }
  fi
  cat >"$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array><string>/bin/bash</string><string>$SUPPORT/reminder.sh</string><string>run</string></array>
  <key>RunAtLoad</key><true/>
  <key>StartInterval</key><integer>900</integer>
  <key>StandardOutPath</key><string>$LOG</string>
  <key>StandardErrorPath</key><string>$LOG</string>
</dict>
</plist>
PLIST
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$PLIST"
  echo "Installed. You'll be reminded at most once a day (after login or wake) while TODO.md has no pending items."
  echo "Log: $LOG"
}

uninstall() {
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
  rm -f "$PLIST"
  rm -rf "$SUPPORT"
  echo "Removed the reminder."
}

status() {
  local file="$HERE/../TODO.md"
  echo "Pending items in TODO.md: $(count_pending "$file")"
  echo "Last reminded: $(cat "$STAMP" 2>/dev/null || echo never)"
  launchctl print "gui/$(id -u)/$LABEL" >/dev/null 2>&1 && echo "Reminder: installed" || echo "Reminder: not installed"
}

case "${1:-}" in
  run) run ;;
  install) install ;;
  uninstall) uninstall ;;
  status) status ;;
  *) echo "usage: $0 install|uninstall|status|run"; exit 2 ;;
esac
