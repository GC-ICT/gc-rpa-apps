import json
from collections.abc import Callable

import httpx
import pytest

from hkmc_api_app import api_003_parts_shipment_info as api_003
from hkmc_api_app import api_005_supplier_inventory as api_005
from hkmc_api_app import api_007_realtime_shortage as api_007
from hkmc_api_app import api_008_parts_retro_result as api_008
from hkmc_api_app import api_009_parts_shipment_creation as api_009
from hkmc_api_app import common, registry

VENDOR = "test_vendor_alt"
TOKEN = "test_token"
DATE = "20260914"

Handler = Callable[[httpx.Request], httpx.Response]

REFERENCE = {
    "001": (
        "MMPM8006",
        "ZFMMP_S_API_DAILY_GROSS_HQ",
        '{"I_LIFNR":"test_vendor","I_DISPD":"20260914","I_ZPLDAYS":"30","I_WERKS":"","IN_LIST":[]}',
        {},
    ),
    "002": (
        "MMPM8007",
        "ZFMMP_S_API_WEEKLY_GROSS_HQ",
        '{"I_LIFNR":"test_vendor","I_DISPD":"20260914","I_WERKS":"","IN_LIST":[]}',
        {},
    ),
    "003": (
        "MMPM8008",
        "ZFMMP_S_API_DISPLAY_LP_ASN_HQ",
        '{"I_LIFNR":"test_vendor","I_ERDAT":"20260914"}',
        {},
    ),
    "004": (
        "MMPM8003",
        "ZFMMP_S_API_HQ_GR_INFO",
        '{"I_LIFNR":"test_vendor","I_BUDAT":"20260914","I_WERKS":"","IN_LIST":[]}',
        {},
    ),
    "005": (
        "MMPM8014",
        "ZFMMP_S_API_CONSIGNMNT",
        '{"I_LIFNR":"test_vendor","I_BASEDT":"20260914","I_WERKS":"1011","I_MATNR":""}',
        {"werks": "1011"},
    ),
    "006": (
        "MMPM8011",
        "ZFMMP_S_API_SC_PHY_STOCK_LIST",
        '{"I_LIFNR":"test_vendor","I_BUDAT":"20260914","I_WERKS":"1011","I_STATUS":""}',
        {},
    ),
    "007": (
        "MMPM8016",
        "ZFMMP_S_API_REQMT_HQ",
        '{"I_LIFNR":"test_vendor","I_WERKS":"","I_MATNR":""}',
        {},
    ),
    "008": (
        "MMPM8010",
        "ZFMMP_S_API_RETRO_RESULT",
        '{"I_LIFNR":"test_vendor","I_SPMON":"202609"}',
        {},
    ),
    "009": (
        "MMPM8009",
        "ZFMMP_R_API_CREATE_LP_ASN_HQ",
        None,
        {"headers": [api_009.header(date=DATE)], "items": [api_009.item()]},
    ),
    "010": (
        "MMPM8015",
        "ZFMMP_R_API_ADJ_CONSIGNMNT",
        '{"I_LIFNR":"test_vendor","I_BUDAT":"20260914","I_WERKS":"","IN_LIST":[]}',
        {"adjustments": []},
    ),
    "011": (
        "MMPM8012",
        "ZFMMP_R_API_SC_PHY_STOCK_SAVE",
        '{"I_LIFNR":"test_vendor","I_BUDAT":"20260914","I_WERKS":"","IN_LIST":[]}',
        {"results": []},
    ),
    "012": (
        "MMPM8001",
        "ZFMMP_S_API_MATERIAL_MASTER",
        '{"I_LIFNR":"test_vendor","I_WERKS":"","IN_LIST":[]}',
        {},
    ),
    "013": (
        "MMPM8002",
        "ZFMMP_S_API_GRIV_D1",
        '{"I_LIFNR":"test_vendor","I_ZDSEND2_START":"20260914"}',
        {},
    ),
    "014": (
        "MMPM8005",
        "ZFMMP_S_API_GRIV_D9",
        '{"I_LIFNR":"test_vendor","I_SPMON":"202609"}',
        {},
    ),
    "015": (
        "MMPM8013",
        "ZFMMP_S_API_SC_GI_DB",
        '{"I_LIFNR":"test_vendor","I_SPMON":"202609","IN_LIST":[{}]}',
        {},
    ),
    "016": (
        "MMPM8004",
        "ZFMMP_S_API_KANBAN_PO_DG",
        '{"I_LIFNR":"test_vendor","I_BUDAT":"20260914","I_WERKS":""}',
        {},
    ),
}

