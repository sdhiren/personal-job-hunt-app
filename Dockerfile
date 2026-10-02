# jobhunt app image: Python + Chromium (from Microsoft's Playwright image) on a virtual display you can
# watch and use through noVNC, plus optionally the Claude Code CLI for the "Claude account" connection.
#
# The Playwright pip package must match the browsers baked into the base image, so both use this version.
ARG PLAYWRIGHT_VERSION=1.63.0
FROM mcr.microsoft.com/playwright/python:v${PLAYWRIGHT_VERSION}-noble

ARG PLAYWRIGHT_VERSION
ARG INSTALL_CLAUDE_CODE=1
ARG UID=1000

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    VIRTUAL_ENV=/opt/venv \
    JOBHUNT_HOME=/app \
    JOBHUNT_HOST=0.0.0.0 \
    JOBHUNT_IN_DOCKER=1 \
    JOBHUNT_BROWSER_PROFILE=/home/app/browser-profile \
    CLAUDE_CONFIG_DIR=/home/app/.claude \
    DISPLAY=:99 \
    PATH=/home/app/.local/bin:/opt/venv/bin:$PATH

# Virtual display (Xvfb ships with the base image), a window manager, VNC and the noVNC web viewer
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3.12-venv tini fluxbox x11vnc novnc websockify \
    && rm -rf /var/lib/apt/lists/*

# The base image's `ubuntu` user holds UID 1000; free it so files in ./data match a typical host user
RUN userdel --remove ubuntu 2>/dev/null || true \
    && useradd --create-home --uid "${UID}" app \
    && python3 -m venv "${VIRTUAL_ENV}" \
    && mkdir -p /app/data /home/app/browser-profile /home/app/.claude \
    && chown -R app:app /app /home/app "${VIRTUAL_ENV}"

USER app
WORKDIR /app

RUN if [ "${INSTALL_CLAUDE_CODE}" = "1" ]; then \
        curl -fsSL https://claude.ai/install.sh -o /tmp/install-claude.sh \
        && bash /tmp/install-claude.sh \
        && rm /tmp/install-claude.sh \
        && claude --version; \
    fi

# Dependencies first, so code changes don't reinstall them
COPY --chown=app:app pyproject.toml README.md ./
RUN mkdir jobhunt && touch jobhunt/__init__.py \
    && pip install "playwright==${PLAYWRIGHT_VERSION}" . \
    && pip uninstall -y jobhunt \
    && rm -rf jobhunt

COPY --chown=app:app config ./config
COPY --chown=app:app jobhunt ./jobhunt
RUN pip install --no-deps .

COPY --chmod=755 docker/entrypoint.sh /usr/local/bin/jobhunt-entrypoint

EXPOSE 8765 6080
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8765/ >/dev/null || exit 1

ENTRYPOINT ["tini", "--", "jobhunt-entrypoint"]
CMD ["jobhunt", "app", "--no-open"]
