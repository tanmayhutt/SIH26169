"""Export a Claude Code session log to a readable Markdown transcript, secrets removed.

Claude Code stores each session on the machine it ran on (~/.claude/projects/<project>/<id>.jsonl).
That log never travels with the repository, so this tool turns it into a Markdown file a teammate
can read: every message from the person and every reply from the assistant, in order, with each
tool call reduced to one line (the command's description) and tool output left out. Passwords,
tokens and e-mail addresses are replaced before anything is written.

    python tools/export_chat.py <session.jsonl> docs/history/<name>.md
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

SECRETS = [  # exact strings that must never appear in the export; add to this list, never remove
    "khalibottle", "tanmay123", "govind.pandey", "govindup63", "tiwaritanmay1021", "govind",
]
PATTERNS = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "<e-mail>"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"), "<github token>"),
    (re.compile(r"(?i)(password|passwd|token|secret)(\s*[:=]\s*)\S+"), r"\1\2<redacted>"),
]


def clean(text: str) -> str:
    for s in SECRETS:
        text = text.replace(s, "<redacted>")
    for pat, rep in PATTERNS:
        text = pat.sub(rep, text)
    return text


def blocks(msg) -> list:
    c = msg.get("content")
    if isinstance(c, str):
        return [{"type": "text", "text": c}]
    return c or []


def main(src: str, dst: str) -> None:
    out, n_user, n_asst, n_tool = [], 0, 0, 0
    first = last = None
    day = None
    for line in open(src, encoding="utf-8"):
        try:
            j = json.loads(line)
        except json.JSONDecodeError:
            continue
        if j.get("type") not in ("user", "assistant") or j.get("isSidechain"):
            continue
        ts = j.get("timestamp", "")
        if ts:
            first = first or ts; last = ts
            d = ts[:10]
            if d != day:
                day = d
                out.append(f"\n## {datetime.fromisoformat(ts.replace('Z', '+00:00')).strftime('%A %d %B %Y')}\n")
        for b in blocks(j.get("message", {})):
            t = b.get("type")
            if j["type"] == "user" and t == "text":
                text = b["text"].strip()
                if not text or text.startswith("<") and text.endswith(">") and "system-reminder" in text:
                    continue
                text = re.sub(r"<system-reminder>.*?</system-reminder>", "", text, flags=re.S).strip()
                text = re.sub(r"<task-notification>.*?</task-notification>", "", text, flags=re.S).strip()
                text = re.sub(r"\[SYSTEM NOTIFICATION - NOT USER INPUT\].*?(?=\n\n|$)", "", text, flags=re.S).strip()
                if not text or text.startswith("<local-command-caveat>") or "[Request interrupted by user" in text and len(text) < 60:
                    continue
                n_user += 1
                out.append(f"\n**Tanmay** ({ts[11:16]} UTC):\n\n{clean(text)}\n")
            elif j["type"] == "assistant" and t == "text":
                text = b["text"].strip()
                if text:
                    n_asst += 1
                    out.append(f"\n**Claude**:\n\n{clean(text)}\n")
            elif j["type"] == "assistant" and t == "tool_use":
                n_tool += 1
                inp = b.get("input", {}) or {}
                what = inp.get("description") or inp.get("file_path") or inp.get("prompt", "")[:80] or inp.get("query", "") or ""
                out.append(f"\n- *{b.get('name')}*: {clean(str(what))[:160]}")
    head = (f"# Chat transcript: the ARGUS project, {first[:10]} to {last[:10]}\n\n"
            f"Exported from the owner's Claude Code session log by `tools/export_chat.py`. {n_user} messages from the "
            f"owner, {n_asst} replies, {n_tool} tool calls (each shown as one line; their output is not included). "
            f"Passwords, tokens and e-mail addresses are removed. This is a record of how the work happened; the current "
            f"state of the project is in `docs/HANDOVER.md` and `docs/KNOWLEDGE_TRANSFER.md`, which are authoritative "
            f"where they differ from something said here.\n")
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    Path(dst).write_text(head + "".join(out), encoding="utf-8")
    print(f"{dst}: {Path(dst).stat().st_size / 1e6:.1f} MB, {n_user} user messages, {n_asst} replies, {n_tool} tool calls")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
