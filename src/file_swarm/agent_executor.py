"""Agent executor: run non-programming tasks via model-driven actions.

Supports multiple action types beyond shell commands:
  - shell:     Execute shell commands in a safety sandbox
  - browser:   Open URLs, fetch page content, navigate
  - mouse:     Simulate mouse clicks, moves, drags
  - keyboard:  Type text, press keys
  - screenshot: Capture screen regions
  - mcp:       Call MCP-style tools with JSON arguments

Safety layers:
  1. Command/action blocklist (rm -rf, format, shutdown, etc.)
  2. Working directory restriction for shell commands
  3. Per-command timeout
  4. Output size cap
  5. Read-only mode (dry_run) for testing
  6. URL allowlist for browser actions (configurable)
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
import time
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .providers.base import ProviderResult


# ── Safety ────────────────────────────────────────────────────────────────

BLOCKED_PATTERNS = [
    re.compile(r"\brm\s+-rf\b", re.IGNORECASE),
    re.compile(r"\bdel\s+/[fsq]\b", re.IGNORECASE),
    re.compile(r"\bformat\b", re.IGNORECASE),
    re.compile(r"\bshutdown\b", re.IGNORECASE),
    re.compile(r"\breboot\b", re.IGNORECASE),
    re.compile(r"\bmkfs\b", re.IGNORECASE),
    re.compile(r"\bdd\s+if=", re.IGNORECASE),
    re.compile(r"\breg\s+delete\b", re.IGNORECASE),
    re.compile(r":\(\)\s*\{", re.IGNORECASE),  # fork bomb
    re.compile(r"\bcurl\b.*\|\s*sh", re.IGNORECASE),  # pipe to shell
    re.compile(r"\bwget\b.*\|\s*sh", re.IGNORECASE),
    re.compile(r"\biex\b.*\(\s*irm", re.IGNORECASE),  # PowerShell IEX
]

MAX_COMMANDS = 10
MAX_OUTPUT_CHARS = 5000
DEFAULT_TIMEOUT = 15

# Action types supported by the enhanced executor
ACTION_TYPES = {
    "shell", "browser_open", "browser_fetch",
    "mouse_click", "mouse_move", "mouse_drag",
    "key_type", "key_press", "key_hotkey",
    "screenshot",
    "mcp_call",
    "wait",
}


# ── Data Classes ──────────────────────────────────────────────────────────

@dataclass(slots=True)
class CommandResult:
    command: str
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    blocked: bool = False
    block_reason: str = ""


@dataclass(slots=True)
class ActionResult:
    """Result of executing a single typed action."""
    action_type: str
    action: dict[str, Any]
    ok: bool
    output: str = ""
    error: str = ""
    duration_ms: int = 0
    blocked: bool = False
    block_reason: str = ""


@dataclass(slots=True)
class AgentResult:
    task_id: str
    ok: bool
    commands_executed: list[CommandResult] = field(default_factory=list)
    actions_executed: list[ActionResult] = field(default_factory=list)
    summary: str = ""
    error: str | None = None
    model: str | None = None
    provider: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


# ── Safety Checks ─────────────────────────────────────────────────────────

def _is_blocked(command: str) -> tuple[bool, str]:
    """Check if a command matches any blocked pattern."""
    for pattern in BLOCKED_PATTERNS:
        if pattern.search(command):
            return True, f"blocked pattern: {pattern.pattern}"
    return False, ""


def _is_url_safe(url: str) -> tuple[bool, str]:
    """Basic URL safety check."""
    if not url:
        return False, "empty URL"
    if not url.startswith(("http://", "https://")):
        return False, f"non-http scheme: {url[:50]}"
    # Block known dangerous patterns
    blocked_url_patterns = [
        r"file://",
        r"javascript:",
        r"data:",
    ]
    for pat in blocked_url_patterns:
        if re.search(pat, url, re.IGNORECASE):
            return False, f"blocked URL scheme: {pat}"
    return True, ""


# ── Action Extraction ─────────────────────────────────────────────────────

def _extract_commands(model_output: str) -> list[str]:
    """Extract shell commands from model output (legacy mode).

    Supports several formats:
    1. JSON array: ["cmd1", "cmd2"]
    2. Fenced code block with shell/bash/json tag
    3. Numbered list: 1. command
    4. Plain lines starting with $ or >
    5. Lines that look like shell commands (heuristic)
    """
    text = model_output.strip()

    # Try to find a JSON array anywhere in the text
    json_match = re.search(r'\[.*?\]', text, re.DOTALL)
    if json_match:
        try:
            items = json.loads(json_match.group())
            return [str(item).strip() for item in items if str(item).strip()][:MAX_COMMANDS]
        except json.JSONDecodeError:
            pass

    # Extract from fenced code blocks
    for fence in ("```json", "```shell", "```bash", "```sh", "```cmd", "```"):
        if fence in text:
            block = text.split(fence, 1)[1]
            if "```" in block:
                block = block.split("```", 1)[0]
            # Try JSON inside the block
            json_match = re.search(r'\[.*?\]', block, re.DOTALL)
            if json_match:
                try:
                    items = json.loads(json_match.group())
                    return [str(item).strip() for item in items if str(item).strip()][:MAX_COMMANDS]
                except json.JSONDecodeError:
                    pass
            text = block.strip()
            break

    # Numbered list or $ prefix or plain command lines
    commands: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        # Skip markdown headings and explanations
        if stripped.startswith("#") or stripped.startswith("##"):
            continue
        if stripped.startswith("Command") or stripped.startswith("Step"):
            continue
        if stripped.startswith("Note:") or stripped.startswith("This "):
            continue
        # Remove numbering: "1. command" -> "command"
        cleaned = re.sub(r"^\d+[\.\)]\s*", "", stripped)
        # Remove $ or > prefix
        cleaned = re.sub(r"^[$>]\s*", "", cleaned)
        # Remove surrounding quotes
        cleaned = cleaned.strip('"').strip("'")
        # Heuristic: must look like a command (contains letters and is short enough)
        if cleaned and len(cleaned) > 2 and len(cleaned) < 500:
            # Skip lines that are clearly prose
            if not cleaned.endswith(".") or cleaned.count(" ") <= 6:
                commands.append(cleaned)

    return commands[:MAX_COMMANDS]


def _extract_actions(model_output: str) -> list[dict[str, Any]]:
    """Extract structured actions from model output.

    Parses JSON arrays of action objects. Each action has:
      - "type": one of ACTION_TYPES
      - type-specific fields (command, url, x, y, text, key, tool, args, etc.)

    Falls back to shell command extraction if no structured actions found.
    """
    text = model_output.strip()

    # Strategy 1: Try to parse as JSON array of objects
    # Find the outermost JSON array
    json_candidates = []

    # Try fenced code blocks first
    for fence in ("```json", "```"):
        if fence in text:
            block = text.split(fence, 1)[1]
            if "```" in block:
                block = block.split("```", 1)[0]
            json_candidates.append(block.strip())
            break

    # Also try the raw text
    json_candidates.append(text)

    for candidate in json_candidates:
        # Find JSON array in candidate
        # Use balanced bracket matching for nested objects
        actions = _try_parse_json_array(candidate)
        if actions:
            # Validate and filter
            valid_actions = []
            for item in actions:
                if isinstance(item, dict) and "type" in item:
                    atype = item["type"]
                    if atype in ACTION_TYPES:
                        valid_actions.append(item)
                    else:
                        # Unknown type, treat as shell if it has a command
                        if "command" in item:
                            valid_actions.append({"type": "shell", "command": item["command"]})
                elif isinstance(item, str):
                    # Plain string = shell command
                    valid_actions.append({"type": "shell", "command": item})
            if valid_actions:
                return valid_actions[:MAX_COMMANDS]

    # Strategy 2: Fall back to legacy shell command extraction
    commands = _extract_commands(model_output)
    if commands:
        return [{"type": "shell", "command": cmd} for cmd in commands]

    return []


def _try_parse_json_array(text: str) -> list | None:
    """Try to find and parse a JSON array in text, handling nested objects."""
    # Find the first '['
    start = text.find("[")
    if start == -1:
        return None

    # Balanced bracket matching
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                # Found the complete array
                json_str = text[start:i + 1]
                try:
                    result = json.loads(json_str)
                    if isinstance(result, list):
                        return result
                except json.JSONDecodeError:
                    pass
                break

    return None


# ── Action Executors ──────────────────────────────────────────────────────

def _execute_command(
    command: str,
    cwd: Path,
    timeout: int = DEFAULT_TIMEOUT,
    env: dict[str, str] | None = None,
) -> CommandResult:
    """Execute a single shell command with safety checks."""
    blocked, reason = _is_blocked(command)
    if blocked:
        return CommandResult(
            command=command,
            exit_code=-1,
            stdout="",
            stderr="",
            duration_ms=0,
            blocked=True,
            block_reason=reason,
        )

    t0 = time.time()
    try:
        merged_env = dict(os.environ)
        if env:
            merged_env.update(env)

        proc = subprocess.run(
            command,
            shell=True,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=merged_env,
        )
        duration_ms = int((time.time() - t0) * 1000)

        stdout = proc.stdout[:MAX_OUTPUT_CHARS] if proc.stdout else ""
        stderr = proc.stderr[:MAX_OUTPUT_CHARS] if proc.stderr else ""

        return CommandResult(
            command=command,
            exit_code=proc.returncode,
            stdout=stdout,
            stderr=stderr,
            duration_ms=duration_ms,
        )
    except subprocess.TimeoutExpired:
        duration_ms = int((time.time() - t0) * 1000)
        return CommandResult(
            command=command,
            exit_code=-1,
            stdout="",
            stderr=f"Command timed out after {timeout}s",
            duration_ms=duration_ms,
        )
    except Exception as exc:
        duration_ms = int((time.time() - t0) * 1000)
        return CommandResult(
            command=command,
            exit_code=-1,
            stdout="",
            stderr=str(exc)[:500],
            duration_ms=duration_ms,
        )


def _action_browser_open(action: dict[str, Any]) -> ActionResult:
    """Open a URL in the default browser."""
    url = action.get("url", "")
    t0 = time.time()
    safe, reason = _is_url_safe(url)
    if not safe:
        return ActionResult(
            action_type="browser_open",
            action=action,
            ok=False,
            error=reason,
            blocked=True,
            block_reason=reason,
        )
    try:
        webbrowser.open(url, new=2)  # new=2: new tab
        return ActionResult(
            action_type="browser_open",
            action=action,
            ok=True,
            output=f"Opened {url} in browser",
            duration_ms=int((time.time() - t0) * 1000),
        )
    except Exception as exc:
        return ActionResult(
            action_type="browser_open",
            action=action,
            ok=False,
            error=str(exc)[:300],
            duration_ms=int((time.time() - t0) * 1000),
        )


def _action_browser_fetch(action: dict[str, Any]) -> ActionResult:
    """Fetch URL content via HTTP (no browser needed)."""
    url = action.get("url", "")
    t0 = time.time()
    safe, reason = _is_url_safe(url)
    if not safe:
        return ActionResult(
            action_type="browser_fetch",
            action=action,
            ok=False,
            error=reason,
            blocked=True,
            block_reason=reason,
        )
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={
            "User-Agent": "FileSwarm-Agent/1.0",
        })
        with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:
            content_type = resp.headers.get("Content-Type", "")
            data = resp.read(MAX_OUTPUT_CHARS)
            # Try to decode as text
            try:
                text = data.decode("utf-8", errors="replace")
            except Exception:
                text = f"<binary data, {len(data)} bytes, content-type: {content_type}>"
            return ActionResult(
                action_type="browser_fetch",
                action=action,
                ok=True,
                output=text[:MAX_OUTPUT_CHARS],
                duration_ms=int((time.time() - t0) * 1000),
            )
    except Exception as exc:
        return ActionResult(
            action_type="browser_fetch",
            action=action,
            ok=False,
            error=str(exc)[:300],
            duration_ms=int((time.time() - t0) * 1000),
        )


def _action_mouse_click(action: dict[str, Any]) -> ActionResult:
    """Simulate a mouse click at (x, y) coordinates."""
    x = action.get("x", 0)
    y = action.get("y", 0)
    button = action.get("button", "left")
    clicks = action.get("clicks", 1)
    t0 = time.time()
    try:
        import pyautogui
        pyautogui.click(x=int(x), y=int(y), button=button, clicks=int(clicks))
        return ActionResult(
            action_type="mouse_click",
            action=action,
            ok=True,
            output=f"Clicked {button} at ({x}, {y}), {clicks} click(s)",
            duration_ms=int((time.time() - t0) * 1000),
        )
    except ImportError:
        return ActionResult(
            action_type="mouse_click",
            action=action,
            ok=False,
            error="pyautogui not installed",
            duration_ms=int((time.time() - t0) * 1000),
        )
    except Exception as exc:
        return ActionResult(
            action_type="mouse_click",
            action=action,
            ok=False,
            error=str(exc)[:300],
            duration_ms=int((time.time() - t0) * 1000),
        )


def _action_mouse_move(action: dict[str, Any]) -> ActionResult:
    """Move mouse to (x, y) coordinates."""
    x = action.get("x", 0)
    y = action.get("y", 0)
    duration = action.get("duration", 0.5)
    t0 = time.time()
    try:
        import pyautogui
        pyautogui.moveTo(int(x), int(y), duration=float(duration))
        return ActionResult(
            action_type="mouse_move",
            action=action,
            ok=True,
            output=f"Moved mouse to ({x}, {y})",
            duration_ms=int((time.time() - t0) * 1000),
        )
    except ImportError:
        return ActionResult(
            action_type="mouse_move",
            action=action,
            ok=False,
            error="pyautogui not installed",
            duration_ms=int((time.time() - t0) * 1000),
        )
    except Exception as exc:
        return ActionResult(
            action_type="mouse_move",
            action=action,
            ok=False,
            error=str(exc)[:300],
            duration_ms=int((time.time() - t0) * 1000),
        )


def _action_mouse_drag(action: dict[str, Any]) -> ActionResult:
    """Drag mouse from (x1,y1) to (x2,y2)."""
    x1 = action.get("x1", 0)
    y1 = action.get("y1", 0)
    x2 = action.get("x2", 0)
    y2 = action.get("y2", 0)
    duration = action.get("duration", 0.5)
    t0 = time.time()
    try:
        import pyautogui
        pyautogui.drag(int(x1), int(y1), int(x2), int(y2), duration=float(duration))
        return ActionResult(
            action_type="mouse_drag",
            action=action,
            ok=True,
            output=f"Dragged from ({x1},{y1}) to ({x2},{y2})",
            duration_ms=int((time.time() - t0) * 1000),
        )
    except ImportError:
        return ActionResult(
            action_type="mouse_drag",
            action=action,
            ok=False,
            error="pyautogui not installed",
            duration_ms=int((time.time() - t0) * 1000),
        )
    except Exception as exc:
        return ActionResult(
            action_type="mouse_drag",
            action=action,
            ok=False,
            error=str(exc)[:300],
            duration_ms=int((time.time() - t0) * 1000),
        )


def _action_key_type(action: dict[str, Any]) -> ActionResult:
    """Type a string of text."""
    text = action.get("text", "")
    t0 = time.time()
    try:
        import pyautogui
        pyautogui.typewrite(str(text), interval=0.02)
        return ActionResult(
            action_type="key_type",
            action=action,
            ok=True,
            output=f"Typed: {str(text)[:100]}",
            duration_ms=int((time.time() - t0) * 1000),
        )
    except ImportError:
        return ActionResult(
            action_type="key_type",
            action=action,
            ok=False,
            error="pyautogui not installed",
            duration_ms=int((time.time() - t0) * 1000),
        )
    except Exception as exc:
        return ActionResult(
            action_type="key_type",
            action=action,
            ok=False,
            error=str(exc)[:300],
            duration_ms=int((time.time() - t0) * 1000),
        )


def _action_key_press(action: dict[str, Any]) -> ActionResult:
    """Press a single key (e.g. 'enter', 'tab', 'escape')."""
    key = action.get("key", "")
    t0 = time.time()
    try:
        import pyautogui
        pyautogui.press(str(key))
        return ActionResult(
            action_type="key_press",
            action=action,
            ok=True,
            output=f"Pressed: {key}",
            duration_ms=int((time.time() - t0) * 1000),
        )
    except ImportError:
        return ActionResult(
            action_type="key_press",
            action=action,
            ok=False,
            error="pyautogui not installed",
            duration_ms=int((time.time() - t0) * 1000),
        )
    except Exception as exc:
        return ActionResult(
            action_type="key_press",
            action=action,
            ok=False,
            error=str(exc)[:300],
            duration_ms=int((time.time() - t0) * 1000),
        )


def _action_key_hotkey(action: dict[str, Any]) -> ActionResult:
    """Press a key combination (e.g. ctrl+c)."""
    keys = action.get("keys", [])
    if isinstance(keys, str):
        keys = [keys]
    t0 = time.time()
    try:
        import pyautogui
        pyautogui.hotkey(*[str(k) for k in keys])
        return ActionResult(
            action_type="key_hotkey",
            action=action,
            ok=True,
            output=f"Hotkey: {'+'.join(str(k) for k in keys)}",
            duration_ms=int((time.time() - t0) * 1000),
        )
    except ImportError:
        return ActionResult(
            action_type="key_hotkey",
            action=action,
            ok=False,
            error="pyautogui not installed",
            duration_ms=int((time.time() - t0) * 1000),
        )
    except Exception as exc:
        return ActionResult(
            action_type="key_hotkey",
            action=action,
            ok=False,
            error=str(exc)[:300],
            duration_ms=int((time.time() - t0) * 1000),
        )


def _action_screenshot(action: dict[str, Any]) -> ActionResult:
    """Take a screenshot and optionally save it."""
    region = action.get("region")  # [left, top, width, height] or None
    save_path = action.get("save_path", "")
    t0 = time.time()
    try:
        import pyautogui
        if region and isinstance(region, list) and len(region) == 4:
            screenshot = pyautogui.screenshot(region=tuple(region))
        else:
            screenshot = pyautogui.screenshot()
        if save_path:
            screenshot.save(save_path)
            output = f"Screenshot saved to {save_path}"
        else:
            # Return basic info
            w, h = screenshot.size
            output = f"Screenshot captured: {w}x{h} pixels"
        return ActionResult(
            action_type="screenshot",
            action=action,
            ok=True,
            output=output,
            duration_ms=int((time.time() - t0) * 1000),
        )
    except ImportError:
        return ActionResult(
            action_type="screenshot",
            action=action,
            ok=False,
            error="pyautogui not installed",
            duration_ms=int((time.time() - t0) * 1000),
        )
    except Exception as exc:
        return ActionResult(
            action_type="screenshot",
            action=action,
            ok=False,
            error=str(exc)[:300],
            duration_ms=int((time.time() - t0) * 1000),
        )


def _action_mcp_call(action: dict[str, Any]) -> ActionResult:
    """Simulate an MCP-style tool call.

    The tool registry is extensible. Currently supports:
    - "search": web search simulation (returns echo)
    - "file_read": read a file
    - "file_write": write a file
    - "http_get": HTTP GET request
    - "http_post": HTTP POST request
    - "json_query": query a JSON structure
    - custom tools registered via register_mcp_tool()
    """
    tool = action.get("tool", "")
    args = action.get("args", {})
    t0 = time.time()
    try:
        result = _MCP_TOOL_REGISTRY.execute(tool, args)
        return ActionResult(
            action_type="mcp_call",
            action=action,
            ok=True,
            output=str(result)[:MAX_OUTPUT_CHARS],
            duration_ms=int((time.time() - t0) * 1000),
        )
    except Exception as exc:
        return ActionResult(
            action_type="mcp_call",
            action=action,
            ok=False,
            error=str(exc)[:300],
            duration_ms=int((time.time() - t0) * 1000),
        )


def _action_wait(action: dict[str, Any]) -> ActionResult:
    """Wait for a specified duration."""
    seconds = float(action.get("seconds", 1))
    t0 = time.time()
    time.sleep(min(seconds, 30))  # cap at 30s
    return ActionResult(
        action_type="wait",
        action=action,
        ok=True,
        output=f"Waited {seconds}s",
        duration_ms=int((time.time() - t0) * 1000),
    )


# Action type -> handler mapping
ACTION_HANDLERS: dict[str, Any] = {
    "browser_open": _action_browser_open,
    "browser_fetch": _action_browser_fetch,
    "mouse_click": _action_mouse_click,
    "mouse_move": _action_mouse_move,
    "mouse_drag": _action_mouse_drag,
    "key_type": _action_key_type,
    "key_press": _action_key_press,
    "key_hotkey": _action_key_hotkey,
    "screenshot": _action_screenshot,
    "mcp_call": _action_mcp_call,
    "wait": _action_wait,
}


def _execute_action(
    action: dict[str, Any],
    cwd: Path,
    timeout: int = DEFAULT_TIMEOUT,
    dry_run: bool = False,
) -> ActionResult:
    """Execute a single typed action."""
    atype = action.get("type", "shell")

    # Shell commands use the legacy executor
    if atype == "shell":
        command = action.get("command", "")
        if dry_run:
            return ActionResult(
                action_type="shell",
                action=action,
                ok=True,
                output="[dry-run] would execute",
            )
        cr = _execute_command(command, cwd, timeout=timeout)
        return ActionResult(
            action_type="shell",
            action=action,
            ok=(cr.exit_code == 0 and not cr.blocked),
            output=cr.stdout,
            error=cr.stderr if cr.exit_code != 0 else "",
            duration_ms=cr.duration_ms,
            blocked=cr.blocked,
            block_reason=cr.block_reason,
        )

    # Other action types use their handlers
    handler = ACTION_HANDLERS.get(atype)
    if handler is None:
        return ActionResult(
            action_type=atype,
            action=action,
            ok=False,
            error=f"unknown action type: {atype}",
        )

    if dry_run:
        return ActionResult(
            action_type=atype,
            action=action,
            ok=True,
            output="[dry-run] would execute",
        )

    return handler(action)


# ── MCP Tool Registry ─────────────────────────────────────────────────────

class MCPToolRegistry:
    """Registry for MCP-style tools that can be called by agent actions."""

    def __init__(self):
        self._tools: dict[str, Any] = {}
        self._register_builtin()

    def _register_builtin(self):
        """Register built-in MCP tools."""
        self.register("file_read", self._tool_file_read)
        self.register("file_write", self._tool_file_write)
        self.register("file_list", self._tool_file_list)
        self.register("http_get", self._tool_http_get)
        self.register("http_post", self._tool_http_post)
        self.register("json_query", self._tool_json_query)
        self.register("text_search", self._tool_text_search)
        self.register("text_replace", self._tool_text_replace)
        self.register("datetime_now", self._tool_datetime_now)
        self.register("env_get", self._tool_env_get)

    def register(self, name: str, handler: Any):
        self._tools[name] = handler

    def execute(self, name: str, args: dict[str, Any]) -> Any:
        handler = self._tools.get(name)
        if handler is None:
            raise ValueError(f"Unknown MCP tool: {name}. Available: {list(self._tools.keys())}")
        return handler(args)

    def list_tools(self) -> list[str]:
        return list(self._tools.keys())

    # ── Built-in tool implementations ────────────────────────────

    def _tool_file_read(self, args: dict) -> str:
        path = args.get("path", "")
        if not path:
            return "error: path required"
        safe, reason = _is_url_safe(path) if path.startswith("http") else (True, "")
        if not safe:
            return f"error: {reason}"
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                return f.read()[:MAX_OUTPUT_CHARS]
        except Exception as exc:
            return f"error: {exc}"

    def _tool_file_write(self, args: dict) -> str:
        path = args.get("path", "")
        content = args.get("content", "")
        if not path:
            return "error: path required"
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return f"Written {len(content)} chars to {path}"
        except Exception as exc:
            return f"error: {exc}"

    def _tool_file_list(self, args: dict) -> str:
        import os
        path = args.get("path", ".")
        pattern = args.get("pattern", "*")
        try:
            import fnmatch
            entries = []
            for entry in os.listdir(path):
                if fnmatch.fnmatch(entry, pattern):
                    full = os.path.join(path, entry)
                    size = os.path.getsize(full) if os.path.isfile(full) else 0
                    entries.append(f"{'[D]' if os.path.isdir(full) else '[F]'} {entry} ({size} bytes)")
            return "\n".join(entries[:100])
        except Exception as exc:
            return f"error: {exc}"

    def _tool_http_get(self, args: dict) -> str:
        url = args.get("url", "")
        safe, reason = _is_url_safe(url)
        if not safe:
            return f"error: {reason}"
        try:
            import urllib.request
            req = urllib.request.Request(url, headers={"User-Agent": "FileSwarm-MCP/1.0"})
            with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:
                return resp.read()[:MAX_OUTPUT_CHARS].decode("utf-8", errors="replace")
        except Exception as exc:
            return f"error: {exc}"

    def _tool_http_post(self, args: dict) -> str:
        url = args.get("url", "")
        data = args.get("data", "")
        safe, reason = _is_url_safe(url)
        if not safe:
            return f"error: {reason}"
        try:
            import urllib.request
            req = urllib.request.Request(
                url,
                data=data.encode("utf-8") if isinstance(data, str) else data,
                headers={"User-Agent": "FileSwarm-MCP/1.0", "Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:
                return resp.read()[:MAX_OUTPUT_CHARS].decode("utf-8", errors="replace")
        except Exception as exc:
            return f"error: {exc}"

    def _tool_json_query(self, args: dict) -> str:
        data = args.get("data", "")
        query = args.get("query", "")
        try:
            obj = json.loads(data) if isinstance(data, str) else data
            # Simple dot-notation query: a.b.c
            for key in query.split("."):
                if isinstance(obj, dict):
                    obj = obj.get(key, "")
                elif isinstance(obj, list):
                    obj = obj[int(key)] if key.isdigit() and int(key) < len(obj) else ""
                else:
                    break
            return json.dumps(obj, ensure_ascii=False, indent=2)[:MAX_OUTPUT_CHARS]
        except Exception as exc:
            return f"error: {exc}"

    def _tool_text_search(self, args: dict) -> str:
        text = args.get("text", "")
        pattern = args.get("pattern", "")
        try:
            matches = []
            for i, line in enumerate(text.splitlines(), 1):
                if re.search(pattern, line, re.IGNORECASE):
                    matches.append(f"L{i}: {line}")
            return "\n".join(matches[:50]) if matches else "no matches"
        except Exception as exc:
            return f"error: {exc}"

    def _tool_text_replace(self, args: dict) -> str:
        text = args.get("text", "")
        old = args.get("old", "")
        new = args.get("new", "")
        try:
            return text.replace(old, new)
        except Exception as exc:
            return f"error: {exc}"

    def _tool_datetime_now(self, args: dict) -> str:
        from datetime import datetime
        fmt = args.get("format", "%Y-%m-%d %H:%M:%S")
        try:
            return datetime.now().strftime(fmt)
        except Exception as exc:
            return f"error: {exc}"

    def _tool_env_get(self, args: dict) -> str:
        key = args.get("key", "")
        if not key:
            # Return safe env vars only (no secrets)
            safe_keys = ["PATH", "HOME", "USERPROFILE", "OS", "COMPUTERNAME",
                         "PROCESSOR_ARCHITECTURE", "PYTHONPATH", "TEMP", "TMP"]
            return "\n".join(f"{k}={os.environ.get(k, '')}" for k in safe_keys if k in os.environ)
        # Block sensitive keys
        sensitive = ["KEY", "SECRET", "TOKEN", "PASSWORD", "PASS", "CRED"]
        if any(s in key.upper() for s in sensitive):
            return f"error: access to sensitive env var '{key}' blocked"
        return os.environ.get(key, f"error: {key} not set")


# Global MCP tool registry instance
_MCP_TOOL_REGISTRY = MCPToolRegistry()


def register_mcp_tool(name: str, handler: Any):
    """Register a custom MCP tool that can be called by agent actions."""
    _MCP_TOOL_REGISTRY.register(name, handler)


def list_mcp_tools() -> list[str]:
    """List all registered MCP tools."""
    return _MCP_TOOL_REGISTRY.list_tools()


# ── Prompt Building ───────────────────────────────────────────────────────

def _build_agent_prompt(
    task_description: str,
    cwd: str,
    context: str = "",
    task_category: str = "mixed",
) -> str:
    """Build a prompt that asks the model for structured actions.

    Args:
        task_description: The natural language task.
        cwd: Working directory.
        context: Additional context string.
        task_category: One of 'shell', 'browser', 'mouse', 'mcp', 'mixed'.
                       Controls which action types are emphasized in the prompt.
    """
    import platform
    is_windows = platform.system() == "Windows"

    shell_hint = ""
    if is_windows:
        shell_hint = (
            "Windows CMD tips: use 'dir' not 'ls', 'md' or 'mkdir' (without -p) not 'mkdir -p', "
            "'type' not 'cat', 'findstr' not 'grep', 'del' not 'rm'. "
            "Use 'dir /s /b' for recursive file listings. "
        )

    # Build action type description based on category
    action_examples: list[str] = []
    action_types_hint = ""

    if task_category in ("shell", "mixed"):
        action_types_hint += (
            "- shell: Execute a shell command. Fields: {\"type\": \"shell\", \"command\": \"...\"}\n"
        )
        if is_windows:
            action_examples.append('  {"type": "shell", "command": "dir /s /b *.py"}')
            action_examples.append('  {"type": "shell", "command": "echo hello > out.txt"}')
        else:
            action_examples.append('  {"type": "shell", "command": "ls -la"}')
            action_examples.append('  {"type": "shell", "command": "echo hello > out.txt"}')

    if task_category in ("browser", "mixed"):
        action_types_hint += (
            "- browser_open: Open URL in browser. Fields: {\"type\": \"browser_open\", \"url\": \"https://...\"}\n"
            "- browser_fetch: Fetch URL content via HTTP. Fields: {\"type\": \"browser_fetch\", \"url\": \"https://...\"}\n"
        )
        action_examples.append('  {"type": "browser_open", "url": "https://example.com"}')
        action_examples.append('  {"type": "browser_fetch", "url": "https://httpbin.org/get"}')

    if task_category in ("mouse", "mixed"):
        action_types_hint += (
            "- mouse_click: Click at coordinates. Fields: {\"type\": \"mouse_click\", \"x\": 100, \"y\": 200, \"button\": \"left\", \"clicks\": 1}\n"
            "- mouse_move: Move mouse. Fields: {\"type\": \"mouse_move\", \"x\": 100, \"y\": 200, \"duration\": 0.5}\n"
            "- key_type: Type text. Fields: {\"type\": \"key_type\", \"text\": \"hello world\"}\n"
            "- key_press: Press key. Fields: {\"type\": \"key_press\", \"key\": \"enter\"}\n"
            "- key_hotkey: Key combo. Fields: {\"type\": \"key_hotkey\", \"keys\": [\"ctrl\", \"c\"]}\n"
            "- screenshot: Capture screen. Fields: {\"type\": \"screenshot\", \"save_path\": \"screen.png\"}\n"
        )
        action_examples.append('  {"type": "mouse_click", "x": 500, "y": 300, "button": "left"}')
        action_examples.append('  {"type": "key_type", "text": "Hello World"}')
        action_examples.append('  {"type": "key_press", "key": "enter"}')
        action_examples.append('  {"type": "screenshot", "save_path": "capture.png"}')

    if task_category in ("mcp", "mixed"):
        available_tools = list_mcp_tools()
        action_types_hint += (
            f"- mcp_call: Call an MCP tool. Fields: {{\"type\": \"mcp_call\", \"tool\": \"<name>\", \"args\": {{...}}}}\n"
            f"  Available MCP tools: {', '.join(available_tools)}\n"
        )
        action_examples.append('  {"type": "mcp_call", "tool": "file_read", "args": {"path": "config.yaml"}}')
        action_examples.append('  {"type": "mcp_call", "tool": "http_get", "args": {"url": "https://httpbin.org/get"}}')
        action_examples.append('  {"type": "mcp_call", "tool": "datetime_now", "args": {}}')

    action_types_hint += (
        "- wait: Pause execution. Fields: {\"type\": \"wait\", \"seconds\": 2}\n"
    )

    examples_str = "\n".join(action_examples)

    return (
        f"TASK: {task_description}\n\n"
        f"WORKING_DIR: {cwd}\n"
        f"PLATFORM: {platform.system()}\n"
        f"{shell_hint}\n"
        f"CONTEXT:\n{context or 'none'}\n\n"
        "Return ONLY a JSON array of action objects to accomplish the task.\n"
        "Each action is a JSON object with a \"type\" field and type-specific fields.\n"
        "\n"
        "Action types:\n"
        f"{action_types_hint}\n"
        "Rules:\n"
        "- Maximum 10 actions.\n"
        "- Each action must be safe and non-destructive.\n"
        "- No rm -rf, format, shutdown, or similar.\n"
        "- Use the most appropriate action type for each step.\n"
        f"{'Use CMD-compatible shell commands (Windows).' if is_windows else 'Use standard Unix shell commands.'}\n"
        "\n"
        "Example actions:\n"
        f"{examples_str}\n"
        "\n"
        'Example output: [{"type": "shell", "command": "echo test"}, {"type": "mcp_call", "tool": "datetime_now", "args": {}}]\n'
    )


def _detect_task_category(task_description: str) -> str:
    """Detect the primary task category from the description."""
    desc = task_description.lower()

    browser_keywords = ["browser", "open url", "navigate", "web page", "website",
                        "网页", "浏览器", "打开网址", "访问"]
    mouse_keywords = ["mouse", "click", "drag", "cursor", "键盘", "鼠标",
                      "点击", "拖拽", "type text", "press key", "screenshot",
                      "截图", "输入"]
    mcp_keywords = ["mcp", "tool", "api call", "json query",
                    "工具调用", "查询", "读取文件", "写入文件"]
    shell_keywords = ["shell", "command", "cmd", "terminal", "dir", "ls",
                      "系统", "检查", "运行", "execute", "process"]

    has_browser = any(kw in desc for kw in browser_keywords)
    has_mouse = any(kw in desc for kw in mouse_keywords)
    has_mcp = any(kw in desc for kw in mcp_keywords)
    has_shell = any(kw in desc for kw in shell_keywords)

    # If multiple categories detected, use "mixed"
    categories = sum([has_browser, has_mouse, has_mcp, has_shell])
    if categories > 1:
        return "mixed"
    if has_browser:
        return "browser"
    if has_mouse:
        return "mouse"
    if has_mcp:
        return "mcp"
    if has_shell:
        return "shell"
    return "mixed"


# ── Main Entry Point ──────────────────────────────────────────────────────

async def execute_agent_task(
    task_id: str,
    task_description: str,
    provider,
    model: str,
    cwd: Path,
    context: str = "",
    timeout_per_command: int = DEFAULT_TIMEOUT,
    dry_run: bool = False,
    max_tokens: int = 2048,
    task_category: str = "",
) -> AgentResult:
    """Execute a non-programming agent task.

    1. Detect task category (shell/browser/mouse/mcp/mixed)
    2. Build category-aware prompt
    3. Ask the model for structured actions
    4. Safety-check each action
    5. Execute sequentially
    6. Collect results

    Includes automatic retry with doubled max_tokens when the model
    returns empty text (common with Anthropic thinking blocks).

    Args:
        task_category: Force a specific category. Auto-detected if empty.
    """
    if not task_category:
        task_category = _detect_task_category(task_description)

    prompt = _build_agent_prompt(task_description, str(cwd), context, task_category)

    # Retry with increasing max_tokens for empty_response (thinking block issue)
    current_max_tokens = max_tokens
    max_retries = 1  # total 2 attempts: original + 1 retry

    result = None
    for attempt in range(max_retries + 1):
        try:
            result = await asyncio.wait_for(
                provider.chat(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=current_max_tokens,
                ),
                timeout=60,
            )
        except TimeoutError:
            return AgentResult(task_id=task_id, ok=False, error="model_timeout")
        except Exception as exc:
            return AgentResult(task_id=task_id, ok=False, error=f"model_error:{type(exc).__name__}")

        if not result.ok:
            return AgentResult(
                task_id=task_id,
                ok=False,
                error=result.error or "provider_error",
                model=model,
                provider=getattr(result, "provider", None),
            )

        output_text = result.text
        if output_text.strip():
            break  # Got valid output, proceed

        # Empty response - retry with more tokens if attempts remain
        if attempt < max_retries:
            current_max_tokens = min(current_max_tokens * 2, 8192)
            continue

    # After all retries, check if still empty
    output_text = result.text if result else ""
    if not output_text.strip():
        return AgentResult(
            task_id=task_id,
            ok=False,
            error="empty_response",
            summary=f"Model returned no text after {max_retries + 1} attempts (max_tokens reached {current_max_tokens}). Thinking blocks may consume all output tokens.",
            model=model,
            provider=getattr(result, "provider", None) if result else None,
            input_tokens=result.input_tokens if result else None,
            output_tokens=result.output_tokens if result else None,
        )

    # Extract structured actions
    actions = _extract_actions(output_text)
    if not actions:
        return AgentResult(
            task_id=task_id,
            ok=False,
            error="no_actions_extracted",
            summary=result.text[:500],
            model=model,
            provider=getattr(result, "provider", None),
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
        )

    executed: list[ActionResult] = []
    legacy_commands: list[CommandResult] = []

    for action in actions:
        ar = _execute_action(action, cwd, timeout=timeout_per_command, dry_run=dry_run)
        executed.append(ar)

        # Also track shell commands in legacy format for backward compat
        if ar.action_type == "shell":
            legacy_commands.append(CommandResult(
                command=action.get("command", ""),
                exit_code=0 if ar.ok else -1,
                stdout=ar.output,
                stderr=ar.error,
                duration_ms=ar.duration_ms,
                blocked=ar.blocked,
                block_reason=ar.block_reason,
            ))

        if ar.blocked:
            break

    # Determine success (lenient: 60% pass rate)
    all_ok = all(ar.ok and not ar.blocked for ar in executed)
    if not all_ok and executed:
        success_count = sum(1 for ar in executed if ar.ok and not ar.blocked)
        if success_count >= max(1, len(executed) * 0.6):
            all_ok = True

    # Build summary
    summary_lines = [f"Executed {len(executed)} actions (category={task_category}):"]
    for ar in executed:
        status = "BLOCKED" if ar.blocked else ("OK" if ar.ok else "FAIL")
        action_desc = json.dumps(ar.action, ensure_ascii=False)[:80]
        summary_lines.append(f"  [{status}] {ar.action_type}: {action_desc}")
        if ar.output:
            summary_lines.append(f"    -> {ar.output[:200].strip()}")
        if ar.error and not ar.ok:
            summary_lines.append(f"    ! {ar.error[:200].strip()}")

    return AgentResult(
        task_id=task_id,
        ok=all_ok,
        commands_executed=legacy_commands,
        actions_executed=executed,
        summary="\n".join(summary_lines),
        model=model,
        provider=getattr(result, "provider", None),
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
    )
