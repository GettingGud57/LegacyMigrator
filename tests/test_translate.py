"""
Tests for migrator/translate.py. They never call the real `claude` command:
subprocess.run is swapped for a fake that records how it was called.
"""
import subprocess
from pathlib import Path

import pytest

import translate


@pytest.fixture
def fake_claude(monkeypatch):
    calls = []

    def fake_run(args, **kwargs):
        calls.append({"args": list(args), **kwargs})
        return subprocess.CompletedProcess(args, 0, stdout="```python\ndef run(spark, tables):\n    return {}\n```\n", stderr="")

    monkeypatch.setattr(translate.subprocess, "run", fake_run)
    return calls


# ---------------------------------------------------------------- works today

def test_claude_runs_outside_the_repo(fake_claude):
    """It runs in an empty temp folder, so the answer key isn't in its working folder."""
    translate.ask_claude("prompt")
    cwd = Path(fake_claude[0]["cwd"])
    assert not (cwd / "snapshots").exists()
    assert Path.cwd() not in [cwd, *cwd.parents]


def test_extract_code_takes_the_python_block():
    answer = "Here you go:\n```python\ndef run(spark, tables):\n    return {}\n```\nDone."
    assert translate.extract_code(answer) == "def run(spark, tables):\n    return {}\n"


def test_prompt_has_no_table_data():
    """The prompt describes table layouts only, never rows. Holdout rows must never get in here."""
    prompt = translate.build_prompt("SELECT 1", "Fact.Sale: Sale Key int64")
    assert "Fact.Sale: Sale Key int64" in prompt and "SELECT 1" in prompt


# ---------------------------------------------------------------- bugs

@pytest.mark.bug
def test_finding7_claude_gets_no_tools(fake_claude):
    """
    Finding 7. Running in an empty folder stops casual snooping, but `claude -p` still has
    its file and shell tools, and your own ~/.claude settings decide what they may touch.
    The translator only needs to write text, so it should get no tools at all: `--tools ""`.
    """
    translate.ask_claude("prompt")
    args = fake_claude[0]["args"]
    assert "--tools" in args and args[args.index("--tools") + 1] == "", f"called as {args}"
