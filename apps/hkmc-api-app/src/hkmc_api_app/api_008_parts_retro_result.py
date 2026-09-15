from __future__ import annotations

from typing import Any

from hkmc_api_app import common

RETRO_DAY_LIMIT = 10


def retro_spmon(date: str) -> str:
    year, month, day = int(date[:4]), int(date[4:6]), int(date[6:8])
    if day > RETRO_DAY_LIMIT:
        return f"{year}{month:02d}"

    if month == 1:
        return f"{year - 1}12"
    return f"{year}{month - 1:02d}"


def indata(*, vendor: str, date: str) -> dict[str, Any]:
    return {
        "I_LIFNR": vendor,
        "I_SPMON": retro_spmon(date),
    }


API = common.Api(
    index="008",
    name="PartsRetroResult",
    ifid="MMPM8010",
    document_type="ZFMMP_S_API_RETRO_RESULT",
    indata=indata,
)
