"""pickel — A pickaxe for mining Claude Code conversation logs."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

__version__ = "0.1.0"

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


def dim(t: str) -> str: return c("2", t)
def bold(t: str) -> str: return c("1", t)
def red(t: str) -> str: return c("31", t)
def green(t: str) -> str: return c("32", t)
def yellow(t: str) -> str: return c("33", t)
def blue(t: str) -> str: return c("34", t)
def magenta(t: str) -> str: return c("35", t)
def cyan(t: str) -> str: return c("36", t)
def orange(t: str) -> str: return c("38;5;208", t)


# ── Data Dir ─────────────────────────────────────────────────────

def get_projects_dir() -> Path:
    config = os.environ.get("CLAUDE_CONFIG_DIR", os.path.expanduser("~/.claude"))
    return Path(config) / "projects"


def normalize_project_name(dirname: str) -> str:
    """Turn long dir names into short project names."""
    name = dirname
    # Remove common prefixes
    for prefix in [
        "-Users-morinpic--ghq-github-com-morinpic-",
        "-Users-morinpic--ghq-github-com-ClaudeCodeCafe-",
        "-Users-morinpic--ghq-github-com-",
        "-Users-morinpic-",
    ]:
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    return name or dirname


def find_projects(base: Path) -> dict[str, Path]:
    """Return {short_name: path} for all projects."""
    projects = {}
    if not base.is_dir():
        return projects
    for d in sorted(base.iterdir()):
        if d.is_dir() and not d.name.startswith("."):
            name = normalize_project_name(d.name)
            projects[name] = d
    return projects


def find_sessions(project_dir: Path) -> list[Path]:
    """Return all .jsonl session files sorted by mtime desc."""
    files = list(project_dir.glob("*.jsonl"))
    files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    return files


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
    query = args.query.lower()
    max_results = args.max or 10
    project_filter = args.project

    results = []

    target_projects = projects.items()
    if project_filter:
        target_projects = [
            (k, v) for k, v in projects.items()
            if project_filter.lower() in k.lower()
        ]

    for proj_name, proj_dir in target_projects:
        for session_file in find_sessions(proj_dir):
            session_id = session_file.stem[:8]
            for entry in iter_messages(session_file):
                etype = entry.get("type", "")
                if etype not in ("user", "assistant"):
                    continue
                text = extract_text(entry)
                if not text:
                    continue
                if query in text.lower():
                    role = entry.get("type", "?")
                    ts = entry.get("timestamp", "")
                    # Extract matching line
                    for line in text.split("\n"):
                        if query in line.lower():
                            results.append({
                                "project": proj_name,
                                "session": session_id,
                                "role": role,
                                "timestamp": ts,
                                "line": line.strip()[:200],
                            })
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

    if not results:
        print(f"⛏️  No results for {bold(args.query)}")
        return

    print(f"⛏️  {bold(str(len(results)))} results for {bold(args.query)}\n")

    current_proj = None
    for r in results:
        if r["project"] != current_proj:
            current_proj = r["project"]
            print(f"  {orange(current_proj)} {dim(r['session'])}")

        icon = "🧑" if r["role"] == "user" else "🤖"
        ts = r["timestamp"][:16].replace("T", " ") if r["timestamp"] else ""

        # Highlight the query in the line
        line = r["line"]
        if USE_COLOR:
            pattern = re.compile(re.escape(args.query), re.IGNORECASE)
            line = pattern.sub(lambda m: c("1;33", m.group()), line)

        print(f"    {dim(ts)} {icon} {line}")
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
    decisions = []
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
        print(json.dumps({
            "project": proj_name,
            "session": target.stem,
            "user_messages": user_msgs[:20],
            "tools_used": sorted(tools_used),
        }, ensure_ascii=False, indent=2))
        return

    print(f"⛏️  {orange(proj_name)} {dim(target.stem[:12])}\n")
    print(f"  {bold('User messages')} ({len(user_msgs)} total):")
    for i, msg in enumerate(user_msgs[:15]):
        first_line = msg.split("\n")[0][:100]
        print(f"    {dim(str(i+1)+'.'):>5} {first_line}")
    if len(user_msgs) > 15:
        print(f"    {dim(f'  ...+{len(user_msgs)-15} more')}")
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
        f"{int(age/3600)}h ago" if age > 3600
        else f"{int(age/60)}m ago" if age > 60
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
        print(json.dumps({
            "project": proj_name,
            "session": latest.stem,
            "age": age_str,
            "model": model,
            "turns": len(user_msgs),
            "tokens": total_tokens,
            "last_user": last_user,
            "last_assistant": last_assistant,
        }, ensure_ascii=False, indent=2))
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
            f"{int(age/86400)}d" if age > 86400
            else f"{int(age/3600)}h" if age > 3600
            else f"{int(age/60)}m"
        ) if last_mod else "?"
        rows.append((name, len(sessions), total_size, age_str))

    rows.sort(key=lambda r: r[2], reverse=True)

    if args.json:
        print(json.dumps([
            {"project": r[0], "sessions": r[1], "size_mb": round(r[2]/1024/1024, 1), "last": r[3]}
            for r in rows
        ], indent=2))
        return

    print(f"⛏️  {bold(str(len(rows)))} projects\n")
    print(f"  {bold('PROJECT'):<30} {bold('SESSIONS'):>8} {bold('SIZE'):>8} {bold('LAST'):>6}")
    print(f"  {'─'*30} {'─'*8} {'─'*8} {'─'*6}")
    for name, count, size, age in rows[:20]:
        size_str = f"{size/1024/1024:.1f}M"
        print(f"  {name:<30} {count:>8} {size_str:>8} {dim(age):>6}")
    print(f"\n  {dim(f'{sum(r[1] for r in rows)} sessions · {sum(r[2] for r in rows)/1024/1024/1024:.1f} GB total')}")
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
    s.add_argument("-m", "--max", type=int, default=10, help="Max results (default: 10)")
    s.add_argument("--json", action="store_true", help="JSON output")

    # context
    ctx = sub.add_parser("context", aliases=["ctx"], help="Session context summary")
    ctx.add_argument("session", help="Session ID (partial match)")
    ctx.add_argument("-p", "--project", help="Filter by project")
    ctx.add_argument("--json", action="store_true", help="JSON output")

    # last
    l = sub.add_parser("last", aliases=["l"], help="Last session for a project")
    l.add_argument("project", help="Project name")
    l.add_argument("--json", action="store_true", help="JSON output")

    # projects
    pj = sub.add_parser("projects", aliases=["p"], help="List all projects")
    pj.add_argument("--json", action="store_true", help="JSON output")

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
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
