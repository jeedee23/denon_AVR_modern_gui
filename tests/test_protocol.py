from unittest.mock import patch

from denon_controller.transport.http import (
    APP_DIRECT_PATH,
    MAIN_ZONE_STATUS_PATH,
    HttpReceiver,
)


def test_power_on_uses_verified_http_endpoint_and_command() -> None:
    with patch.object(HttpReceiver, "_get", return_value=b"") as get:
        HttpReceiver("192.168.1.20").power_on()

    get.assert_called_once_with(APP_DIRECT_PATH, "PWON")


def test_refresh_uses_unverified_candidate_status_endpoint() -> None:
    payload = b"<item><Power><value>ON</value></Power></item>"
    with patch.object(HttpReceiver, "_get", return_value=payload) as get:
        state = HttpReceiver("192.168.1.20").get_main_zone_status()

    get.assert_called_once_with(MAIN_ZONE_STATUS_PATH)
    assert state.connected
