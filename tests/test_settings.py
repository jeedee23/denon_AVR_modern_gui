import pytest

from denon_controller.settings import Settings, config_path


def test_round_trip_config(tmp_path):
    path = tmp_path / "settings" / "config.toml"
    settings = Settings(host="avr.example", theme="dark", volume_ceiling=-40)
    settings.save(path)
    assert Settings.load(path) == settings
    assert not path.with_suffix(".tmp").exists()


@pytest.mark.parametrize(
    "changes",
    [
        {"host": "http://avr.example:8080/"},
        {"host": "avr\rPWON"},
        {"http_port": 0},
        {"telnet_port": 65536},
        {"volume_ceiling": float("nan")},
        {"volume_ceiling": 5},
        {"poll_interval": 0.1},
        {"timeout": 60},
        {"theme": "unknown"},
        {"auto_connect": "true"},
        {"host": ""},
        {"http_port": True},
    ],
)
def test_invalid_config(changes):
    with pytest.raises(ValueError):
        Settings(**changes)


def test_per_user_xdg_path(monkeypatch, tmp_path):
    import sys

    if sys.platform == "win32":
        monkeypatch.setenv("APPDATA", str(tmp_path))
    else:
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert config_path() == tmp_path / "denon-controller" / "config.toml"
