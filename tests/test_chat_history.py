"""tools/chat_history.py finds a teammate's Claude Code sessions wherever they were started:
the project folder name as Claude Code writes it (Windows, dots, spaces), and sessions started in a
parent folder, of which only the stretch worked inside the repository is taken."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("chat_history", ROOT / "tools" / "chat_history.py")
ch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ch)


def test_the_project_folder_name_matches_claude_code_on_every_os():
    assert ch.claude_dir_name(Path("/Users/abjt/SIH26169")) == "-Users-abjt-SIH26169"
    assert ch.claude_dir_name("C:\\Users\\rahul.k\\Desktop\\SIH 26169") == "C--Users-rahul-k-Desktop-SIH-26169"
    assert ch.claude_dir_name("/home/a_b/SIH26169") == "-home-a-b-SIH26169"


def test_a_folder_inside_the_repository_counts_and_a_sibling_does_not():
    assert ch.in_repo(str(ROOT)) and ch.in_repo(str(ROOT / "docs"))
    assert not ch.in_repo(str(ROOT.parent)) and not ch.in_repo(str(ROOT) + "-other") and not ch.in_repo(None)


def test_a_session_started_in_a_parent_folder_keeps_only_the_repository_stretch(tmp_path):
    def rec(i, kind, text, cwd):
        m = {"role": kind, "content": text}
        return {"type": kind, "uuid": f"0000000{i}-aaaa", "timestamp": "2026-09-25T10:00:00Z", "cwd": cwd, "message": m}
    lines = [rec(1, "user", "an unrelated project", str(ROOT.parent)),
             rec(2, "user", "work on ARGUS", str(ROOT)),
             rec(3, "assistant", "a reply from a scratch folder", "/tmp/scratch"),
             rec(4, "user", "more ARGUS work", str(ROOT / "docs")),
             rec(5, "user", "back to something else", str(ROOT.parent))]
    log = tmp_path / "s.jsonl"
    log.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")
    span = ch.repo_span(log)
    assert span == (1, 3)
    text, n, _, _ = ch.render_session(log, set(), "someone", span)
    assert n == 3 and "work on ARGUS" in text and "a reply from a scratch folder" in text and "more ARGUS work" in text
    assert "unrelated" not in text and "something else" not in text
