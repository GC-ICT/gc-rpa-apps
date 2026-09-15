from __future__ import annotations

from typing import Any

from hkmc_api_app import common


def indata(
    *, vendor: str, date: str, in_list: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    return {
        "I_LIFNR": vendor,
        "I_SPMON": date[:6],
        "IN_LIST": in_list if in_list is not None else [{}],
    }


API = common.Api(
    index="015",
    name="PaidSuppliedSalesStatus",
    ifid="MMPM8013",
    document_type="ZFMMP_S_API_SC_GI_DB",
    indata=indata,
)
