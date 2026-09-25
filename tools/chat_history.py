"""The team's shared chat history: one file, every person's Claude Code sessions, in order.

Claude Code keeps each session as a log on the machine it ran on
(~/.claude/projects/<project>/<session>.jsonl); nothing of it reaches the repository by itself.
This tool appends the sessions of this machine to docs/history/CHAT_LOG.md and tells you what
other people appended since you last looked, so every clone has the whole conversation.

    python tools/chat_history.py sync     # append my new messages; then list blocks new to me
    python tools/chat_history.py sync --dry-run   # show what would be appended, write nothing
    python tools/chat_history.py new      # only list blocks I have not seen yet
    python tools/chat_history.py export <session.jsonl>   # append one specific log

A session belongs to this repository when Claude Code worked inside it: every log line records
the working directory, so sessions are found wherever Claude Code was started (in the repository,
in a parent folder, on Windows, macOS or Linux). Of a session started elsewhere, the stretch from
its first to its last message inside the repository is taken.

On a merge conflict in CHAT_LOG.md, take the incoming version and run `sync` again: every message
carries an id, so only this machine's missing messages are appended. (A union merge is not safe
here: git shares identical lines such as `---` between the two sides and interleaves the blocks.)

The file holds one block per person and session ("### Session: <name>, <first day> to <last
day>"), each message once (a hidden id prevents duplicates), no clock times, tool calls as one
line each, tool output left out. Before writing, passwords, tokens and e-mail addresses are
replaced. Exact strings to remove (a site password, a handle) go one per line in a local file
`.chat_redact` next to this repository's root; it is ignored by git and must never be committed.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "docs/history/CHAT_LOG.md"
SEEN = ROOT / ".history_seen"          # per machine, ignored by git: ids of the blocks already shown
REDACT = ROOT / ".chat_redact"         # per machine, ignored by git: exact strings to remove
MARK = re.compile(r"<!-- m:([0-9a-f-]{8,}) -->")
HEADER = ("# Chat history of the ARGUS project\n\n"
          "One block per person and Claude Code session, appended by `python tools/chat_history.py sync`. Each block is that "
          "conversation in order: the person's messages, the assistant's replies, and one line per tool call (output left out). "
          "Passwords, tokens and e-mail addresses are removed. This is how the work happened; `docs/HANDOVER.md` and "
          "`docs/KNOWLEDGE_TRANSFER.md` state the current truth where they differ from something said here.\n")
PATTERNS = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "<e-mail>"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"), "<github token>"),
    (re.compile(r"(?i)\b(password|passwd|token|secret|login)\b(\s*(?:is|are|:|=)\s*)(\S+)"), r"\1\2<redacted>"),
    (re.compile(r"(?i)\b(username|user name|password)\b( of the (?:web)?site is )(\S+)( and )(\S+)"), r"\1\2<redacted>\4<redacted>"),
]


def secrets() -> list[str]:
    if REDACT.is_file():
        return [ln.strip() for ln in REDACT.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]
    return []


def clean(text: str, extra: list[str]) -> str:
    for s in extra:
        text = text.replace(s, "<redacted>")
    for pat, rep in PATTERNS:
        text = pat.sub(rep, text)
    return text


def person() -> str:
    try:
        return subprocess.run(["git", "config", "user.name"], capture_output=True, text=True, cwd=ROOT).stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _norm(path: str) -> str:
    return os.path.normcase(os.path.realpath(path))


ROOT_N = _norm(str(ROOT))


def in_repo(cwd: str | None) -> bool:
    """True when a working directory is this repository or a folder inside it."""
    if not cwd:
        return False
    c = _norm(cwd)
    return c == ROOT_N or c.startswith(ROOT_N.rstrip(os.sep) + os.sep)


def claude_dir_name(path: Path) -> str:
    """The folder name Claude Code gives a project: every character that is not a letter or a digit
    becomes '-' ('C:\\Users\\a.b\\SIH26169' -> 'C--Users-a-b-SIH26169'). Replacing only '/' missed
    Windows paths and any path with a dot, underscore or space."""
    return re.sub(r"[^A-Za-z0-9]", "-", str(path))


def repo_span(path: Path) -> tuple[int, int] | None:
    """(first, last) line numbers of this session's messages worked inside the repository, or None."""
    first = last = None
    with open(path, encoding="utf-8", errors="replace") as f:
        for i, line in enumerate(f):
            if '"cwd"' not in line:
                continue
            try:
                cwd = json.loads(line).get("cwd")
            except json.JSONDecodeError:
                continue
            if in_repo(cwd):
                first = i if first is None else first
                last = i
    return None if first is None else (first, last)


def project_logs() -> list[tuple[Path, tuple[int, int]]]:
    """This machine's Claude Code sessions that worked in this repository, oldest first, each with
    the line span that belongs to it. Every project folder is searched, so a session started in a
    parent folder (or anywhere else) is found by the working directories it records."""
    base = Path.home() / ".claude" / "projects"
    if not base.is_dir():
        return []
    own = base / claude_dir_name(ROOT)
    tag = ROOT.name.encode()
    found = []
    for d in base.iterdir():
        if not d.is_dir():
            continue
        for p in d.glob("*.jsonl"):
            if p.stat().st_size <= 5000:
                continue
            if d != own:
                with open(p, "rb") as f:          # cheap filter before parsing: the repository's folder name must occur
                    if tag not in f.read():
                        continue
            span = repo_span(p)
            if span:
                found.append((p, span))
    return sorted(found, key=lambda ps: ps[0].stat().st_mtime)


