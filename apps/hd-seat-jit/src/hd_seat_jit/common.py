from __future__ import annotations

from gc_rpa_core import config
from gc_rpa_core.env import optional_env

SCHEDULE_ID_ENV = "HD_SEAT_JIT_SCHEDULE_ID"
DEFAULT_SCHEDULE_ID = "16"

VPN_SCHEDULE_ID_ENV = "HD_SEAT_JIT_VPN_SCHEDULE_ID"
DEFAULT_VPN_SCHEDULE_ID = "18"

OTP_SCHEDULE_ID_ENV = "HD_SEAT_JIT_OTP_SCHEDULE_ID"
DEFAULT_OTP_SCHEDULE_ID = "17"

HEADLESS_ENV = "HD_SEAT_JIT_HEADLESS"

PLANTS = ("1", "2", "3")
CUSTOMER_CODE = "1001"


def schedule_id() -> str:
    return optional_env(SCHEDULE_ID_ENV, DEFAULT_SCHEDULE_ID)


def vpn_schedule_id() -> str:
    return optional_env(VPN_SCHEDULE_ID_ENV, DEFAULT_VPN_SCHEDULE_ID)


def otp_schedule_id() -> str:
    return optional_env(OTP_SCHEDULE_ID_ENV, DEFAULT_OTP_SCHEDULE_ID)


def load() -> config.RpaConfig:
    return config.load(schedule_id())


def headless() -> bool:
    return config.flag(optional_env(HEADLESS_ENV, "1"))
