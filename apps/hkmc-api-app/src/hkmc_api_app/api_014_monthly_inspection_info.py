from __future__ import annotations

from typing import Any

from hkmc_api_app import common


def indata(*, vendor: str, date: str) -> dict[str, Any]:
    return {
        "I_LIFNR": vendor,
        "I_SPMON": date[:6],
    }


API = common.Api(
    index="014",
    name="MonthlyInspectionInfo",
    ifid="MMPM8005",
    document_type="ZFMMP_S_API_GRIV_D9",
    indata=indata,
)
