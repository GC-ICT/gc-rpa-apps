import pytest

from hd_seat_jit import common


def test_schedule_ids_have_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (common.SCHEDULE_ID_ENV, common.VPN_SCHEDULE_ID_ENV, common.OTP_SCHEDULE_ID_ENV):
        monkeypatch.delenv(name, raising=False)

    assert common.schedule_id() == "16"
    assert common.vpn_schedule_id() == "18"
    assert common.otp_schedule_id() == "17"


def test_schedule_id_can_be_overridden(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(common.SCHEDULE_ID_ENV, "99")

    assert common.schedule_id() == "99"


def test_headless_is_on_unless_the_env_says_otherwise(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(common.HEADLESS_ENV, raising=False)
    assert common.headless() is True

    monkeypatch.setenv(common.HEADLESS_ENV, "N")
    assert common.headless() is False


def test_the_three_assembly_plants_are_swept() -> None:
    assert common.PLANTS == ("1", "2", "3")
