from __future__ import annotations

from typing import Any

from hkmc_api_app import common


def indata(*, vendor: str, date: str, werks: str = "") -> dict[str, Any]:
    return {
        "I_LIFNR": vendor,
        "I_BUDAT": date,
        "I_WERKS": werks,
    }


API = common.Api(
    index="016",
    name="JeonjuKanbanOrderInfo",
    ifid="MMPM8004",
    document_type="ZFMMP_S_API_KANBAN_PO_DG",
    indata=indata,
    companies=("HMC",),
)
