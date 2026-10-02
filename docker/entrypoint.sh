#!/bin/sh
# Container entrypoint: start a virtual display for the application browser, make it viewable in a web
# browser through noVNC (port 6080), then run the given command (the jobhunt app by default).
#
#   JOBHUNT_VNC=0           skip the display (searching/tracking still work; applying needs it)
#   JOBHUNT_VNC_PASSWORD    ask for this password in the viewer (the port is published to localhost only)
#   JOBHUNT_SCREEN          virtual screen size, default 1366x900x24
set -eu

LOG_DIR=/tmp/jobhunt
export DISPLAY="${DISPLAY:-:99}"
DISPLAY_NUM="${DISPLAY#:}"

start_display() {
    rm -f "/tmp/.X${DISPLAY_NUM}-lock" "/tmp/.X11-unix/X${DISPLAY_NUM}"  # left over from a previous run
    Xvfb "$DISPLAY" -screen 0 "${JOBHUNT_SCREEN:-1366x900x24}" -nolisten tcp >"$LOG_DIR/xvfb.log" 2>&1 &

    tries=0
    until [ -S "/tmp/.X11-unix/X${DISPLAY_NUM}" ]; do
        tries=$((tries + 1))
        if [ "$tries" -gt 100 ]; then
            echo "entrypoint: the virtual display didn't start, see $LOG_DIR/xvfb.log" >&2
            exit 1
        fi
        sleep 0.1
    done

    fluxbox >"$LOG_DIR/fluxbox.log" 2>&1 &
}

start_viewer() {
    auth="-nopw"
    if [ -n "${JOBHUNT_VNC_PASSWORD:-}" ]; then
        pwfile="$LOG_DIR/vncpass"
        (umask 077 && printf '%s\n' "$JOBHUNT_VNC_PASSWORD" >"$pwfile")
        auth="-passwdfile rm:$pwfile"  # x11vnc deletes the file once it has read it
    fi
    # VNC itself only listens inside the container; noVNC (websockify) is the published port
    # shellcheck disable=SC2086  # $auth is deliberately split into separate options
    x11vnc -display "$DISPLAY" -localhost -rfbport 5900 -forever -shared -quiet $auth \
        >"$LOG_DIR/x11vnc.log" 2>&1 &
    websockify --web /usr/share/novnc 6080 127.0.0.1:5900 >"$LOG_DIR/websockify.log" 2>&1 &
}

if [ "${JOBHUNT_VNC:-1}" = "1" ]; then
    mkdir -p "$LOG_DIR"
    start_display
    start_viewer
fi

exec "$@"
