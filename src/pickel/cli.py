"""pickel — A pickaxe for mining Claude Code conversation logs."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional

__version__ = "0.6.0"

# ── Color ────────────────────────────────────────────────────────

NO_COLOR = os.environ.get("NO_COLOR") is not None
FORCE_COLOR = os.environ.get("FORCE_COLOR") is not None


def _supports_color() -> bool:
    if FORCE_COLOR:
        return True
    if NO_COLOR:
        return False
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


USE_COLOR = _supports_color()


def c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if USE_COLOR else text


def dim(t: str) -> str:
    return c("2", t)


def bold(t: str) -> str:
    return c("1", t)


def red(t: str) -> str:
    return c("31", t)


def orange(t: str) -> str:
    return c("38;5;208", t)


# ── Sanitization ────────────────────────────────────────────────

_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]|\x1b\[[0-9;]*[A-Za-z]")


def _sanitize(text: str) -> str:
    """Remove C0 control characters and ANSI escape sequences from text."""
    return _CONTROL_RE.sub("", text)


# ── Safe helpers ────────────────────────────────────────────────


def _safe_int(val: object) -> int:
    """Coerce *val* to int, returning 0 (with warning) on failure.

    * ``bool`` is rejected (bool is a subclass of int).
    * Negative values are clamped to 0.
    """
    if isinstance(val, bool):
        _warn(f"expected int, got bool: {val!r}")
        return 0
    if isinstance(val, int):
        if val < 0:
            _warn(f"negative int clamped to 0: {val!r}")
            return 0
        return val
    if isinstance(val, float):
        if not math.isfinite(val):
            _warn(f"non-finite float coerced to 0: {val!r}")
            return 0
        n = int(val)
        if n < 0:
            _warn(f"negative float clamped to 0: {val!r}")
            return 0
        return n
    _warn(f"expected int, got {type(val).__name__}: {val!r}")
    return 0


# ── Data Dir ─────────────────────────────────────────────────────


def get_projects_dir() -> Path:
    config = os.environ.get("CLAUDE_CONFIG_DIR", os.path.expanduser("~/.claude"))
    return Path(config) / "projects"


def get_ores_dir() -> Path:
    return Path(os.environ.get("PICKEL_ORES_DIR", os.path.expanduser("~/.pickel/ores")))


def _sanitize_project_name(name: str) -> "Optional[str]":
    """Validate a project name to prevent path traversal.

    Rejects names containing slashes, backslashes, parent-directory
    references (``..``), or leading dots.
    """
    if not name or '/' in name or '\\' in name or '..' in name or name.startswith('.'):
        return None
    return name


def _project_name_from_cwd(cwd: str) -> "Optional[str]":
    if not cwd:
        return None
    p = Path(cwd)
    name = p.name
    if not name:
        return None
    # GitHub / ghq structure: parent = org name
    parent = p.parent.name
    if parent and parent not in ('', '.', 'src', 'home', 'Users'):
        # ghq structure: github.com/org/repo -> org-repo
        grandparent = p.parent.parent.name
        if grandparent in ('github.com', 'gitlab.com', 'bitbucket.org'):
            result = f"{parent}-{name}"
            return _sanitize_project_name(result) and result or None
    return _sanitize_project_name(name) and name or None


# Directories to exclude from project listing
_EXCLUDED_DIRS = {"-claude-mem-observer-sessions", "subagents"}


def normalize_project_name(dirname: str) -> str:
    """Turn long dir names into short project names.

    Claude encodes filesystem paths by replacing ``/`` with ``-`` and ``.``
    with ``-``.  Double ``--`` marks a dotfile directory boundary
    (e.g. ``/.ghq/`` becomes ``--ghq-``).

    Examples::

        -Users-alice--ghq-github-com-org-my-app  -> my-app
        -Users-bob--ghq-github-com-bob-cool-lib   -> cool-lib
        -Users-bob-Documents-zombie-automation     -> Documents-zombie-automation

    Owner is treated as a single non-hyphenated segment.  For owners
    that *contain* hyphens (e.g. ``my-org``), only the first segment is
    consumed as the owner and the rest becomes part of the repo name.
    This is an accepted limitation of the path-encoding scheme.
    """
    # ghq / GitHub pattern: -github-com-{owner}-{everything-else}
    # owner = first non-hyphenated segment after "-github-com-"
    m = re.search(r"-github-com-([^-]+)-(.+)$", dirname)
    if m:
        return m.group(2)

    # Generic encoded path
    if dirname.startswith("-"):
        path = dirname[1:]
        # Split on -- (dotfile directory boundaries)
        segments = path.split("--")
        last_seg = segments[-1]

        # Strip Users-{user}- prefix if present
        m2 = re.match(r"^Users-[^-]+-(.*)", last_seg)
        if m2 and m2.group(1):
            return m2.group(1)

        # -Users-{user} with no sub-path
        m3 = re.match(r"^Users-(.+)", last_seg)
        if m3:
            return m3.group(1)

        return last_seg

    return dirname


def find_projects(base: Path) -> dict[str, Path]:
    """Return {short_name: path} for all projects.

    When two directories resolve to the same short name, the parent
    directory info is appended to disambiguate (e.g. ``my-app (org1)``
    vs ``my-app (org2)``).
    """
    projects: dict[str, Path] = {}
    if not base.is_dir():
        return projects

    # First pass: collect name -> list of (dirname, path)
    name_to_dirs: dict[str, list[tuple[str, Path]]] = {}
    try:
        entries = sorted(base.iterdir())
    except OSError as e:
        _warn(f"cannot list {base}: {e}")
        return projects
    for d in entries:
        if d.is_dir() and not d.name.startswith(".") and d.name not in _EXCLUDED_DIRS:
            name = normalize_project_name(d.name)
            name_to_dirs.setdefault(name, []).append((d.name, d))

    # Second pass: disambiguate collisions
    for name, dirs in name_to_dirs.items():
        if len(dirs) == 1:
            projects[name] = dirs[0][1]
        else:
            for dirname, path in dirs:
                # Try to extract org from github-com-{org}-{repo}
                m = re.search(r"-github-com-([^-]+)-", dirname)
                suffix = m.group(1) if m else dirname[:16]
                display = f"{name} ({suffix})"
                # Ensure uniqueness: append counter if display name already taken
                if display in projects:
                    counter = 2
                    while f"{display} ({counter})" in projects:
                        counter += 1
                    display = f"{display} ({counter})"
                projects[display] = path

    return projects


def find_sessions(project_dir: Path) -> list[Path]:
    """Return all .jsonl session files sorted by mtime desc."""
    try:
        files = list(project_dir.glob("*.jsonl"))
    except OSError as e:
        _warn(f"cannot list {project_dir}: {e}")
        return []
    timed: list[tuple[float, Path]] = []
    for f in files:
        try:
            mtime = f.stat().st_mtime
            timed.append((mtime, f))
        except OSError as e:
            _warn(f"cannot stat {f}: {e}")
    timed.sort(key=lambda t: t[0], reverse=True)
    return [f for _, f in timed]


def _session_mtime_date(session_path: Path) -> str | None:
    """Return YYYY-MM-DD from file mtime, or None on error."""
    try:
        return datetime.fromtimestamp(session_path.stat().st_mtime).strftime("%Y-%m-%d")
    except OSError as e:
        _warn(f"cannot stat {session_path}: {e}")
        return None


def _today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _this_month_str() -> str:
    return datetime.now().strftime("%Y-%m")


def _format_age(seconds: float) -> str:
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{int(seconds / 60)}m ago"
    if seconds < 86400:
        return f"{int(seconds / 3600)}h ago"
    return f"{int(seconds / 86400)}d ago"


def _format_size(nbytes: int) -> str:
    if nbytes < 1024:
        return f"{nbytes}B"
    kb = nbytes / 1024
    if kb < 1024:
        return f"{kb:.1f}K"
    return f"{kb / 1024:.1f}M"


def _validate_date(date_str: str) -> str:
    """Validate a YYYY-MM-DD date string. Exit with code 2 on failure."""
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        print(
            f"pickel: invalid date '{date_str}' (expected YYYY-MM-DD)",
            file=sys.stderr,
        )
        sys.exit(2)
    return date_str


# ── Quiet mode ──────────────────────────────────────────────────

_QUIET = False


def _warn(msg: str) -> None:
    """Print a warning to stderr unless --quiet is set."""
    if not _QUIET:
        print(f"pickel: warning: {msg}", file=sys.stderr)


# ── JSONL Parser ─────────────────────────────────────────────────


def iter_messages(jsonl_path: Path) -> Iterator[dict]:
    """Yield parsed entries from a .jsonl session file."""
    try:
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    _warn(f"{jsonl_path.name}:{lineno}: invalid JSON, skipping")
                    continue
                if not isinstance(entry, dict):
                    _warn(
                        f"{jsonl_path.name}:{lineno}: expected object, "
                        f"got {type(entry).__name__}, skipping"
                    )
                    continue
                yield entry
    except (OSError, IOError) as e:
        _warn(f"cannot read {jsonl_path}: {e}")
        return


def extract_text(entry: dict) -> str | None:
    """Extract human-readable text from a message entry."""
    msg = entry.get("message", {})
    if not isinstance(msg, dict):
        return None
    content = msg.get("content", [])
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    val = block.get("text", "")
                    if isinstance(val, str):
                        parts.append(val)
                elif block.get("type") == "tool_use":
                    parts.append(f"[tool:{block.get('name', '?')}]")
                elif block.get("type") == "tool_result":
                    # Compact tool results
                    sub = block.get("content", "")
                    if isinstance(sub, list):
                        for s in sub:
                            if isinstance(s, dict) and s.get("type") == "text":
                                val = s.get("text", "")
                                if isinstance(val, str):
                                    parts.append(val[:200])
                    elif isinstance(sub, str):
                        parts.append(sub[:200])
        return "\n".join(parts) if parts else None
    return None


# ── Mine: constants ──────────────────────────────────────────────

_MINE_MAX_CONTEXT = 10_000

_MINE_DECISION_USER_RE = re.compile(
    r"に決めた|でいこう|で確定|let'?s go with|decided",
    re.IGNORECASE,
)
_MINE_DECISION_ASST_RE = re.compile(
    r"確定しました|に決まりました|に決定しました|we decided|we'll use|settled on|chosen|going with",
    re.IGNORECASE,
)
_MINE_DISCOVERY_RE = re.compile(
    r"わかった|発見|\bfound\b|turns out|原因は|\bfix(?:ed)?\b|\bsolved\b|直った",
    re.IGNORECASE,
)
_MINE_UNFINISHED_RE = re.compile(
    r"次は|\bTODO\b|後で|残課題|next step|\blater\b|やること|あとで",
    re.IGNORECASE,
)
_MINE_ERROR_RE = re.compile(
    r"\b404\b|\berror:?\b|\bfailed\b|\bbug\b|\bexception\b",
    re.IGNORECASE,
)
_MINE_CORRECTION_RE_LIST = [
    re.compile(r"違う"),
    re.compile(r"ちょっと待って"),
    re.compile(r"だめ"),
    re.compile(r"\bwrong\b", re.IGNORECASE),
    re.compile(r"\bwait\b", re.IGNORECASE),
    re.compile(r"^no\b", re.IGNORECASE | re.MULTILINE),
]


# ── Commands ─────────────────────────────────────────────────────


def cmd_search(args):
    """Search conversation logs for a query string."""
    base = get_projects_dir()
    projects = find_projects(base)
    use_regex = getattr(args, "regex", False)
    max_results = args.max
    project_filter = args.project
    compact = getattr(args, "compact", False)

    # Date filters
    since_date = None
    if getattr(args, "today", False):
        since_date = _today_str()
    elif getattr(args, "since", None):
        since_date = _validate_date(args.since)

    # Build match function
    if use_regex:
        try:
            pat = re.compile(args.query, re.IGNORECASE)
        except re.error as e:
            print(f"Invalid regex: {e}", file=sys.stderr)
            sys.exit(1)

        def match(text: str) -> bool:
            return pat.search(text) is not None

        def match_line(line: str) -> bool:
            return pat.search(line) is not None
    else:
        query = args.query.lower()

        def match(text: str) -> bool:
            return query in text.lower()

        def match_line(line: str) -> bool:
            return query in line.lower()

    results = []

    target_projects = list(projects.items())
    if project_filter:
        target_projects = [
            (k, v) for k, v in projects.items() if project_filter.lower() in k.lower()
        ]
        if not target_projects:
            print(
                f"pickel: no projects matching '{project_filter}'",
                file=sys.stderr,
            )
            sys.exit(1)

    for proj_name, proj_dir in target_projects:
        for session_file in find_sessions(proj_dir):
            # Date filter: skip sessions older than since_date
            if since_date:
                file_date = _session_mtime_date(session_file)
                if file_date is None or file_date < since_date:
                    continue

            session_id = session_file.stem[:8]
            for entry in iter_messages(session_file):
                etype = entry.get("type", "")
                if etype not in ("user", "assistant"):
                    continue
                text = extract_text(entry)
                if not text:
                    continue
                if match(text):
                    role = entry.get("type", "?")
                    ts = entry.get("timestamp", "")
                    # Extract matching line
                    for line in text.split("\n"):
                        if match_line(line):
                            results.append(
                                {
                                    "project": proj_name,
                                    "session": session_id,
                                    "role": role,
                                    "timestamp": ts,
                                    "line": line.strip()[:200],
                                }
                            )
                            if len(results) >= max_results:
                                break
                if len(results) >= max_results:
                    break
            if len(results) >= max_results:
                break
        if len(results) >= max_results:
            break

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return

    if compact:
        for r in results:
            print(
                f"project:{_sanitize(r['project'])} session:{_sanitize(r['session'])} "
                f"role:{_sanitize(r['role'])} text:{_sanitize(r['line'])}"
            )
        return

    if not results:
        print(f"No results for {bold(args.query)}")
        return

    print(f"{bold(str(len(results)))} results for {bold(args.query)}\n")

    # Group by project -> session
    current_proj = None
    current_session = None
    for r in results:
        if r["project"] != current_proj:
            current_proj = r["project"]
            current_session = None
            print(f"  {orange(_sanitize(current_proj))}")
        if r["session"] != current_session:
            current_session = r["session"]
            print(f"    {dim(_sanitize(current_session))}")

        icon = "U" if r["role"] == "user" else "A"
        raw_ts = r["timestamp"]
        ts = raw_ts[:16].replace("T", " ") if isinstance(raw_ts, str) and raw_ts else ""

        # Highlight the query in the line
        line = _sanitize(r["line"])
        if USE_COLOR:
            if use_regex:
                try:
                    line = pat.sub(lambda m: c("1;33", m.group()), line)
                except Exception:
                    pass
            else:
                pattern = re.compile(re.escape(args.query), re.IGNORECASE)
                line = pattern.sub(lambda m: c("1;33", m.group()), line)

        print(f"      {dim(ts)} {icon} {line}")
    print()


def cmd_context(args):
    """Show compact context summary for a session."""
    base = get_projects_dir()
    projects = find_projects(base)

    # Find all matching sessions
    matches = []
    for pname, pdir in projects.items():
        if args.project and args.project.lower() not in pname.lower():
            continue
        for sf in find_sessions(pdir):
            if args.session in sf.stem:
                matches.append((pname, sf))

    if not matches:
        print(f"Session {bold(args.session)} not found", file=sys.stderr)
        sys.exit(1)

    if len(matches) > 1:
        print(
            f"Multiple sessions match '{args.session}':",
            file=sys.stderr,
        )
        for pname, sf in matches:
            print(f"  {pname} {sf.stem}", file=sys.stderr)
        sys.exit(1)

    proj_name, target = matches[0][0], matches[0][1]

    # Collect user messages and key assistant responses
    user_msgs = []
    tools_used = set()

    for entry in iter_messages(target):
        etype = entry.get("type", "")
        text = extract_text(entry)

        if etype == "user" and text:
            user_msgs.append(text.strip()[:150])

        if etype == "assistant":
            msg = entry.get("message", {})
            if not isinstance(msg, dict):
                continue
            content = msg.get("content", [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        name = block.get("name", "unknown")
                        if not isinstance(name, str):
                            name = "unknown"
                        tools_used.add(name)

    if args.json:
        print(
            json.dumps(
                {
                    "project": proj_name,
                    "session": target.stem,
                    "user_messages": user_msgs[:20],
                    "tools_used": sorted(tools_used),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    print(f"  {orange(_sanitize(proj_name))} {dim(_sanitize(target.stem[:12]))}\n")
    print(f"  {bold('User messages')} ({len(user_msgs)} total):")
    for i, msg in enumerate(user_msgs[:15]):
        first_line = msg.split("\n")[0][:100]
        print(f"    {dim(str(i + 1) + '.'):>5} {_sanitize(first_line)}")
    if len(user_msgs) > 15:
        print(f"    {dim(f'  ...+{len(user_msgs) - 15} more')}")
    print(
        f"\n  {bold('Tools used')}: {', '.join(_sanitize(t) for t in sorted(tools_used)) or 'none'}"
    )
    print()


def cmd_last(args):
    """Show the last session summary for a project."""
    base = get_projects_dir()
    projects = find_projects(base)

    matches = [(k, v) for k, v in projects.items() if args.project.lower() in k.lower()]
    if not matches:
        print(f"Project {bold(args.project)} not found", file=sys.stderr)
        sys.exit(1)

    if len(matches) > 1:
        print(
            f"Multiple projects match '{args.project}':",
            file=sys.stderr,
        )
        for name, _ in matches:
            print(f"  {name}", file=sys.stderr)
        sys.exit(1)

    proj_name, proj_dir = matches[0]
    sessions = find_sessions(proj_dir)
    if not sessions:
        print(f"No sessions in {bold(proj_name)}", file=sys.stderr)
        sys.exit(1)

    latest = sessions[0]
    try:
        mtime = latest.stat().st_mtime
    except OSError:
        print(f"Session vanished: {latest}", file=sys.stderr)
        sys.exit(1)
    age = time.time() - mtime
    age_str = (
        f"{int(age / 3600)}h ago"
        if age > 3600
        else f"{int(age / 60)}m ago"
        if age > 60
        else "just now"
    )

    # Collect summary
    user_msgs = []
    last_user = ""
    last_assistant = ""
    model = "?"
    total_tokens = 0

    for entry in iter_messages(latest):
        etype = entry.get("type", "")
        text = extract_text(entry)

        if etype == "user" and text:
            user_msgs.append(text.strip().split("\n")[0][:100])
            last_user = text.strip().split("\n")[0][:100]

        if etype == "assistant":
            msg = entry.get("message", {})
            if not isinstance(msg, dict):
                continue
            m = msg.get("model", "")
            if isinstance(m, str) and m and not m.startswith("<"):
                model = m
            usage = msg.get("usage") or {}
            if isinstance(usage, dict):
                total_tokens += _safe_int(usage.get("input_tokens", 0)) + _safe_int(
                    usage.get("output_tokens", 0)
                )
            if text:
                last_assistant = text.strip().split("\n")[0][:100]

    if args.json:
        print(
            json.dumps(
                {
                    "project": proj_name,
                    "session": latest.stem,
                    "age": age_str,
                    "model": model,
                    "turns": len(user_msgs),
                    "tokens": total_tokens,
                    "last_user": last_user,
                    "last_assistant": last_assistant,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    print(f"  {orange(_sanitize(proj_name))} — last session ({age_str})\n")
    print(f"  {dim('session')}  {_sanitize(latest.stem[:12])}")
    print(f"  {dim('model')}    {_sanitize(model)}")
    print(f"  {dim('turns')}    {len(user_msgs)}")
    print(f"  {dim('tokens')}   {total_tokens:,}")
    print()
    print(f"  {bold('Last exchange')}:")
    print(f"    U {_sanitize(last_user)}")
    print(f"    A {_sanitize(last_assistant)}")
    print()


def cmd_projects(args):
    """List all projects with stats."""
    base = get_projects_dir()
    projects = find_projects(base)
    limit = getattr(args, "limit", None)

    rows = []
    for name, pdir in projects.items():
        try:
            sessions = list(pdir.glob("*.jsonl"))
        except OSError as e:
            _warn(f"cannot list {pdir}: {e}")
            continue
        total_size = 0
        last_mod = 0
        session_count = 0
        for f in sessions:
            try:
                st = f.stat()
            except OSError:
                continue
            session_count += 1
            total_size += st.st_size
            if st.st_mtime > last_mod:
                last_mod = st.st_mtime
        age = time.time() - last_mod if last_mod else 0
        age_str = (
            (
                f"{int(age / 86400)}d"
                if age > 86400
                else f"{int(age / 3600)}h"
                if age > 3600
                else f"{int(age / 60)}m"
            )
            if last_mod
            else "?"
        )
        rows.append((name, session_count, total_size, age_str))

    rows.sort(key=lambda r: r[2], reverse=True)

    if args.json:
        print(
            json.dumps(
                [
                    {
                        "project": r[0],
                        "sessions": r[1],
                        "size_mb": round(r[2] / 1024 / 1024, 1),
                        "last": r[3],
                    }
                    for r in rows
                ],
                indent=2,
            )
        )
        return

    display_limit = limit if limit else len(rows)
    print(f"  {bold(str(len(rows)))} projects\n")
    print(
        f"  {bold('PROJECT'):<30} {bold('SESSIONS'):>8} {bold('SIZE'):>8} {bold('LAST'):>6}"
    )
    print(f"  {'─' * 30} {'─' * 8} {'─' * 8} {'─' * 6}")
    for name, count, size, age in rows[:display_limit]:
        size_str = f"{size / 1024 / 1024:.1f}M"
        print(f"  {_sanitize(name):<30} {count:>8} {size_str:>8} {dim(age):>6}")
    remaining = len(rows) - display_limit
    if remaining > 0:
        print(f"  {dim(f'...+{remaining} more')}")
    print(
        f"\n  {dim(f'{sum(r[1] for r in rows)} sessions · {sum(r[2] for r in rows) / 1024 / 1024 / 1024:.1f} GB total')}"
    )
    print()


def cmd_chat(args):
    """Show session conversation in chat format."""
    base = get_projects_dir()
    projects = find_projects(base)

    session_files = []

    if args.session:
        # Find all matching sessions
        matches = []
        for pname, pdir in projects.items():
            if args.project and args.project.lower() not in pname.lower():
                continue
            for sf in find_sessions(pdir):
                if args.session in sf.stem:
                    matches.append((pname, sf))

        if len(matches) > 1:
            print(
                f"Multiple sessions match '{args.session}':",
                file=sys.stderr,
            )
            for pname, sf in matches:
                print(f"  {pname} {sf.stem}", file=sys.stderr)
            sys.exit(1)

        session_files = matches
    elif args.project:
        matches = [
            (k, v) for k, v in projects.items() if args.project.lower() in k.lower()
        ]
        if not matches:
            print(f"Project {bold(args.project)} not found", file=sys.stderr)
            sys.exit(1)
        if len(matches) > 1:
            print(
                f"Multiple projects match '{args.project}':",
                file=sys.stderr,
            )
            for name, _ in matches:
                print(f"  {name}", file=sys.stderr)
            sys.exit(1)
        proj_name, proj_dir = matches[0]
        sessions = find_sessions(proj_dir)
        n = args.last or 1
        for sf in sessions[:n]:
            session_files.append((proj_name, sf))
    else:
        print("Specify -p PROJECT or a session ID", file=sys.stderr)
        sys.exit(1)

    if not session_files:
        print("No sessions found", file=sys.stderr)
        sys.exit(1)

    all_conversations = []

    for proj_name, sf in session_files:
        messages = []
        for entry in iter_messages(sf):
            etype = entry.get("type", "")
            if etype not in ("user", "assistant"):
                continue
            msg = entry.get("message", {})
            if not isinstance(msg, dict):
                continue
            content = msg.get("content", [])
            ts = entry.get("timestamp", "")

            # Extract text parts and tool_use summaries
            parts = []
            if isinstance(content, str):
                parts.append(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            val = block.get("text", "")
                            if isinstance(val, str):
                                parts.append(val)
                        elif block.get("type") == "tool_use":
                            parts.append(f"[tool:{block.get('name', '?')}]")
                        elif block.get("type") == "tool_result":
                            pass  # skip tool results in chat view

            text = "\n".join(parts).strip() if parts else ""
            if not text:
                continue

            messages.append(
                {
                    "role": etype,
                    "timestamp": ts,
                    "text": text,
                }
            )

        all_conversations.append(
            {
                "project": proj_name,
                "session": sf.stem,
                "messages": messages,
            }
        )

    if args.json:
        print(json.dumps(all_conversations, ensure_ascii=False, indent=2))
        return

    for conv in all_conversations:
        print(
            f"  {orange(_sanitize(conv['project']))} "
            f"{dim(_sanitize(conv['session'][:12]))}\n"
        )
        for m in conv["messages"]:
            icon = "U" if m["role"] == "user" else "A"
            raw_ts = m["timestamp"]
            ts = (
                raw_ts[:16].replace("T", " ")
                if isinstance(raw_ts, str) and raw_ts
                else ""
            )
            print(f"  {dim(ts)} {icon}")
            for line in m["text"].split("\n"):
                print(f"    {_sanitize(line)}")
            print()
        print(f"  {dim('─' * 40)}\n")


def cmd_errors(args):
    """Extract user correction messages and API errors."""
    base = get_projects_dir()
    projects = find_projects(base)
    project_filter = args.project

    target_projects = list(projects.items())
    if project_filter:
        target_projects = [
            (k, v) for k, v in projects.items() if project_filter.lower() in k.lower()
        ]
        if not target_projects:
            print(
                f"pickel: no projects matching '{project_filter}'",
                file=sys.stderr,
            )
            sys.exit(1)

    results = []

    for proj_name, proj_dir in target_projects:
        for session_file in find_sessions(proj_dir):
            session_id = session_file.stem[:8]
            for entry in iter_messages(session_file):
                etype = entry.get("type", "")
                ts = entry.get("timestamp", "")

                # Check user messages for corrections
                if etype == "user":
                    text = extract_text(entry)
                    if text:
                        for pat in _MINE_CORRECTION_RE_LIST:
                            if pat.search(text):
                                first_line = text.strip().split("\n")[0][:200]
                                results.append(
                                    {
                                        "type": "correction",
                                        "project": proj_name,
                                        "session": session_id,
                                        "timestamp": ts,
                                        "text": first_line,
                                    }
                                )
                                break

                # Check for API errors
                if etype == "system":
                    subtype = entry.get("subtype", "")
                    if subtype == "api_error":
                        msg_text = ""
                        msg = entry.get("message", {})
                        if isinstance(msg, dict):
                            msg_text = str(msg.get("error", msg.get("message", "")))[
                                :200
                            ]
                        elif isinstance(msg, str):
                            msg_text = msg[:200]
                        results.append(
                            {
                                "type": "api_error",
                                "project": proj_name,
                                "session": session_id,
                                "timestamp": ts,
                                "text": msg_text,
                            }
                        )

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return

    if not results:
        print("No errors or corrections found")
        return

    corrections = [r for r in results if r["type"] == "correction"]
    api_errors = [r for r in results if r["type"] == "api_error"]

    print(f"  {bold(str(len(results)))} issues found\n")

    if corrections:
        print(f"  {bold('User corrections')} ({len(corrections)})")
        for r in corrections[:20]:
            raw_ts = r["timestamp"]
            ts = (
                raw_ts[:16].replace("T", " ")
                if isinstance(raw_ts, str) and raw_ts
                else ""
            )
            print(
                f"    {dim(ts)} {orange(_sanitize(r['project']))} "
                f"{dim(_sanitize(r['session']))} {_sanitize(r['text'])}"
            )
        if len(corrections) > 20:
            print(f"    {dim(f'  ...+{len(corrections) - 20} more')}")
        print()

    if api_errors:
        print(f"  {red('API errors')} ({len(api_errors)})")
        for r in api_errors[:20]:
            raw_ts = r["timestamp"]
            ts = (
                raw_ts[:16].replace("T", " ")
                if isinstance(raw_ts, str) and raw_ts
                else ""
            )
            print(
                f"    {dim(ts)} {orange(_sanitize(r['project']))} "
                f"{dim(_sanitize(r['session']))} {_sanitize(r['text'])}"
            )
        if len(api_errors) > 20:
            print(f"    {dim(f'  ...+{len(api_errors) - 20} more')}")
        print()


def cmd_tools(args):
    """Show tool usage frequency."""
    base = get_projects_dir()
    projects = find_projects(base)
    project_filter = args.project

    target_projects = list(projects.items())
    if project_filter:
        target_projects = [
            (k, v) for k, v in projects.items() if project_filter.lower() in k.lower()
        ]
        if not target_projects:
            print(
                f"pickel: no projects matching '{project_filter}'",
                file=sys.stderr,
            )
            sys.exit(1)

    tool_counts: dict[str, int] = defaultdict(int)

    for proj_name, proj_dir in target_projects:
        for session_file in find_sessions(proj_dir):
            for entry in iter_messages(session_file):
                if entry.get("type") != "assistant":
                    continue
                msg = entry.get("message", {})
                if not isinstance(msg, dict):
                    continue
                content = msg.get("content", [])
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "tool_use":
                            name = block.get("name", "unknown")
                            if not isinstance(name, str):
                                name = "unknown"
                            tool_counts[name] += 1

    sorted_tools = sorted(tool_counts.items(), key=lambda x: x[1], reverse=True)

    if args.json:
        print(
            json.dumps(
                [{"tool": name, "count": count} for name, count in sorted_tools],
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    if not sorted_tools:
        print("No tool usage found")
        return

    total = sum(count for _, count in sorted_tools)
    print(f"  Tool usage ({bold(str(total))} total calls)\n")
    print(f"  {bold('TOOL'):<40} {bold('COUNT'):>8} {bold('%'):>6}")
    print(f"  {'─' * 40} {'─' * 8} {'─' * 6}")
    for name, count in sorted_tools[:30]:
        pct = count / total * 100 if total else 0
        print(f"  {_sanitize(name):<40} {count:>8} {dim(f'{pct:.1f}%'):>6}")
    if len(sorted_tools) > 30:
        rest = sum(count for _, count in sorted_tools[30:])
        print(f"  {dim(f'...+{len(sorted_tools) - 30} more'):<40} {rest:>8}")
    print()


def cmd_cost(args):
    """Show estimated token costs."""
    base = get_projects_dir()
    projects = find_projects(base)
    project_filter = args.project

    # Date filters
    since_date = None
    if getattr(args, "today", False):
        since_date = _today_str()
    elif getattr(args, "month", False):
        since_date = _this_month_str() + "-01"

    target_projects = list(projects.items())
    if project_filter:
        target_projects = [
            (k, v) for k, v in projects.items() if project_filter.lower() in k.lower()
        ]
        if not target_projects:
            print(
                f"pickel: no projects matching '{project_filter}'",
                file=sys.stderr,
            )
            sys.exit(1)

    # Cost rates per 1M tokens (USD)
    cost_rates = {
        "opus": {"input": 15.0, "output": 75.0},
        "sonnet": {"input": 3.0, "output": 15.0},
        "haiku": {"input": 0.25, "output": 1.25},
    }

    # model_name -> {input_tokens, output_tokens}
    model_usage: dict[str, dict[str, int]] = defaultdict(
        lambda: {"input_tokens": 0, "output_tokens": 0}
    )

    for proj_name, proj_dir in target_projects:
        for session_file in find_sessions(proj_dir):
            if since_date:
                file_date = _session_mtime_date(session_file)
                if file_date is None or file_date < since_date:
                    continue
            for entry in iter_messages(session_file):
                if entry.get("type") != "assistant":
                    continue
                msg = entry.get("message", {})
                if not isinstance(msg, dict):
                    continue
                model = msg.get("model", "unknown")
                if not isinstance(model, str) or not model or model.startswith("<"):
                    model = "unknown"
                usage = msg.get("usage") or {}
                if isinstance(usage, dict):
                    input_total = (
                        _safe_int(usage.get("input_tokens", 0))
                        + _safe_int(usage.get("cache_creation_input_tokens", 0))
                        + _safe_int(usage.get("cache_read_input_tokens", 0))
                    )
                    model_usage[model]["input_tokens"] += input_total
                    model_usage[model]["output_tokens"] += _safe_int(
                        usage.get("output_tokens", 0)
                    )

    # Compute costs
    results = []
    total_cost = 0.0
    total_input = 0
    total_output = 0

    for model, usage in sorted(model_usage.items()):
        inp = usage["input_tokens"]
        out = usage["output_tokens"]
        total_input += inp
        total_output += out

        # Determine rate tier
        rate_key = None
        model_lower = model.lower()
        if "opus" in model_lower:
            rate_key = "opus"
        elif "sonnet" in model_lower:
            rate_key = "sonnet"
        elif "haiku" in model_lower:
            rate_key = "haiku"

        if rate_key:
            rates = cost_rates[rate_key]
            cost = (inp / 1_000_000 * rates["input"]) + (
                out / 1_000_000 * rates["output"]
            )
        else:
            cost = None  # uncosted — unknown model

        if cost is not None:
            total_cost += cost

        results.append(
            {
                "model": model,
                "input_tokens": inp,
                "output_tokens": out,
                "cost_usd": round(cost, 2) if cost is not None else None,
            }
        )

    if args.json:
        print(
            json.dumps(
                {
                    "models": results,
                    "total_input_tokens": total_input,
                    "total_output_tokens": total_output,
                    "total_cost_usd": round(total_cost, 2),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    if not results:
        print("No usage data found")
        return

    print("  Token cost estimate\n")
    print(
        f"  {bold('MODEL'):<45} {bold('INPUT'):>12} {bold('OUTPUT'):>12} {bold('COST'):>10}"
    )
    print(f"  {'─' * 45} {'─' * 12} {'─' * 12} {'─' * 10}")
    uncosted = []
    for r in results:
        inp_str = f"{r['input_tokens']:,}"
        out_str = f"{r['output_tokens']:,}"
        if r["cost_usd"] is not None:
            cost_str = f"${r['cost_usd']:.2f}"
        else:
            cost_str = dim("n/a")
            uncosted.append(r["model"])
        print(
            f"  {_sanitize(r['model']):<45} {inp_str:>12} {out_str:>12} {cost_str:>10}"
        )
    print(f"  {'─' * 45} {'─' * 12} {'─' * 12} {'─' * 10}")
    print(
        f"  {bold('TOTAL'):<45} {total_input:>12,} {total_output:>12,} "
        f"{bold(f'${total_cost:.2f}'):>10}"
    )
    if uncosted:
        uncosted_str = ", ".join(uncosted)
        print(f"\n  {dim('Uncosted models: ' + uncosted_str)}")
    print(
        f"\n  {dim('Rates: opus $15/$75, sonnet $3/$15, haiku $0.25/$1.25 per 1M tokens')}"
    )
    print()


def _calculate_session_cost(transcript_path: "Optional[Path]") -> "Optional[str]":
    """Return a one-line cost summary for a single transcript, or None."""
    if transcript_path is None or not transcript_path.exists():
        return None

    cost_rates = {
        "opus": {"input": 15.0, "output": 75.0},
        "sonnet": {"input": 3.0, "output": 15.0},
        "haiku": {"input": 0.25, "output": 1.25},
    }
    model_usage: dict = defaultdict(lambda: {"input_tokens": 0, "output_tokens": 0})

    for entry in iter_messages(transcript_path):
        if entry.get("type") != "assistant":
            continue
        msg = entry.get("message", {})
        if not isinstance(msg, dict):
            continue
        model = msg.get("model", "unknown")
        if not isinstance(model, str) or not model or model.startswith("<"):
            model = "unknown"
        usage = msg.get("usage") or {}
        if isinstance(usage, dict):
            input_total = (
                _safe_int(usage.get("input_tokens", 0))
                + _safe_int(usage.get("cache_creation_input_tokens", 0))
                + _safe_int(usage.get("cache_read_input_tokens", 0))
            )
            model_usage[model]["input_tokens"] += input_total
            model_usage[model]["output_tokens"] += _safe_int(usage.get("output_tokens", 0))

    if not model_usage:
        return None

    total_cost = 0.0
    total_tokens = 0
    model_costs: list = []

    for model, usage in model_usage.items():
        inp = usage["input_tokens"]
        out = usage["output_tokens"]
        tokens = inp + out
        total_tokens += tokens
        model_lower = model.lower()
        rate_key = None
        if "opus" in model_lower:
            rate_key = "opus"
        elif "sonnet" in model_lower:
            rate_key = "sonnet"
        elif "haiku" in model_lower:
            rate_key = "haiku"
        if rate_key:
            rates = cost_rates[rate_key]
            cost = (inp / 1_000_000 * rates["input"]) + (out / 1_000_000 * rates["output"])
            total_cost += cost
            model_costs.append((model, cost, tokens))

    if not total_tokens:
        return None

    parts = []
    for model, _cost, tokens in sorted(model_costs, key=lambda x: -x[2]):
        pct = int(tokens / total_tokens * 100) if total_tokens else 0
        tier = "n/a"
        if "opus" in model.lower():
            tier = "Opus"
        elif "sonnet" in model.lower():
            tier = "Sonnet"
        elif "haiku" in model.lower():
            tier = "Haiku"
        parts.append(f"{tier} {pct}%")

    breakdown = ", ".join(parts) if parts else "n/a"

    # Don't return cost string when cost is $0.00
    if total_cost < 0.005:
        return None

    return f"Estimated: ${total_cost:.2f} ({breakdown})"


def _ore_build_content(
    extracted: dict,
    session_id: str,
    project_name: str,
    cost_str: "Optional[str]" = None,
    trigger: str = "session-end",
) -> str:
    """Build ore markdown from extracted context. Returns empty string if no content."""
    has_content = any(
        extracted.get(k) for k in ("decisions", "discoveries", "errors_fixes", "unfinished")
    )
    if not has_content and not cost_str:
        return ""

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    sid_short = session_id[:8] if session_id else "unknown"
    lines = [
        f"# Ore — {now}",
        f"<!-- session: {sid_short} | project: {project_name} | trigger: {trigger} -->",
        "",
    ]
    for section, key in [
        ("Decisions", "decisions"),
        ("Discoveries", "discoveries"),
        ("Errors & Fixes", "errors_fixes"),
        ("Unfinished", "unfinished"),
    ]:
        items = extracted.get(key, [])
        if items:
            lines.append(f"## {section}")
            for item in items:
                lines.append(f"- {item}")
            lines.append("")

    if cost_str:
        lines.append("## Cost")
        lines.append(f"- {cost_str}")
        lines.append("")

    return "\n".join(lines)


def _ore_save(
    project_name: str, session_id: str, content: str, suffix: str = ""
) -> "Optional[Path]":
    """Save ore to ~/.pickel/ores/{project_name}/{date}-{session_id[:8]}{suffix}.md"""
    if not project_name or not content.strip():
        return None
    ores_dir = get_ores_dir() / project_name
    try:
        ores_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    except OSError as e:
        _warn(f"cannot create ores dir: {e}")
        return None
    sid = session_id[:8] if session_id else "unknown"
    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"{date_str}-{sid}{suffix}.md"
    ore_path = ores_dir / filename
    try:
        ore_path.write_text(content, encoding="utf-8")
        os.chmod(str(ore_path), 0o600)
    except OSError as e:
        _warn(f"cannot write ore: {e}")
        return None
    return ore_path


# ── Wrap ─────────────────────────────────────────────────────────


def cmd_wrap(args) -> None:
    """Save session summary to ~/.pickel/ores/ (SessionEnd hook)."""
    stdin_data: dict = {}
    if not sys.stdin.isatty():
        try:
            raw = sys.stdin.read().strip()
            if raw:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    stdin_data = parsed
        except (json.JSONDecodeError, ValueError):
            pass

    tp = stdin_data.get("transcript_path")
    transcript_path: "Optional[Path]" = None
    if isinstance(tp, str) and tp:
        projects_dir = get_projects_dir().resolve()
        resolved = Path(tp).resolve()
        try:
            resolved.relative_to(projects_dir)
            transcript_path = resolved
        except ValueError:
            _warn(f"transcript_path outside projects dir: {tp}")

    if transcript_path is None:
        return

    session_id = stdin_data.get("session_id", "") or ""
    cwd = stdin_data.get("cwd", "") or ""
    project_name = _project_name_from_cwd(cwd) if cwd else None
    if not project_name:
        return

    extracted = _mine_extract_context(transcript_path)

    # Don't save cost-only ores (no decisions/discoveries/errors/unfinished)
    has_context = any(
        extracted.get(k)
        for k in ("decisions", "discoveries", "errors_fixes", "unfinished")
    )
    if not has_context:
        return

    cost_str = _calculate_session_cost(transcript_path)
    content = _ore_build_content(extracted, session_id, project_name, cost_str, "session-end")

    if content.strip():
        _ore_save(project_name, session_id or "unknown", content)


# ── Recall ───────────────────────────────────────────────────────

_RECALL_MAX = 5000


def cmd_recall(args) -> None:
    """Load previous session context (SessionStart hook)."""
    stdin_data: dict = {}
    if not sys.stdin.isatty():
        try:
            raw = sys.stdin.read().strip()
            if raw:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    stdin_data = parsed
        except (json.JSONDecodeError, ValueError):
            pass

    source = stdin_data.get("source", "")
    if source and source != "startup":
        return

    cwd = stdin_data.get("cwd", "") or ""
    project_name = _project_name_from_cwd(cwd) if cwd else None
    if not project_name:
        return

    ores_dir = get_ores_dir() / project_name
    if not ores_dir.is_dir():
        return

    try:
        ore_files = [f for f in ores_dir.iterdir() if f.suffix == ".md"]
        ore_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return

    if not ore_files:
        return

    try:
        content = ore_files[0].read_text(encoding="utf-8")
    except OSError:
        return

    if len(content) > _RECALL_MAX:
        content = content[: _RECALL_MAX - 3] + "..."

    print(content)


# ── Ores ─────────────────────────────────────────────────────────


def cmd_ores(args) -> None:
    """List and view saved ores."""
    action = getattr(args, "action", "list") or "list"
    project_filter = getattr(args, "project", None)
    ores_base = get_ores_dir()

    if project_filter:
        sanitized = _sanitize_project_name(project_filter)
        if sanitized is None:
            print(f"pickel: invalid project name: {project_filter}", file=sys.stderr)
            sys.exit(1)
        project_filter = sanitized

    if action == "show":
        _ores_show(ores_base, project_filter)
        return

    _ores_list(ores_base, project_filter, getattr(args, "json", False))


def _ores_show(ores_base: Path, project_filter: "Optional[str]") -> None:
    if project_filter:
        target_dir = ores_base / project_filter
        if not target_dir.is_dir():
            print(f"No ores found for project: {project_filter}")
            return
        try:
            ore_files = sorted(
                (f for f in target_dir.glob("*.md")),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
        except OSError:
            ore_files = []
        if not ore_files:
            print(f"No ores found for project: {project_filter}")
            return
        try:
            print(ore_files[0].read_text(encoding="utf-8"))
        except OSError as e:
            print(f"pickel: cannot read ore: {e}", file=sys.stderr)
            sys.exit(1)
        return

    best_file: "Optional[Path]" = None
    best_mtime = 0.0
    if ores_base.is_dir():
        try:
            for proj_dir in ores_base.iterdir():
                if not proj_dir.is_dir():
                    continue
                for ore_file in proj_dir.glob("*.md"):
                    try:
                        mtime = ore_file.stat().st_mtime
                        if mtime > best_mtime:
                            best_mtime = mtime
                            best_file = ore_file
                    except OSError:
                        pass
        except OSError:
            pass

    if best_file is None:
        print("No ores found")
        return
    try:
        print(best_file.read_text(encoding="utf-8"))
    except OSError as e:
        print(f"pickel: cannot read ore: {e}", file=sys.stderr)
        sys.exit(1)


def _ores_list(ores_base: Path, project_filter: "Optional[str]", as_json: bool) -> None:
    project_rows: list = []

    if ores_base.is_dir():
        try:
            for proj_dir in sorted(ores_base.iterdir()):
                if not proj_dir.is_dir():
                    continue
                if project_filter and project_filter.lower() not in proj_dir.name.lower():
                    continue
                try:
                    ore_files = sorted(
                        (f for f in proj_dir.glob("*.md")),
                        key=lambda p: p.stat().st_mtime,
                        reverse=True,
                    )
                except OSError:
                    continue
                if not ore_files:
                    continue
                total_size = sum(f.stat().st_size for f in ore_files if f.exists())
                latest_mtime = ore_files[0].stat().st_mtime
                project_rows.append(
                    {
                        "name": proj_dir.name,
                        "count": len(ore_files),
                        "latest_mtime": latest_mtime,
                        "total_size": total_size,
                    }
                )
        except OSError as e:
            _warn(f"cannot list ores dir: {e}")

    if as_json:
        print(json.dumps({"projects": project_rows}, ensure_ascii=False, indent=2))
        return

    print(f"  {dim('~/.pickel/ores/')}\n")

    if not project_rows:
        if project_filter:
            print(f"  No ores found for project: {project_filter}")
        else:
            print("  No ores found")
        return

    now = time.time()
    print(
        f"  {bold('PROJECT'):<22} {bold('ORES'):>6}  {bold('LATEST'):<12} {bold('SIZE'):>8}"
    )
    print(f"  {'─' * 22} {'─' * 6}  {'─' * 12} {'─' * 8}")

    total_ores = 0
    total_size = 0
    for proj in project_rows:
        name = _sanitize(proj["name"])[:22]
        count = proj["count"]
        age = _format_age(now - proj["latest_mtime"])
        size = _format_size(proj["total_size"])
        total_ores += count
        total_size += proj["total_size"]
        print(f"  {name:<22} {count:>6}  {age:<12} {size:>8}")

    print()
    print(f"  {total_ores} ores · {_format_size(total_size)} total")
    print()


# ── Mine: helpers ────────────────────────────────────────────────


def _mine_find_fallback_session(
    args: "argparse.Namespace", stdin_data: dict
) -> "Optional[Path]":
    base = get_projects_dir()
    projects = find_projects(base)

    project_name = getattr(args, "project", None)
    if project_name:
        # Prefer exact match, then partial match
        exact = [(k, v) for k, v in projects.items() if project_name.lower() == k.lower()]
        if exact:
            sessions = find_sessions(exact[0][1])
            return sessions[0] if sessions else None
        matches = [
            (k, v) for k, v in projects.items() if project_name.lower() in k.lower()
        ]
        if len(matches) == 1:
            sessions = find_sessions(matches[0][1])
            return sessions[0] if sessions else None
        if len(matches) > 1:
            candidates = ", ".join(k for k, _ in matches)
            print(
                f"pickel: ambiguous -p '{project_name}': {candidates}",
                file=sys.stderr,
            )
            sys.exit(1)
        return None

    cwd = stdin_data.get("cwd", "")
    if isinstance(cwd, str) and cwd:
        repo_name = Path(cwd).name
        if repo_name:
            for _proj_name, proj_dir in projects.items():
                if normalize_project_name(proj_dir.name) == repo_name:
                    sessions = find_sessions(proj_dir)
                    if sessions:
                        return sessions[0]

    best: "Optional[tuple[float, Path]]" = None
    for _proj_name, proj_dir in projects.items():
        sessions = find_sessions(proj_dir)
        if sessions:
            try:
                mtime = sessions[0].stat().st_mtime
                if best is None or mtime > best[0]:
                    best = (mtime, sessions[0])
            except OSError:
                pass
    return best[1] if best else None


def _mine_extract_context(transcript_path: "Optional[Path]") -> dict:
    _MAX_DECISIONS = 20
    _MAX_DISCOVERIES = 20
    _MAX_ERRORS_FIXES = 20
    _MAX_UNFINISHED = 10

    decisions: list = []
    decisions_seen: set = set()
    discoveries: list = []
    discoveries_seen: set = set()
    errors_fixes: list = []
    errors_fixes_seen: set = set()
    unfinished: list = []
    unfinished_seen: set = set()
    last_user_text: "Optional[str]" = None

    def decisions_add(item: str) -> None:
        if len(decisions) < _MAX_DECISIONS and item not in decisions_seen:
            decisions_seen.add(item)
            decisions.append(item)

    def discoveries_add(item: str) -> None:
        if len(discoveries) < _MAX_DISCOVERIES and item not in discoveries_seen:
            discoveries_seen.add(item)
            discoveries.append(item)

    def errors_fixes_add(item: str) -> None:
        if len(errors_fixes) < _MAX_ERRORS_FIXES and item not in errors_fixes_seen:
            errors_fixes_seen.add(item)
            errors_fixes.append(item)

    def unfinished_add(item: str) -> None:
        if len(unfinished) < _MAX_UNFINISHED and item not in unfinished_seen:
            unfinished_seen.add(item)
            unfinished.append(item)

    if transcript_path is not None and transcript_path.exists():
        for entry in iter_messages(transcript_path):
            etype = entry.get("type", "")
            if etype not in ("user", "assistant", "system"):
                continue

            # Handle system entries (API errors)
            if etype == "system":
                subtype = entry.get("subtype", "")
                if subtype == "api_error":
                    msg = entry.get("message", {})
                    error_text = ""
                    if isinstance(msg, dict):
                        error_text = str(msg.get("error", msg.get("message", "")))[:200]
                    elif isinstance(msg, str):
                        error_text = msg[:200]
                    if error_text:
                        errors_fixes_add(f"[API Error] {error_text}")
                continue

            text = extract_text(entry)
            if not text:
                continue

            first_line = text.strip().split("\n")[0][:200]

            if etype == "user":
                last_user_text = text.strip()
                if _MINE_DECISION_USER_RE.search(text):
                    decisions_add(first_line)
                for pat in _MINE_CORRECTION_RE_LIST:
                    if pat.search(text):
                        errors_fixes_add(first_line)
                        break
            elif etype == "assistant":
                if _MINE_DECISION_ASST_RE.search(text):
                    decisions_add(first_line)

            if _MINE_DISCOVERY_RE.search(text):
                discoveries_add(first_line)

            if _MINE_ERROR_RE.search(text):
                errors_fixes_add(first_line)

            if _MINE_UNFINISHED_RE.search(text):
                unfinished_add(first_line)

    if last_user_text:
        last_line = last_user_text.split("\n")[0][:200]
        if _MINE_UNFINISHED_RE.search(last_user_text) or len(last_user_text) > 50:
            tag = f"[Last] {last_line}"
            if last_line not in unfinished_seen:
                unfinished_add(tag)

    return {
        "decisions": decisions,
        "discoveries": discoveries,
        "errors_fixes": errors_fixes,
        "unfinished": unfinished,
    }


def _mine_format_context(extracted: dict) -> str:
    has_content = any(
        extracted.get(k)
        for k in ("decisions", "discoveries", "errors_fixes", "unfinished")
    )
    if not has_content:
        return "No significant context extracted."

    lines = ["# pickel mine — Session Context Rescue", ""]
    for section, key in [
        ("Decisions", "decisions"),
        ("Discoveries", "discoveries"),
        ("Errors & Fixes", "errors_fixes"),
        ("Unfinished", "unfinished"),
    ]:
        items = extracted.get(key, [])
        if items:
            lines.append(f"## {section}")
            for item in items:
                lines.append(f"- {item}")
            lines.append("")

    result = "\n".join(lines)
    if len(result) > _MINE_MAX_CONTEXT:
        result = result[: _MINE_MAX_CONTEXT - 3] + "..."
    return result


def _mine_print_dry_run(extracted: dict, transcript_path: "Optional[Path]") -> None:
    src = str(transcript_path) if transcript_path else "(no transcript)"
    print(f"  {bold('pickel mine')} — dry run")
    print(f"  {dim('source:')} {_sanitize(src)}\n")
    for section, key in [
        ("Decisions", "decisions"),
        ("Discoveries", "discoveries"),
        ("Errors & Fixes", "errors_fixes"),
        ("Unfinished", "unfinished"),
    ]:
        items = extracted.get(key, [])
        print(f"  {bold(section)} ({len(items)})")
        for item in items[:5]:
            print(f"    - {_sanitize(item)}")
        if len(items) > 5:
            print(f"    {dim(f'...+{len(items) - 5} more')}")
        print()


def _mine_empty_hook_output() -> None:
    """Print empty context as hook output and return."""
    extracted = {"decisions": [], "discoveries": [], "errors_fixes": [], "unfinished": []}
    context_text = _mine_format_context(extracted)
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PreCompact",
            "additionalContext": context_text,
        }
    }
    print(json.dumps(output, ensure_ascii=False))


def cmd_mine(args) -> None:
    """Extract key context from session (PreCompact hook)."""
    transcript_path: "Optional[Path]" = None
    stdin_data: dict = {}
    is_hook_mode = False

    # Fix 5: --transcript existence check
    if getattr(args, "transcript", None):
        transcript_path = Path(args.transcript)
        if not transcript_path.is_file():
            print(f"pickel: transcript not found: {transcript_path}", file=sys.stderr)
            sys.exit(1)
    else:
        if not sys.stdin.isatty():
            try:
                raw = sys.stdin.read().strip()
                if raw:
                    # Fix 4: type check for parsed JSON
                    parsed = json.loads(raw)
                    if isinstance(parsed, dict):
                        stdin_data = parsed
                    # else: non-dict JSON ([], null, string) — treat as empty
                    tp = stdin_data.get("transcript_path")
                    if isinstance(tp, str) and tp:
                        # Fix 11: security check for stdin transcript_path
                        projects_dir = get_projects_dir().resolve()
                        resolved = Path(tp).resolve()
                        try:
                            resolved.relative_to(projects_dir)
                        except ValueError:
                            _warn(f"transcript_path outside projects dir: {tp}")
                            _mine_empty_hook_output()
                            return
                        transcript_path = resolved
                    hook_event_name = stdin_data.get("hook_event_name")
                    if hook_event_name:
                        is_hook_mode = True
            except (json.JSONDecodeError, ValueError):
                # Fix 9: malformed stdin — warn and return empty context
                _warn("malformed stdin JSON, returning empty context")
                _mine_empty_hook_output()
                return

    # Fix 10: hook mode — no global fallback
    if transcript_path is None:
        if is_hook_mode:
            # Hook invocation without transcript — return empty context
            _mine_empty_hook_output()
            return
        else:
            # Manual CLI — fallback is OK
            transcript_path = _mine_find_fallback_session(args, stdin_data)

    extracted = _mine_extract_context(transcript_path)

    if getattr(args, "dry_run", False):
        _mine_print_dry_run(extracted, transcript_path)
        return

    if getattr(args, "json", False):
        print(json.dumps(extracted, ensure_ascii=False, indent=2))
        return

    context_text = _mine_format_context(extracted)
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PreCompact",
            "additionalContext": context_text,
        }
    }
    print(json.dumps(output, ensure_ascii=False))

    # Side-effect: persist ore (best-effort, failures are silently ignored)
    try:
        _sid = stdin_data.get("session_id", "") or ""
        _cwd = stdin_data.get("cwd", "") or ""
        _proj = _project_name_from_cwd(_cwd) if _cwd else None
        if _proj and _sid:
            _content = _ore_build_content(extracted, _sid, _proj, trigger="compact")
            if _content.strip():
                _ore_save(_proj, _sid, _content, suffix="-compact")
    except Exception:
        pass


# ── CLI ──────────────────────────────────────────────────────────


def _positive_int(value: str) -> int:
    """argparse type: positive integer (>= 1)."""
    try:
        n = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid integer: '{value}'")
    if n < 1:
        raise argparse.ArgumentTypeError(f"must be >= 1, got {n}")
    return n


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pickel",
        description="A pickaxe for mining Claude Code conversation logs",
    )
    p.add_argument("-V", "--version", action="version", version=f"pickel {__version__}")
    p.add_argument(
        "-q", "--quiet", action="store_true", help="Suppress warnings on stderr"
    )

    sub = p.add_subparsers(dest="command")

    # search
    s = sub.add_parser("search", aliases=["s"], help="Search conversation logs")
    s.add_argument("query", help="Search query")
    s.add_argument("-p", "--project", help="Filter by project name")
    s.add_argument(
        "-m",
        "--max",
        type=_positive_int,
        default=10,
        help="Max results (default: 10)",
    )
    s.add_argument("-r", "--regex", action="store_true", help="Use regex search")
    s.add_argument(
        "--since",
        help="Filter sessions since date, YYYY-MM-DD (by file modification time)",
    )
    s.add_argument(
        "--today",
        action="store_true",
        help="Only today's sessions (by file modification time)",
    )
    s.add_argument(
        "--compact", action="store_true", help="Compact output (for AI tools)"
    )
    s.add_argument("--json", action="store_true", help="JSON output")

    # context
    ctx = sub.add_parser("context", aliases=["ctx"], help="Show session context")
    ctx.add_argument("session", help="Session ID (partial match)")
    ctx.add_argument("-p", "--project", help="Filter by project")
    ctx.add_argument("--json", action="store_true", help="JSON output")

    # last
    la = sub.add_parser("last", aliases=["l"], help="Last session for a project")
    la.add_argument("project", help="Project name")
    la.add_argument("--json", action="store_true", help="JSON output")

    # projects
    pj = sub.add_parser("projects", aliases=["p"], help="List all projects")
    pj.add_argument(
        "--limit",
        type=_positive_int,
        help="Max number of projects to display",
    )
    pj.add_argument("--json", action="store_true", help="JSON output")

    # chat
    ch = sub.add_parser("chat", help="Show session conversation in chat format")
    ch.add_argument("session", nargs="?", help="Session ID (partial match)")
    ch.add_argument("-p", "--project", help="Project name")
    ch.add_argument(
        "--last",
        type=_positive_int,
        help="Show last N sessions (default: 1)",
    )
    ch.add_argument("--json", action="store_true", help="JSON output")

    # errors
    er = sub.add_parser("errors", help="Extract corrections and API errors")
    er.add_argument("-p", "--project", help="Filter by project")
    er.add_argument("--json", action="store_true", help="JSON output")

    # tools
    tl = sub.add_parser("tools", help="Show tool usage frequency")
    tl.add_argument("-p", "--project", help="Filter by project")
    tl.add_argument("--json", action="store_true", help="JSON output")

    # cost
    co = sub.add_parser("cost", help="Estimate token costs")
    co.add_argument("-p", "--project", help="Filter by project")
    co.add_argument("--today", action="store_true", help="Only today")
    co.add_argument("--month", action="store_true", help="This month")
    co.add_argument("--json", action="store_true", help="JSON output")

    # mine
    mi = sub.add_parser(
        "mine", help="Extract key context from session (PreCompact hook)"
    )
    mi.add_argument("--transcript", help="Path to transcript file (overrides stdin)")
    mi.add_argument("-p", "--project", help="Project name (for fallback)")
    mi.add_argument(
        "--json", action="store_true", help="JSON output (raw extracted data)"
    )
    mi.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="Show what would be extracted without hook output",
    )

    # wrap
    sub.add_parser("wrap", help="Save session summary to ores (SessionEnd hook)")

    # recall
    sub.add_parser("recall", help="Load previous session context (SessionStart hook)")

    # ores
    or_ = sub.add_parser("ores", help="List and view saved ores")
    or_.add_argument(
        "action",
        nargs="?",
        default="list",
        choices=["list", "show"],
        help="Action: list (default) or show",
    )
    or_.add_argument("-p", "--project", help="Filter by project name")
    or_.add_argument("--json", action="store_true", help="JSON output")

    return p


def main():
    global _QUIET
    parser = build_parser()
    args = parser.parse_args()

    if getattr(args, "quiet", False):
        _QUIET = True

    if not args.command:
        parser.print_help()
        sys.exit(0)

    cmd = args.command
    if cmd in ("search", "s"):
        cmd_search(args)
    elif cmd in ("context", "ctx"):
        cmd_context(args)
    elif cmd in ("last", "l"):
        cmd_last(args)
    elif cmd in ("projects", "p"):
        cmd_projects(args)
    elif cmd == "chat":
        cmd_chat(args)
    elif cmd == "errors":
        cmd_errors(args)
    elif cmd == "tools":
        cmd_tools(args)
    elif cmd == "cost":
        cmd_cost(args)
    elif cmd == "mine":
        cmd_mine(args)
    elif cmd == "wrap":
        cmd_wrap(args)
    elif cmd == "recall":
        cmd_recall(args)
    elif cmd == "ores":
        cmd_ores(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
