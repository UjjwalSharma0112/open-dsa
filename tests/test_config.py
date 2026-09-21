from pathlib import Path

import pytest

from opendsa import config as cfgmod

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "config.toml"
TMP = ROOT / ".tmp-config-test.toml"


def _load_text(text: str) -> cfgmod.Config:
    TMP.write_text(text, encoding="utf-8")
    try:
        return cfgmod.load_config(str(TMP))
    finally:
        TMP.unlink(missing_ok=True)


def _load_tweaked(replace: tuple[str, str]) -> cfgmod.Config:
    old, new = replace
    text = DEFAULT.read_text(encoding="utf-8")
    assert old in text, f"pattern {old!r} not found in config.toml"
    return _load_text(text.replace(old, new, 1))


def _load_curriculum(new_block: str) -> cfgmod.Config:
    text = DEFAULT.read_text(encoding="utf-8")
    start = text.index("[curriculum]")
    arr = text.index("patterns = [", start)
    close = text.index("]", arr)
    return _load_text(text[:arr] + f"patterns = {new_block}" + text[close + 1 :])


def test_load_default_config() -> None:
    cfg = cfgmod.load_config(str(DEFAULT))
    assert cfg.app.database_path.is_absolute()
    assert cfg.context.last_n_turns == 8
    assert cfg.context.compaction_threshold_percent == 70
    assert 0 < cfg.context.compaction_threshold_percent <= 100
    assert cfg.doubts.loop_cap == 3
    assert cfg.mastery.min_attempts == 5
    assert cfg.mastery.min_correct_streak == 3
    assert cfg.difficulty.start == "medium"
    assert cfg.difficulty.floor == "easy"
    assert cfg.model.provider == "gemini"
    assert cfg.flavor.companies
    assert len(cfg.curriculum) == 8
    assert cfg.curriculum[0] == "two_pointer"


def test_load_missing_file_raises() -> None:
    with pytest.raises(FileNotFoundError):
        cfgmod.load_config(str(ROOT / "does-not-exist.toml"))


def test_invalid_start_difficulty_rejected() -> None:
    with pytest.raises(ValueError, match="difficulty"):
        _load_tweaked(('start = "medium"', 'start = "legendary"'))


def test_floor_hard_rejected() -> None:
    with pytest.raises(ValueError, match="floor"):
        _load_tweaked(('floor = "easy"', 'floor = "hard"'))


def test_compaction_percent_range_rejected() -> None:
    with pytest.raises(ValueError, match="compaction_threshold_percent"):
        _load_tweaked(
            ("compaction_threshold_percent = 70", "compaction_threshold_percent = 150")
        )


def test_empty_curriculum_rejected() -> None:
    with pytest.raises(ValueError, match="curriculum"):
        _load_curriculum("[]")