DATE_FIELD = {
    "001": ("I_DISPD", common.today),
    "002": ("I_DISPD", common.today),
    "003": ("I_ERDAT", common.today),
    "004": ("I_BUDAT", common.yesterday),
    "005": ("I_BASEDT", common.today),
    "006": ("I_BUDAT", common.today),
    "008": ("I_SPMON", lambda: api_008.retro_spmon(common.today())),
    "013": ("I_ZDSEND2_START", common.today),
    "014": ("I_SPMON", lambda: common.today()[:6]),
    "015": ("I_SPMON", lambda: common.today()[:6]),
    "016": ("I_BUDAT", common.today),
}

DATE_FIXED = {"003", "004"}

FETCH_PARAMS = {"005": {"werks": "1011"}}


def ids(api: common.Api) -> str:
    return f"{api.index}-{api.name}"


def build(api: common.Api, *, company: str = "HMC", dated: bool = True) -> dict[str, str]:
    _, _, _, params = REFERENCE[api.index]
    date = DATE if dated and api.base_date else None
    return api.payload(company=company, vendor="test_vendor", date=date, **params)


@pytest.mark.parametrize("api", registry.APIS, ids=ids)
def test_envelope_key_order(api: common.Api) -> None:
    assert tuple(build(api)) == common.ENVELOPE_KEYS


@pytest.mark.parametrize("api", registry.APIS, ids=ids)
def test_envelope_constants(api: common.Api) -> None:
    payload = build(api)

    assert payload["COMPANY"] == "HMC"
    assert payload["SENDER"] == "test_vendor"
    assert payload["RECORD_COUNT"] == "1"
    assert payload["TARGET_SYSTEM"] == "ERPMM"


@pytest.mark.parametrize("api", registry.APIS, ids=ids)
def test_matches_reference_example(api: common.Api) -> None:
    ifid, document_type, indata_json, _ = REFERENCE[api.index]
    payload = build(api)

    assert payload["IFID"] == ifid
    assert payload["DOCUMENTTYPE"] == document_type
    assert payload["SERVICE_CODE"] == f"test_vendor-MMH-B-{ifid[4:]}0"
    if indata_json is not None:
        assert payload["INDATA_JSON"] == indata_json


@pytest.mark.parametrize("api", [a for a in registry.APIS if a.supports("KIA")], ids=ids)
def test_kia_switches_system_and_path(api: common.Api) -> None:
    payload = build(api, company="KIA")

    assert payload["SERVICE_CODE"] == f"test_vendor-MMK-B-{api.ifid[4:]}0"
    assert common.RECEIVE_PATH[payload["COMPANY"]].startswith("/KGERPVENDOR")


@pytest.mark.parametrize("api", registry.APIS, ids=ids)
def test_indata_json_is_compact(api: common.Api) -> None:
    raw = build(api)["INDATA_JSON"]

    assert ", " not in raw
    assert ": " not in raw


@pytest.mark.parametrize("api", [a for a in registry.APIS if a.base_date], ids=ids)
def test_rejects_bad_date(api: common.Api) -> None:
    _, _, _, params = REFERENCE[api.index]

    with pytest.raises(ValueError, match="YYYYMMDD"):
        api.payload(company="HMC", vendor="test_vendor", date="2026-09-14", **params)


@pytest.mark.parametrize("api", registry.for_company("HMC"), ids=ids)
def test_date_rule(api: common.Api, capture_session: dict[str, str]) -> None:
    api.run(**FETCH_PARAMS.get(api.index, {}))

    indata = json.loads(json.loads(capture_session["body"])["INDATA_JSON"])
    if api.index in DATE_FIELD:
        field, expected = DATE_FIELD[api.index]
        assert indata[field] == expected()
    else:
        assert api.base_date is None


@pytest.mark.parametrize("api", registry.for_company("HMC"), ids=ids)
def test_run_sends_token_to_company_path(api: common.Api, capture_session: dict[str, str]) -> None:
    api.run(**FETCH_PARAMS.get(api.index, {}))

    assert capture_session["token"] == TOKEN
    assert capture_session["path"] == "/HGERPVENDOR/apiGERPAPIGW/GERPVENDOR/Receive"


@pytest.mark.parametrize("api", [registry.BY_INDEX[i] for i in sorted(DATE_FIXED)], ids=ids)
def test_fixed_date_rejects_override(api: common.Api, capture_session: dict[str, str]) -> None:
    with pytest.raises(ValueError, match="날짜를 지정할 수 없습니다"):
        api.run(date=DATE)


@pytest.mark.parametrize("api", [a for a in registry.APIS if a.base_date is None], ids=ids)
def test_dateless_rejects_date(api: common.Api) -> None:
    with pytest.raises(ValueError, match="날짜를 쓰지 않습니다"):
        api.check_date(DATE)


