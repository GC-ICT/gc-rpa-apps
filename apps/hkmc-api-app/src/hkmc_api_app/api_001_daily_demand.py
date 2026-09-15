from __future__ import annotations

from typing import Any

from hkmc_api_app import common

DEFAULT_PLAN_DAYS = "30"


def indata(
    *,
    vendor: str,
    date: str,
    plan_days: str = DEFAULT_PLAN_DAYS,
    werks: str = "",
    in_list: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "I_LIFNR": vendor,
        "I_DISPD": date,
        "I_ZPLDAYS": plan_days,
        "I_WERKS": werks,
        "IN_LIST": in_list if in_list is not None else [],
    }


API = common.Api(
    index="001",
    name="DailyDemand",
    ifid="MMPM8006",
    document_type="ZFMMP_S_API_DAILY_GROSS_HQ",
    indata=indata,
)