def blocks_of(msg) -> list:
    c = msg.get("content")
    return [{"type": "text", "text": c}] if isinstance(c, str) else (c or [])


def render_session(path: Path, known: set[str], who: str, span: tuple[int, int] | None = None) -> tuple[str, int, str, str]:
    """Markdown for the messages of one log that are not in `known`; returns (text, count, first day, last day).
    With `span`, only the lines from span[0] to span[1] (the part worked in this repository)."""
    extra = secrets()
    out, n, first, last = [], 0, "", ""
    for i, line in enumerate(open(path, encoding="utf-8", errors="replace")):
        if span and not (span[0] <= i <= span[1]):
            continue
        try:
            j = json.loads(line)
        except json.JSONDecodeError:
            continue
        if j.get("type") not in ("user", "assistant") or j.get("isSidechain"):
            continue
        uid = j.get("uuid", "")
        if not uid or uid in known:
            continue
        ts = j.get("timestamp", "")[:10]
        parts = []
        for b in blocks_of(j.get("message", {})):
            t = b.get("type")
            if j["type"] == "user" and t == "text":
                text = re.sub(r"<system-reminder>.*?</system-reminder>|<task-notification>.*?</task-notification>", "", b["text"], flags=re.S)
                text = re.sub(r"\[SYSTEM NOTIFICATION - NOT USER INPUT\].*?(?=\n\n|$)", "", text, flags=re.S).strip()
                if not text or text.startswith("<local-command-caveat>") or "<command-name>" in text or text.startswith("# Claude Code Doctor"):
                    continue
                if "[Request interrupted by user" in text and len(text) < 60:
                    continue
                parts.append(f"\n**{who}**:\n\n{clean(text, extra)}\n")
            elif j["type"] == "assistant" and t == "text" and b["text"].strip():
                parts.append(f"\n**Claude**:\n\n{clean(b['text'].strip(), extra)}\n")
            elif j["type"] == "assistant" and t == "tool_use":
                inp = b.get("input", {}) or {}
                what = inp.get("description") or inp.get("file_path") or (inp.get("prompt") or "")[:80] or inp.get("query") or ""
                parts.append(f"\n- *{b.get('name')}*: {clean(str(what), extra)[:160]}")
        if parts:
            known.add(uid)
            n += 1
            first = first or ts; last = ts or last
            out.append(f"<!-- m:{uid} -->" + "".join(parts))
    return "".join(out), n, first, last


def known_ids() -> set[str]:
    return set(MARK.findall(LOG.read_text(encoding="utf-8"))) if LOG.is_file() else set()


def block_ids() -> list[tuple[str, str]]:
    """(id, header) of every session block in the file."""
    if not LOG.is_file():
        return []
    return re.findall(r"<!-- s:([0-9a-f-]+) -->\n### (Session: [^\n]*)", LOG.read_text(encoding="utf-8"))


def cmd_export(logs: list, dry: bool = False) -> int:
    known = known_ids()
    who = person()
    if not LOG.is_file() and not dry:
        LOG.parent.mkdir(parents=True, exist_ok=True); LOG.write_text(HEADER, encoding="utf-8")
    added = 0
    for item in logs:
        p, span = item if isinstance(item, tuple) else (item, None)
        sid = p.stem
        text, n, first, last = render_session(p, known, who, span)
        if not n:
            continue
        if dry:
            print(f"would append {n} messages from session {sid[:8]} ({who}, {first} to {last})")
            added += n
            continue
        day = lambda d: datetime.fromisoformat(d).strftime("%d %B %Y") if d else "?"
        span = day(first) if first == last else f"{day(first)} to {day(last)}"
        existing = LOG.read_text(encoding="utf-8")
        if f"<!-- s:{sid} -->" in existing:
            # the same session continued: add the new messages to its block, which is the last one if it is ours
            LOG.write_text(existing.rstrip("\n") + "\n" + text, encoding="utf-8")
        else:
            LOG.write_text(existing.rstrip("\n") + f"\n\n---\n\n<!-- s:{sid} -->\n### Session: {who}, {span}\n" + text, encoding="utf-8")
        added += n
        print(f"appended {n} messages from session {sid[:8]} ({who}, {span})")
    if not added:
        n_found = len(logs)
        print("nothing new to append from this machine" + ("" if n_found else
              " (no Claude Code session on this machine has worked in this repository yet)"))
    return added


def cmd_new() -> None:
    seen = set(SEEN.read_text().split()) if SEEN.is_file() else set()
    mine = person()
    fresh = [(sid, h) for sid, h in block_ids() if sid not in seen and f"Session: {mine}," not in h]
    if fresh:
        print("new in the shared chat history since you last looked (read these blocks in docs/history/CHAT_LOG.md and brief the user):")
        for sid, h in fresh:
            print(f"  {h}   <!-- s:{sid} -->")
    else:
        print("no new sessions from other people in the shared chat history")
    SEEN.write_text("\n".join(sid for sid, _ in block_ids()) + "\n")


def main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "sync"
    if cmd == "export":
        cmd_export([Path(a) for a in argv[1:]]); return 0
    if cmd == "sync":
        dry = "--dry-run" in argv[1:]
        cmd_export(project_logs(), dry)
        if not dry:
            cmd_new()
        return 0
    if cmd == "new":
        cmd_new(); return 0
    print(__doc__); return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