def test_registry_is_ordered_and_complete() -> None:
    assert [api.index for api in registry.APIS] == [f"{i:03d}" for i in range(1, 17)]
    assert set(registry.BY_INDEX) == set(REFERENCE)


def test_registry_separates_write_apis() -> None:
    assert [api.index for api in registry.APIS if api.writes] == ["009", "010", "011"]
    assert api_009.API not in registry.READABLE


def test_001_plan_days_and_werks_overrides() -> None:
    indata = json.loads(
        registry.BY_INDEX["001"].payload(
            company="HMC", vendor=VENDOR, date=DATE, plan_days="7", werks="1000"
        )["INDATA_JSON"]
    )

    assert indata["I_ZPLDAYS"] == "7"
    assert indata["I_WERKS"] == "1000"


@pytest.mark.parametrize("index", ["002", "004", "006", "012", "016"])
def test_werks_override(index: str) -> None:
    api = registry.BY_INDEX[index]
    payload = api.payload(
        company="HMC", vendor=VENDOR, date=DATE if api.base_date else None, werks="1014"
    )

    assert json.loads(payload["INDATA_JSON"])["I_WERKS"] == "1014"


def test_003_takes_no_werks() -> None:
    with pytest.raises(TypeError):
        api_003.API.payload(company="HMC", vendor=VENDOR, date=DATE, werks="1000")


def test_003_collect_returns_both_export_lists() -> None:
    result = {
        "outData": {
            "E_IFRESULT": "Z",
            "OUTDATA_JSON": json.dumps(
                {"ET_EXPORT1": [{"ZASNNO": "A1"}], "ET_EXPORT2": [{"MATNR": "M1"}]}
            ),
        }
    }

    assert api_003.API.collect(result) == {
        "ET_EXPORT1": [{"ZASNNO": "A1"}],
        "ET_EXPORT2": [{"MATNR": "M1"}],
    }


def test_003_collect_defaults_missing_keys_to_empty() -> None:
    result = {"outData": {"E_IFRESULT": "Z", "OUTDATA_JSON": json.dumps({"ET_EXPORT1": None})}}

    assert api_003.API.collect(result) == {"ET_EXPORT1": [], "ET_EXPORT2": []}


def test_005_requires_werks() -> None:
    with pytest.raises(TypeError):
        api_005.API.payload(company="HMC", vendor=VENDOR, date=DATE)


def test_005_inventory_plants_are_known_codes() -> None:
    for company, plants in api_005.INVENTORY_PLANTS.items():
        assert set(plants) <= set(common.PLANTS[company])


def test_collect_all_merges_plants_and_skips_failures() -> None:
    ok = {
        "outData": {
            "E_IFRESULT": "Z",
            "OUTDATA_JSON": json.dumps({"OUT_LIST": [{"MATNR": "M1"}, {"MATNR": "M2"}]}),
        }
    }
    failed = {"outData": {"E_IFRESULT": "E", "E_IFMSG": "nope"}}

    assert api_005.API.collect_all({"2931": ok, "2932": failed}) == {
        "OUT_LIST": [{"MATNR": "M1"}, {"MATNR": "M2"}]
    }


def test_008_retro_spmon_rolls_back_first_ten_days() -> None:
    assert api_008.retro_spmon("20260911") == "202609"
    assert api_008.retro_spmon("20260910") == "202608"
    assert api_008.retro_spmon("20260901") == "202608"
    assert api_008.retro_spmon("20260110") == "202512"
    assert api_008.retro_spmon("20260111") == "202601"


def test_009_indata_shape_and_key_order() -> None:
    indata = json.loads(build(api_009.API)["INDATA_JSON"])

    assert list(indata) == ["I_LIFNR", "I_ZASNNO", "IT_IMPORT1", "IT_IMPORT2"]
    assert tuple(indata["IT_IMPORT1"][0]) == api_009.HEADER_KEYS
    assert tuple(indata["IT_IMPORT2"][0]) == api_009.ITEM_KEYS


def test_009_header_defaults_arrival_date_to_departure_date() -> None:
    built = api_009.header(date=DATE)

    assert built["ZDEPDAT"] == DATE
    assert built["ZEARDAT"] == DATE


def test_009_requires_headers_and_items() -> None:
    with pytest.raises(TypeError):
        api_009.API.payload(company="HMC", vendor="test_vendor")


