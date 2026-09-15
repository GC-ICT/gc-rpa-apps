from __future__ import annotations

from typing import Any

from hkmc_api_app import common


def indata(*, vendor: str, date: str) -> dict[str, Any]:
    return {
        "I_LIFNR": vendor,
        "I_ZDSEND2_START": date,
    }


API = common.Api(
    index="013",
    name="InspectionSuccessNotification",
    ifid="MMPM8002",
    document_type="ZFMMP_S_API_GRIV_D1",
    indata=indata,
)
