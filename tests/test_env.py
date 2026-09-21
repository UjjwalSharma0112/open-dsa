import os
from pathlib import Path

from opendsa.env import find_dotenv, load_dotenv


def _write_env(tmp_path: Path, text: str) -> Path:
    p = tmp_path / ".env"
    p.write_text(text, encoding="utf-8")
    return p


def test_load_parses_values(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("FOO", raising=False)
    monkeypatch.delenv("BAR", raising=False)
    monkeypatch.delenv("BAZ", raising=False)
    p = _write_env(
        tmp_path,
        "# comment\n\nFOO=abc123\nexport BAR=\"with spaces\"\nBAZ='quoted'\n",
    )
    assert load_dotenv(p) is True
    assert os.environ["FOO"] == "abc123"
    assert os.environ["BAR"] == "with spaces"
    assert os.environ["BAZ"] == "quoted"


def test_load_does_not_override_existing(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FOO", "already-set")
    p = _write_env(tmp_path, "FOO=from-file\n")
    assert load_dotenv(p) is True
    assert os.environ["FOO"] == "already-set"


def test_load_ignores_malformed_lines(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("A", raising=False)
    p = _write_env(tmp_path, "A=1\nNOT A LINE\n=novalue\nBAD-KEY=x\n")
    assert load_dotenv(p) is True
    assert os.environ.get("A") == "1"
    assert "BAD-KEY" not in os.environ


def test_load_missing_file_returns_false(tmp_path: Path) -> None:
    assert load_dotenv(tmp_path / "nope.env") is False


def test_find_dotenv_from_subdirectory(monkeypatch, tmp_path: Path) -> None:
    sub = tmp_path / "a" / "b"
    sub.mkdir(parents=True)
    (tmp_path / ".env").write_text("X=1\n", encoding="utf-8")
    monkeypatch.chdir(sub)
    assert find_dotenv() == (tmp_path / ".env")