"""pickel — A pickaxe for mining Claude Code conversation logs."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

__version__ = "0.2.0"

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


def green(t: str) -> str:
    return c("32", t)


def yellow(t: str) -> str:
    return c("33", t)


def blue(t: str) -> str:
    return c("34", t)


def magenta(t: str) -> str:
    return c("35", t)


def cyan(t: str) -> str:
    return c("36", t)


def orange(t: str) -> str:
    return c("38;5;208", t)


# ── Data Dir ─────────────────────────────────────────────────────


def get_projects_dir() -> Path:
    config = os.environ.get("CLAUDE_CONFIG_DIR", os.path.expanduser("~/.claude"))
    return Path(config) / "projects"


# Directories to exclude from project listing
_EXCLUDED_DIRS = {"-claude-mem-observer-sessions", "subagents"}


def normalize_project_name(dirname: str) -> str:
    """Turn long dir names into short project names.

    Detects patterns like -Users-{user}--ghq-github-com-{org}-{project}
    and returns just the last segment ({project}).
    """
    name = dirname
    # Generic pattern: -Users-<user>-...-<last_segment>
    # Matches paths encoded as dash-separated directory components
    m = re.match(r"^-Users-[^-]+-.*-([^-]+)$", name)
    if m:
        return m.group(1)
    return name or dirname


def find_projects(base: Path) -> dict[str, Path]:
    """Return {short_name: path} for all projects."""
    projects = {}
    if not base.is_dir():
        return projects
    for d in sorted(base.iterdir()):
        if d.is_dir() and not d.name.startswith(".") and d.name not in _EXCLUDED_DIRS:
            name = normalize_project_name(d.name)
            projects[name] = d
    return projects


def find_sessions(project_dir: Path) -> list[Path]:
    """Return all .jsonl session files sorted by mtime desc."""
    files = list(project_dir.glob("*.jsonl"))
    files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    return files


def _session_mtime_date(session_path: Path) -> str:
    """Return YYYY-MM-DD from file mtime."""
    return datetime.fromtimestamp(session_path.stat().st_mtime).strftime("%Y-%m-%d")


def _today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _this_month_str() -> str:
    return datetime.now().strftime("%Y-%m")


# ── JSONL Parser ─────────────────────────────────────────────────


def iter_messages(jsonl_path: Path):
    """Yield parsed entries from a .jsonl session file."""
    try:
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
    except (OSError, IOError):
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
                    parts.append(block.get("text", ""))
                elif block.get("type") == "tool_use":
                    parts.append(f"[tool:{block.get('name', '?')}]")
                elif block.get("type") == "tool_result":
                    # Compact tool results
                    sub = block.get("content", "")
                    if isinstance(sub, list):
                        for s in sub:
                            if isinstance(s, dict) and s.get("type") == "text":
                                parts.append(s.get("text", "")[:200])
                    elif isinstance(sub, str):
                        parts.append(sub[:200])
        return "\n".join(parts) if parts else None
    return None


# ── Commands ─────────────────────────────────────────────────────


def cmd_search(args):
    """Search conversation logs for a query string."""
    base = get_projects_dir()
    projects = find_projects(base)
    use_regex = getattr(args, "regex", False)
    max_results = args.max or 10
    project_filter = args.project
    compact = getattr(args, "compact", False)

    # Date filters
    since_date = None
    if getattr(args, "today", False):
        since_date = _today_str()
    elif getattr(args, "since", None):
        since_date = args.since

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

    for proj_name, proj_dir in target_projects:
        for session_file in find_sessions(proj_dir):
            # Date filter: skip sessions older than since_date
            if since_date:
                file_date = _session_mtime_date(session_file)
                if file_date < since_date:
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
                f"project:{r['project']} session:{r['session']} "
                f"role:{r['role']} text:{r['line']}"
            )
        return

    if not results:
        print(f"⛏️  No results for {bold(args.query)}")
        return

    print(f"⛏️  {bold(str(len(results)))} results for {bold(args.query)}\n")

    # Group by project -> session
    current_proj = None
    current_session = None
    for r in results:
        if r["project"] != current_proj:
            current_proj = r["project"]
            current_session = None
            print(f"  {orange(current_proj)}")
        if r["session"] != current_session:
            current_session = r["session"]
            print(f"    {dim(current_session)}")

        icon = "🧑" if r["role"] == "user" else "🤖"
        ts = r["timestamp"][:16].replace("T", " ") if r["timestamp"] else ""

        # Highlight the query in the line
        line = r["line"]
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

    # Find the session
    target = None
    proj_name = None
    for pname, pdir in projects.items():
        if args.project and args.project.lower() not in pname.lower():
            continue
        for sf in find_sessions(pdir):
            if args.session in sf.stem:
                target = sf
                proj_name = pname
                break
        if target:
            break

    if not target:
        print(f"⛏️  Session {bold(args.session)} not found", file=sys.stderr)
        sys.exit(1)

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
            content = msg.get("content", [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        tools_used.add(block.get("name", "?"))

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

    print(f"⛏️  {orange(proj_name)} {dim(target.stem[:12])}\n")
    print(f"  {bold('User messages')} ({len(user_msgs)} total):")
    for i, msg in enumerate(user_msgs[:15]):
        first_line = msg.split("\n")[0][:100]
        print(f"    {dim(str(i + 1) + '.'):>5} {first_line}")
    if len(user_msgs) > 15:
        print(f"    {dim(f'  ...+{len(user_msgs) - 15} more')}")
    print(f"\n  {bold('Tools used')}: {', '.join(sorted(tools_used)) or 'none'}")
    print()


def cmd_last(args):
    """Show the last session summary for a project."""
    base = get_projects_dir()
    projects = find_projects(base)

    matches = [(k, v) for k, v in projects.items() if args.project.lower() in k.lower()]
    if not matches:
        print(f"⛏️  Project {bold(args.project)} not found", file=sys.stderr)
        sys.exit(1)

    proj_name, proj_dir = matches[0]
    sessions = find_sessions(proj_dir)
    if not sessions:
        print(f"⛏️  No sessions in {bold(proj_name)}", file=sys.stderr)
        sys.exit(1)

    latest = sessions[0]
    mtime = latest.stat().st_mtime
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
            m = msg.get("model", "")
            if m and not m.startswith("<"):
                model = m
            usage = msg.get("usage", {})
            total_tokens += usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
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

    print(f"⛏️  {orange(proj_name)} — last session ({age_str})\n")
    print(f"  {dim('session')}  {latest.stem[:12]}")
    print(f"  {dim('model')}    {model}")
    print(f"  {dim('turns')}    {len(user_msgs)}")
    print(f"  {dim('tokens')}   {total_tokens:,}")
    print()
    print(f"  {bold('Last exchange')}:")
    print(f"    🧑 {last_user}")
    print(f"    🤖 {last_assistant}")
    print()


def cmd_projects(args):
    """List all projects with stats."""
    base = get_projects_dir()
    projects = find_projects(base)

    rows = []
    for name, pdir in projects.items():
        sessions = list(pdir.glob("*.jsonl"))
        total_size = sum(f.stat().st_size for f in sessions)
        last_mod = max((f.stat().st_mtime for f in sessions), default=0)
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
        rows.append((name, len(sessions), total_size, age_str))

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

    print(f"⛏️  {bold(str(len(rows)))} projects\n")
    print(
        f"  {bold('PROJECT'):<30} {bold('SESSIONS'):>8} {bold('SIZE'):>8} {bold('LAST'):>6}"
    )
    print(f"  {'─' * 30} {'─' * 8} {'─' * 8} {'─' * 6}")
    for name, count, size, age in rows[:20]:
        size_str = f"{size / 1024 / 1024:.1f}M"
        print(f"  {name:<30} {count:>8} {size_str:>8} {dim(age):>6}")
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
        # Find by session ID
        for pname, pdir in projects.items():
            for sf in find_sessions(pdir):
                if args.session in sf.stem:
                    session_files.append((pname, sf))
                    break
            if session_files:
                break
    elif args.project:
        matches = [
            (k, v) for k, v in projects.items() if args.project.lower() in k.lower()
        ]
        if not matches:
            print(f"⛏️  Project {bold(args.project)} not found", file=sys.stderr)
            sys.exit(1)
        proj_name, proj_dir = matches[0]
        sessions = find_sessions(proj_dir)
        n = args.last or 1
        for sf in sessions[:n]:
            session_files.append((proj_name, sf))
    else:
        print("⛏️  Specify -p PROJECT or a session ID", file=sys.stderr)
        sys.exit(1)

    if not session_files:
        print("⛏️  No sessions found", file=sys.stderr)
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
                            parts.append(block.get("text", ""))
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
        print(f"⛏️  {orange(conv['project'])} {dim(conv['session'][:12])}\n")
        for m in conv["messages"]:
            icon = "🧑" if m["role"] == "user" else "🤖"
            ts = m["timestamp"][:16].replace("T", " ") if m["timestamp"] else ""
            print(f"  {dim(ts)} {icon}")
            for line in m["text"].split("\n"):
                print(f"    {line}")
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

    # Patterns for user correction messages
    correction_patterns = [
        re.compile(r"違う", re.IGNORECASE),
        re.compile(r"ちょっと待って", re.IGNORECASE),
        re.compile(r"だめ", re.IGNORECASE),
        re.compile(r"\bwrong\b", re.IGNORECASE),
        re.compile(r"\bwait\b", re.IGNORECASE),
        re.compile(r"^no\b", re.IGNORECASE | re.MULTILINE),
    ]

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
                        for pat in correction_patterns:
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
        print("⛏️  No errors or corrections found")
        return

    corrections = [r for r in results if r["type"] == "correction"]
    api_errors = [r for r in results if r["type"] == "api_error"]

    print(f"⛏️  {bold(str(len(results)))} issues found\n")

    if corrections:
        print(f"  {bold('User corrections')} ({len(corrections)})")
        for r in corrections[:20]:
            ts = r["timestamp"][:16].replace("T", " ") if r["timestamp"] else ""
            print(
                f"    {dim(ts)} {orange(r['project'])} {dim(r['session'])} {r['text']}"
            )
        if len(corrections) > 20:
            print(f"    {dim(f'  ...+{len(corrections) - 20} more')}")
        print()

    if api_errors:
        print(f"  {red('API errors')} ({len(api_errors)})")
        for r in api_errors[:20]:
            ts = r["timestamp"][:16].replace("T", " ") if r["timestamp"] else ""
            print(
                f"    {dim(ts)} {orange(r['project'])} {dim(r['session'])} {r['text']}"
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
        print("⛏️  No tool usage found")
        return

    total = sum(count for _, count in sorted_tools)
    print(f"⛏️  Tool usage ({bold(str(total))} total calls)\n")
    print(f"  {bold('TOOL'):<40} {bold('COUNT'):>8} {bold('%'):>6}")
    print(f"  {'─' * 40} {'─' * 8} {'─' * 6}")
    for name, count in sorted_tools[:30]:
        pct = count / total * 100 if total else 0
        print(f"  {name:<40} {count:>8} {dim(f'{pct:.1f}%'):>6}")
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

    # Cost rates per 1M tokens (USD)
    cost_rates = {
        "opus": {"input": 15.0, "output": 75.0},
        "sonnet": {"input": 3.0, "output": 15.0},
    }

    # model_name -> {input_tokens, output_tokens}
    model_usage: dict[str, dict[str, int]] = defaultdict(
        lambda: {"input_tokens": 0, "output_tokens": 0}
    )

    for proj_name, proj_dir in target_projects:
        for session_file in find_sessions(proj_dir):
            if since_date:
                file_date = _session_mtime_date(session_file)
                if file_date < since_date:
                    continue
            for entry in iter_messages(session_file):
                if entry.get("type") != "assistant":
                    continue
                msg = entry.get("message", {})
                if not isinstance(msg, dict):
                    continue
                model = msg.get("model", "unknown")
                if not model or model.startswith("<"):
                    model = "unknown"
                usage = msg.get("usage", {})
                model_usage[model]["input_tokens"] += usage.get("input_tokens", 0)
                model_usage[model]["output_tokens"] += usage.get("output_tokens", 0)

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
        rate_key = "sonnet"  # default
        model_lower = model.lower()
        if "opus" in model_lower:
            rate_key = "opus"
        elif "sonnet" in model_lower:
            rate_key = "sonnet"

        rates = cost_rates[rate_key]
        cost = (inp / 1_000_000 * rates["input"]) + (out / 1_000_000 * rates["output"])
        total_cost += cost

        results.append(
            {
                "model": model,
                "input_tokens": inp,
                "output_tokens": out,
                "cost_usd": round(cost, 2),
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
        print("⛏️  No usage data found")
        return

    print("⛏️  Token cost estimate\n")
    print(
        f"  {bold('MODEL'):<45} {bold('INPUT'):>12} {bold('OUTPUT'):>12} {bold('COST'):>10}"
    )
    print(f"  {'─' * 45} {'─' * 12} {'─' * 12} {'─' * 10}")
    for r in results:
        inp_str = f"{r['input_tokens']:,}"
        out_str = f"{r['output_tokens']:,}"
        cost_str = f"${r['cost_usd']:.2f}"
        print(f"  {r['model']:<45} {inp_str:>12} {out_str:>12} {cost_str:>10}")
    print(f"  {'─' * 45} {'─' * 12} {'─' * 12} {'─' * 10}")
    print(
        f"  {bold('TOTAL'):<45} {total_input:>12,} {total_output:>12,} "
        f"{bold(f'${total_cost:.2f}'):>10}"
    )
    print(
        f"\n  {dim('Rates: opus $15/$75, sonnet $3/$15 per 1M tokens (input/output)')}"
    )
    print()


# ── CLI ──────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pickel",
        description="⛏️  A pickaxe for mining Claude Code conversation logs",
    )
    p.add_argument("-V", "--version", action="version", version=f"pickel {__version__}")

    sub = p.add_subparsers(dest="command")

    # search
    s = sub.add_parser("search", aliases=["s"], help="Search conversation logs")
    s.add_argument("query", help="Search query")
    s.add_argument("-p", "--project", help="Filter by project name")
    s.add_argument(
        "-m", "--max", type=int, default=10, help="Max results (default: 10)"
    )
    s.add_argument("-r", "--regex", action="store_true", help="Use regex search")
    s.add_argument("--since", help="Filter sessions since date (YYYY-MM-DD)")
    s.add_argument("--today", action="store_true", help="Only today's sessions")
    s.add_argument(
        "--compact", action="store_true", help="Compact output (for AI tools)"
    )
    s.add_argument("--json", action="store_true", help="JSON output")

    # context
    ctx = sub.add_parser("context", aliases=["ctx"], help="Session context summary")
    ctx.add_argument("session", help="Session ID (partial match)")
    ctx.add_argument("-p", "--project", help="Filter by project")
    ctx.add_argument("--json", action="store_true", help="JSON output")

    # last
    la = sub.add_parser("last", aliases=["l"], help="Last session for a project")
    la.add_argument("project", help="Project name")
    la.add_argument("--json", action="store_true", help="JSON output")

    # projects
    pj = sub.add_parser("projects", aliases=["p"], help="List all projects")
    pj.add_argument("--json", action="store_true", help="JSON output")

    # chat
    ch = sub.add_parser("chat", help="Show session conversation in chat format")
    ch.add_argument("session", nargs="?", help="Session ID (partial match)")
    ch.add_argument("-p", "--project", help="Project name")
    ch.add_argument("--last", type=int, help="Show last N sessions (default: 1)")
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

    return p


def main():
    parser = build_parser()
    args = parser.parse_args()

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
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
