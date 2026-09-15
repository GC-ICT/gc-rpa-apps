from __future__ import annotations

from typing import Any

from hkmc_api_app import common


def indata(
    *,
    vendor: str,
    date: str,
    werks: str = "",
    in_list: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "I_LIFNR": vendor,
        "I_BUDAT": date,
        "I_WERKS": werks,
        "IN_LIST": in_list if in_list is not None else [],
    }


API = common.Api(
    index="004",
    name="ProductionPerformance",
    ifid="MMPM8003",
    document_type="ZFMMP_S_API_HQ_GR_INFO",
    indata=indata,
    base_date=common.yesterday,
    date_fixed=True,
)
