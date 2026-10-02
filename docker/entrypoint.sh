#!/bin/sh
# Starts a virtual display for the application browser and serves it through noVNC
# (http://localhost:6080), then runs the given command (the jobhunt app by default).
set -e

if [ "${JOBHUNT_VNC:-1}" = "1" ] && [ -z "${JOBHUNT_DISPLAY_READY:-}" ]; then
    rm -f /tmp/.X99-lock
    Xvfb :99 -screen 0 "${JOBHUNT_SCREEN:-1366x900x24}" -nolisten tcp >/tmp/xvfb.log 2>&1 &
    i=0
    while [ ! -e /tmp/.X11-unix/X99 ] && [ "$i" -lt 50 ]; do sleep 0.1; i=$((i + 1)); done
    fluxbox >/tmp/fluxbox.log 2>&1 &
    # VNC listens inside the container only; websockify is what gets published (to localhost)
    x11vnc -display :99 -localhost -forever -shared -nopw -quiet -rfbport 5900 >/tmp/x11vnc.log 2>&1 &
    websockify --web /usr/share/novnc 6080 127.0.0.1:5900 >/tmp/websockify.log 2>&1 &
    export JOBHUNT_DISPLAY_READY=1
fi

exec "$@"
