from __future__ import annotations

from typing import Any

from hkmc_api_app import common


def indata(
    *,
    vendor: str,
    date: str,
    adjustments: list[dict[str, Any]],
    werks: str = "",
) -> dict[str, Any]:
    return {
        "I_LIFNR": vendor,
        "I_BUDAT": date,
        "I_WERKS": werks,
        "IN_LIST": adjustments,
    }


API = common.Api(
    index="010",
    name="SupplierInventoryAdjustment",
    ifid="MMPM8015",
    document_type="ZFMMP_R_API_ADJ_CONSIGNMNT",
    indata=indata,
)
