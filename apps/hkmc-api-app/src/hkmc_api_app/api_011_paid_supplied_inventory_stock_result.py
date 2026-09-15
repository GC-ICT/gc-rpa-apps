from __future__ import annotations

from typing import Any

from hkmc_api_app import common


def indata(
    *,
    vendor: str,
    date: str,
    results: list[dict[str, Any]],
    werks: str = "",
) -> dict[str, Any]:
    return {
        "I_LIFNR": vendor,
        "I_BUDAT": date,
        "I_WERKS": werks,
        "IN_LIST": results,
    }


API = common.Api(
    index="011",
    name="PaidSuppliedInventoryStockResult",
    ifid="MMPM8012",
    document_type="ZFMMP_R_API_SC_PHY_STOCK_SAVE",
    indata=indata,
)