def test_session_serves_every_readable_api_with_one_token(
    patch_build_client: Callable[[Handler], None],
) -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path == common.TOKEN_PATH:
            return httpx.Response(200, json={"accToken": TOKEN})
        assert request.headers["AccToken"] == TOKEN
        return httpx.Response(200, json={"outData": {"E_IFRESULT": "Z"}})

    patch_build_client(handler)

    with common.session("HMC") as opened:
        for api in registry.for_company("HMC"):
            api.fetch(opened, **FETCH_PARAMS.get(api.index, {}))

    assert paths.count(common.TOKEN_PATH) == 1
    assert len(paths) == 1 + len(registry.for_company("HMC"))


def test_014_and_015_do_not_apply_retro_rule() -> None:
    for index in ("014", "015"):
        indata = json.loads(
            registry.BY_INDEX[index].payload(company="HMC", vendor="test_vendor", date="20260901")[
                "INDATA_JSON"
            ]
        )
        assert indata["I_SPMON"] == "202609"

    assert api_008.retro_spmon("20260901") == "202608"


def test_015_defaults_in_list_to_one_empty_row() -> None:
    indata = json.loads(build(registry.BY_INDEX["015"])["INDATA_JSON"])

    assert indata["IN_LIST"] == [{}]


@pytest.mark.parametrize("index", ["010", "011"])
def test_write_apis_require_their_rows(index: str) -> None:
    with pytest.raises(TypeError):
        registry.BY_INDEX[index].payload(company="HMC", vendor="test_vendor", date=DATE)


def test_company_specific_interfaces() -> None:
    assert registry.BY_INDEX["007"].companies == ("KIA",)
    assert registry.BY_INDEX["016"].companies == ("HMC",)
    assert [a.index for a in registry.APIS if a.companies != common.COMPANIES] == ["007", "016"]


def test_for_company_skips_unsupported_interfaces() -> None:
    assert "007" not in [a.index for a in registry.for_company("HMC")]
    assert "016" not in [a.index for a in registry.for_company("KIA")]
    assert "016" in [a.index for a in registry.for_company("HMC")]
    assert "007" in [a.index for a in registry.for_company("KIA")]


def test_fetch_rejects_unsupported_company(patch_build_client: Callable[[Handler], None]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"accToken": TOKEN})

    patch_build_client(handler)

    with common.session("HMC") as opened, pytest.raises(ValueError, match="인터페이스가 없습니다"):
        registry.BY_INDEX["007"].fetch(opened)


def test_out_keys_are_declared_per_api() -> None:
    assert api_003.API.out_keys == ("ET_EXPORT1", "ET_EXPORT2")
    assert api_007.API.out_keys == ("ET_EXPORT_1", "ET_EXPORT_2")
    assert api_005.API.out_keys == ("OUT_LIST",)


def test_007_collect_all_merges_plants_and_skips_failures() -> None:
    ok = {
        "outData": {
            "E_IFRESULT": "Z",
            "OUTDATA_JSON": json.dumps(
                {"ET_EXPORT_1": [{"MATNR": "M1"}], "ET_EXPORT_2": [{"MATNR": "M2"}]}
            ),
        }
    }
    failed = {"outData": {"E_IFRESULT": "E", "E_IFMSG": "데이터를 찾을 수 없습니다."}}

    assert api_007.API.collect_all({"2921": ok, "2922": ok, "2931": failed}) == {
        "ET_EXPORT_1": [{"MATNR": "M1"}, {"MATNR": "M1"}],
        "ET_EXPORT_2": [{"MATNR": "M2"}, {"MATNR": "M2"}],
    }


def test_sweep_uses_given_plants(patch_build_client: Callable[[Handler], None]) -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == common.TOKEN_PATH:
            return httpx.Response(200, json={"accToken": TOKEN})
        indata = json.loads(json.loads(request.content.decode())["INDATA_JSON"])
        seen.append(indata["I_WERKS"])
        return httpx.Response(200, json={"outData": {"E_IFRESULT": "Z"}})

    patch_build_client(handler)

    with common.session("HMC") as opened:
        api_005.API.sweep(opened, plants=("1011", "1014"))

    assert seen == ["1011", "1014"]


def test_sweep_defaults_to_every_plant_of_the_company(
    patch_build_client: Callable[[Handler], None],
) -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == common.TOKEN_PATH:
            return httpx.Response(200, json={"accToken": TOKEN})
        indata = json.loads(json.loads(request.content.decode())["INDATA_JSON"])
        seen.append(indata["I_WERKS"])
        return httpx.Response(200, json={"outData": {"E_IFRESULT": "Z"}})

    patch_build_client(handler)

    with common.session("KIA") as opened:
        api_007.API.sweep(opened)

    assert seen == list(common.PLANTS["KIA"])


def test_run_rejects_unsupported_company_before_issuing_token() -> None:
    with pytest.raises(ValueError, match="인터페이스가 없습니다"):
        api_007.API.run(company="HMC")
