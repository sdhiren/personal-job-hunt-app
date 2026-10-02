"""One interface, two ways to reach Claude.

* account — your Claude Pro/Max subscription, through the locally installed Claude Code CLI
            (`claude -p`, headless). Login happens in Claude Code itself (`claude auth login`);
            this app never sees your password or tokens.
* api_key — the Anthropic API with a key from console.anthropic.com (billed per token).

Both expose `structured(prompt, schema, system, web=False)` -> dict that matches `schema`.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime

from .config import DATA_DIR, settings

log = logging.getLogger(__name__)


class ClaudeError(RuntimeError):
    pass


class ClaudeNotConfigured(ClaudeError):
    pass


class ClaudeUsageLimit(ClaudeError):
    """The plan's or API account's limit is used up: further calls fail until `resets`."""

    def __init__(self, reason: str, resets: str | None = None):
        super().__init__(f"{reason} · resets {resets}" if resets else reason)
        self.reason = reason
        self.resets = resets

    def as_dict(self) -> dict:
        return {"reason": self.reason, "resets": self.resets}


_LIMIT_RE = re.compile(
    r"hit your (?:[\w-]+ )?limit|usage limit|out of extra usage|credit balance (?:is )?too low|rate.?limit", re.I
)
_RESETS_RE = re.compile(r"resets?\s+(?:at\s+)?(.+)", re.I)
_EPOCH_RE = re.compile(r"\|(\d{10})\b")


def usage_limit_from(message: str) -> ClaudeUsageLimit | None:
    """Recognise Claude Code's limit messages, e.g.
    "You've hit your session limit · resets 5:10pm (Asia/Calcutta)" or "Claude AI usage limit reached|1759411200"."""
    message = message.strip()
    if not _LIMIT_RE.search(message):
        return None
    epoch = _EPOCH_RE.search(message)
    if epoch:
        resets = datetime.fromtimestamp(int(epoch.group(1))).strftime("%-I:%M%p on %d %b").replace("AM", "am")
        return ClaudeUsageLimit(message[: epoch.start()].strip(), resets.replace("PM", "pm"))
    reason, sep, rest = message.partition("·")
    resets = _RESETS_RE.search(rest if sep else message)
    return ClaudeUsageLimit((reason if sep else message).strip(" ."), resets.group(1).strip() if resets else None)


# ---------------------------------------------------------------- Claude account (Claude Code CLI)


def cli_path() -> str | None:
    return shutil.which("claude") or next(
        (
            p
            for p in [
                os.path.expanduser("~/.local/bin/claude"),
                os.path.expanduser("~/.claude/local/claude"),
                "/usr/local/bin/claude",
                "/opt/homebrew/bin/claude",
            ]
            if os.path.exists(p)
        ),
        None,
    )


def _cli_env() -> dict:
    env = dict(os.environ)
    # an API key in the environment would take precedence over the subscription login
    for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        env.pop(k, None)
    return env


def account_status() -> dict:
    exe = cli_path()
    if not exe:
        return {"installed": False, "loggedIn": False}
    try:
        out = subprocess.run(
            [exe, "auth", "status", "--json"], capture_output=True, text=True, timeout=30, env=_cli_env()
        )
        data = json.loads(out.stdout or "{}")
    except Exception as e:
        return {"installed": True, "loggedIn": False, "error": str(e)}
    return {"installed": True, **{k: data.get(k) for k in ("loggedIn", "authMethod", "email", "subscriptionType")}}


def start_account_login() -> str:
    """Open a terminal running `claude auth login` (browser-based sign-in)."""
    exe = cli_path()
    if not exe:
        raise ClaudeError("Claude Code is not installed. Install it from https://claude.com/claude-code first.")
    if os.environ.get("JOBHUNT_IN_DOCKER"):
        return "Run `make docker-claude-login` in a terminal on your computer, then click Refresh."
    cmd = f"'{exe}' auth login --claudeai"
    if sys.platform == "darwin":
        subprocess.Popen(
            [
                "osascript",
                "-e",
                f'tell application "Terminal" to do script "{cmd}"',
                "-e",
                'tell application "Terminal" to activate',
            ]
        )
        return "A Terminal window opened. Finish signing in in your browser, then click Refresh."
    return f"Run this in a terminal, then click Refresh:  {cmd}"


class AccountBackend:
    name = "Claude account"

    def __init__(self, model: str = ""):
        self.exe = cli_path()
        if not self.exe:
            raise ClaudeNotConfigured("Claude Code CLI not found")
        self.model = model
        self.workdir = DATA_DIR / "claude-work"  # neutral cwd: no project CLAUDE.md / settings
        self.workdir.mkdir(parents=True, exist_ok=True)

    def structured(self, prompt: str, schema: dict, system: str, web: bool = False, timeout: int = 900) -> dict:
        tools = "WebSearch,WebFetch" if web else ""
        args = [
            self.exe,
            "-p",
            "--output-format",
            "json",
            "--json-schema",
            json.dumps(schema),
            "--no-session-persistence",
            "--strict-mcp-config",
            "--setting-sources",
            "",
            "--disable-slash-commands",
            "--system-prompt",
            system,
            "--tools",
            tools,
            "--effort",
            "medium" if web else "low",
        ]
        if web:
            args += ["--allowedTools", tools]
        if self.model:
            args += ["--model", self.model]
        try:
            proc = subprocess.run(
                args, input=prompt, capture_output=True, text=True, timeout=timeout, cwd=self.workdir, env=_cli_env()
            )
        except subprocess.TimeoutExpired as e:
            raise ClaudeError("Claude Code timed out") from e
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError as e:
            message = (proc.stderr or proc.stdout or "no output from claude")[:500]
            raise usage_limit_from(message) or ClaudeError(message) from e
        if data.get("is_error") or data.get("structured_output") is None:
            message = str(data.get("result") or data.get("subtype") or "Claude Code returned an error")[:500]
            raise usage_limit_from(message) or ClaudeError(message)
        return data["structured_output"]


# ---------------------------------------------------------------- API key


class ApiBackend:
    name = "API key"

    def __init__(self, api_key: str, model: str = "claude-opus-5"):
        import anthropic

        if not api_key:
            raise ClaudeNotConfigured("No API key saved")
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model or "claude-opus-5"

    def structured(self, prompt: str, schema: dict, system: str, web: bool = False, timeout: int = 420) -> dict:
        import anthropic

        try:
            if web:
                return self._structured_with_search(prompt, schema, system)
            return self._structured(prompt, schema, system)
        except anthropic.RateLimitError as e:  # still limited after the SDK's own retries
            retry_after = e.response.headers.get("retry-after")
            raise ClaudeUsageLimit(
                "Anthropic API rate limit reached", f"in about {retry_after}s" if retry_after else None
            ) from e
        except anthropic.BadRequestError as e:
            if "credit balance" in str(e).lower():
                raise ClaudeUsageLimit("Anthropic API credit balance is too low") from e
            raise

    def _structured(self, prompt: str, schema: dict, system: str) -> dict:
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=16000,
            system=system,
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
            messages=[{"role": "user", "content": prompt}],
        )
        if resp.stop_reason == "refusal":
            raise ClaudeError("Claude declined this request")
        text = next((b.text for b in resp.content if b.type == "text"), "")
        return json.loads(text)

    def _structured_with_search(self, prompt: str, schema: dict, system: str) -> dict:
        """Web search (server tool), then hand the result back through a strict `submit` tool."""
        submit = {
            "name": "submit",
            "description": "Submit the final result. Call exactly once, at the end.",
            "input_schema": schema,
            "strict": True,
        }
        tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": 8}, submit]
        messages = [{"role": "user", "content": prompt + "\n\nWhen done, call the `submit` tool with the result."}]
        for _ in range(8):
            with self.client.messages.stream(
                model=self.model,
                max_tokens=32000,
                system=system,
                tools=tools,
                output_config={"effort": "medium"},
                messages=messages,
            ) as stream:
                resp = stream.get_final_message()
            for block in resp.content:
                if block.type == "tool_use" and block.name == "submit":
                    return block.input
            if resp.stop_reason == "refusal":
                raise ClaudeError("Claude declined this request")
            messages.append({"role": "assistant", "content": resp.content})
            if resp.stop_reason != "pause_turn":
                messages.append({"role": "user", "content": "Call the `submit` tool now with what you found."})
        raise ClaudeError("Claude did not return a result")

    def test(self) -> str:
        self.client.models.retrieve(self.model)
        return f"API key works ({self.model})"


# ---------------------------------------------------------------- selection


def backend():
    s = settings()
    mode = s["claude_mode"]
    if mode == "api_key":
        return ApiBackend(s.get("api_key") or os.environ.get("ANTHROPIC_API_KEY", ""), s.get("api_model"))
    if mode == "account":
        return AccountBackend(s.get("cli_model", ""))
    raise ClaudeNotConfigured("Claude is turned off in Settings")


def status() -> dict:
    s = settings()
    out = {
        "mode": s["claude_mode"],
        "account": account_status(),
        "api_key_saved": bool(s.get("api_key")),
        "api_key_hint": _mask(s.get("api_key", "")),
        "api_model": s.get("api_model"),
        "cli_model": s.get("cli_model", ""),
    }
    out["ready"] = (s["claude_mode"] == "account" and bool(out["account"].get("loggedIn"))) or (
        s["claude_mode"] == "api_key" and out["api_key_saved"]
    )
    return out


def _mask(key: str) -> str:
    return f"{key[:7]}…{key[-4:]}" if len(key) > 12 else ""
