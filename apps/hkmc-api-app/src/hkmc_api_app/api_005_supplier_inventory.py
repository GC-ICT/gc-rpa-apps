from __future__ import annotations

from typing import Any

from hkmc_api_app import common

INVENTORY_PLANTS = {
    "HMC": (
        "1011",
        "1012",
        "1013",
        "1014",
        "1015",
        "101A",
        "1019",
        "1021",
        "1031",
        "1041",
        "1070",
        "1071",
        "1072",
        "1073",
    ),
    "KIA": (
        "2911",
        "2912",
        "2921",
        "2922",
        "2923",
        "2924",
        "2925",
        "2931",
        "2932",
        "2933",
        "2934",
        "2935",
        "2941",
        "2971",
        "2972",
        "2973",
    ),
}


def indata(*, vendor: str, date: str, werks: str, matnr: str = "") -> dict[str, Any]:
    return {
        "I_LIFNR": vendor,
        "I_BASEDT": date,
        "I_WERKS": werks,
        "I_MATNR": matnr,
    }


API = common.Api(
    index="005",
    name="SupplierInventory",
    ifid="MMPM8014",
    document_type="ZFMMP_S_API_CONSIGNMNT",
    indata=indata,
)
