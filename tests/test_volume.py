import pytest

from denon_controller.models import decode_volume, encode_volume


@pytest.mark.parametrize(
    ("db", "raw"),
    [
        (-80, "00"),
        (-79.5, "005"),
        (-45, "35"),
        (-30, "50"),
        (-29.5, "505"),
        (0, "80"),
        (0.5, "805"),
        (18, "98"),
    ],
)
def test_mapping(db, raw):
    assert encode_volume(db) == raw
    assert decode_volume(raw) == db


@pytest.mark.parametrize("db", [-81, 18.5, 0.1, float("nan"), float("inf")])
def test_reject_unsafe_volume(db):
    with pytest.raises(ValueError):
        encode_volume(db)


@pytest.mark.parametrize("raw", ["350", "995", "MVUP", "5", "-10", "50\rPWON", "98.5"])
def test_reject_malformed_protocol(raw):
    with pytest.raises(ValueError):
        decode_volume(raw)
