from __future__ import annotations

from typing import Any

from hkmc_api_app import common

HEADER_KEYS = (
    "ZASNNO",
    "ZDEPDAT",
    "ZDEPTIM",
    "ZEARDAT",
    "ZEARTIM",
    "ZCARNO",
    "ZDLRNAME",
    "ZDLRMOBL",
    "ZDIVNO",
    "ZDLTLOC",
    "ZCPGATE",
    "ZCTAG_CO",
)

ITEM_KEYS = (
    "ZASNSEQ",
    "WERKS",
    "MATNR",
    "ZDLMENGE",
    "ZDLBOX",
    "ZNDONUM",
    "ZNDOSEQ",
)


def header(
    *,
    date: str,
    asn_no: str = "",
    departure_time: str = "",
    arrival_date: str = "",
    arrival_time: str = "",
    car_no: str = "",
    driver_name: str = "",
    driver_mobile: str = "",
    invoice_no: str = "",
    delivery_to: str = "",
    dock_no: str = "",
    tag_no: str = "",
) -> dict[str, str]:
    return {
        "ZASNNO": asn_no,
        "ZDEPDAT": date,
        "ZDEPTIM": departure_time,
        "ZEARDAT": arrival_date or date,
        "ZEARTIM": arrival_time,
        "ZCARNO": car_no,
        "ZDLRNAME": driver_name,
        "ZDLRMOBL": driver_mobile,
        "ZDIVNO": invoice_no,
        "ZDLTLOC": delivery_to,
        "ZCPGATE": dock_no,
        "ZCTAG_CO": tag_no,
    }


def item(
    *,
    asn_seq: str = "",
    werks: str = "",
    matnr: str = "",
    quantity: str = "",
    boxes: str = "",
    order_no: str = "",
    order_seq: str = "",
) -> dict[str, str]:
    return {
        "ZASNSEQ": asn_seq,
        "WERKS": werks,
        "MATNR": matnr,
        "ZDLMENGE": quantity,
        "ZDLBOX": boxes,
        "ZNDONUM": order_no,
        "ZNDOSEQ": order_seq,
    }


def indata(
    *,
    vendor: str,
    headers: list[dict[str, str]],
    items: list[dict[str, str]],
    asn_no: str = "",
) -> dict[str, Any]:
    return {
        "I_LIFNR": vendor,
        "I_ZASNNO": asn_no,
        "IT_IMPORT1": headers,
        "IT_IMPORT2": items,
    }


API = common.Api(
    index="009",
    name="PartsShipmentCreation",
    ifid="MMPM8009",
    document_type="ZFMMP_R_API_CREATE_LP_ASN_HQ",
    indata=indata,
    base_date=None,
)
