from __future__ import annotations

from typing import Any

from hkmc_api_app import common


def indata(*, vendor: str, werks: str = "", matnr: str = "") -> dict[str, Any]:
    return {
        "I_LIFNR": vendor,
        "I_WERKS": werks,
        "I_MATNR": matnr,
    }


API = common.Api(
    index="007",
    name="RealTimeShortage",
    ifid="MMPM8016",
    document_type="ZFMMP_S_API_REQMT_HQ",
    indata=indata,
    base_date=None,
    companies=("KIA",),
    out_keys=("ET_EXPORT_1", "ET_EXPORT_2"),
)
