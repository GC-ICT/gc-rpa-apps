from __future__ import annotations

from typing import Any

from hkmc_api_app import common


def indata(*, vendor: str, date: str) -> dict[str, Any]:
    return {
        "I_LIFNR": vendor,
        "I_ERDAT": date,
    }


API = common.Api(
    index="003",
    name="PartsShipmentInfo",
    ifid="MMPM8008",
    document_type="ZFMMP_S_API_DISPLAY_LP_ASN_HQ",
    indata=indata,
    date_fixed=True,
    out_keys=("ET_EXPORT1", "ET_EXPORT2"),
)
