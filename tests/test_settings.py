from pathlib import Path

import pytest

from denon_controller.settings import Settings, load_settings, save_settings


def test_config_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "config.toml"
    settings = Settings(host="192.168.1.42", poll_interval_seconds=5)

    save_settings(settings, path)

    assert load_settings(path) == settings


def test_volume_ceiling_cannot_be_loud() -> None:
    with pytest.raises(ValueError, match="quieter"):
        Settings(volume_ceiling_db=0)
