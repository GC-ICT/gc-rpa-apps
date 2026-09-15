from __future__ import annotations

from typing import Any

from hkmc_api_app import common

ANY_PLANT = "1011"


def indata(
    *,
    vendor: str,
    date: str,
    werks: str = ANY_PLANT,
    status: str = "",
) -> dict[str, Any]:
    return {
        "I_LIFNR": vendor,
        "I_BUDAT": date,
        "I_WERKS": werks,
        "I_STATUS": status,
    }


API = common.Api(
    index="006",
    name="PaidSuppliedInventory",
    ifid="MMPM8011",
    document_type="ZFMMP_S_API_SC_PHY_STOCK_LIST",
    indata=indata,
)
