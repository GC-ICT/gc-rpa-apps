import json
from collections.abc import Callable
from datetime import date, timedelta

import httpx
import pytest

from hkmc_api_app import common

TOKEN = "tok-1"
VENDOR = "V123"

Handler = Callable[[httpx.Request], httpx.Response]


def test_build_client_requires_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("API_BASE_URL")

    with pytest.raises(common.MissingConfigError):
        common.build_client()


def test_vendor_reads_env() -> None:
    assert common.vendor() == VENDOR


def test_vendor_requires_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VENDOR_CODE")

    with pytest.raises(common.MissingConfigError):
        common.vendor()


def test_issue_token_posts_client_credentials(
    mock_client: Callable[[Handler], httpx.Client],
) -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["auth"] = request.headers["Authorization"]
        captured["content_type"] = request.headers["Content-Type"]
        captured["body"] = request.content.decode()
        return httpx.Response(200, json={"accToken": TOKEN})

    with mock_client(handler) as client:
        assert common.issue_token(client, "HMC") == TOKEN

    assert captured["path"] == "/oauth/token"
    assert captured["auth"] == "Basic aWQ6c2VjcmV0"
    assert captured["content_type"] == "application/x-www-form-urlencoded"
    assert captured["body"] == "grant_type=client_credentials"


def test_issue_token_without_acc_token(mock_client: Callable[[Handler], httpx.Client]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"error": "nope"})

    with mock_client(handler) as client, pytest.raises(common.TokenError, match="accToken"):
        common.issue_token(client, "HMC")


def test_issue_token_raises_on_http_error(mock_client: Callable[[Handler], httpx.Client]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={})

    with mock_client(handler) as client, pytest.raises(httpx.HTTPStatusError):
        common.issue_token(client, "HMC")


def test_issue_token_requires_credentials(
    monkeypatch: pytest.MonkeyPatch, mock_client: Callable[[Handler], httpx.Client]
) -> None:
    monkeypatch.delenv("HMC_CLIENT_SECRET")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"accToken": TOKEN})

    with mock_client(handler) as client, pytest.raises(common.MissingConfigError):
        common.issue_token(client, "HMC")


def test_service_code_derives_from_ifid() -> None:
    assert common.service_code("HMC", "D191", "MMPM8006") == "D191-MMH-B-80060"
    assert common.service_code("KIA", "D191", "MMPM8006") == "D191-MMK-B-80060"
    assert common.service_code("HMC", "D191", "MMPM8003") == "D191-MMH-B-80030"


def test_receive_path_per_company() -> None:
    assert common.RECEIVE_PATH["HMC"] == "/HGERPVENDOR/apiGERPAPIGW/GERPVENDOR/Receive"
    assert common.RECEIVE_PATH["KIA"] == "/KGERPVENDOR/apiGERPAPIGW/GERPVENDOR/Receive"


def test_parse_date_accepts_yyyymmdd() -> None:
    assert common.parse_date("20260914") == "20260914"


def test_parse_date_rejects_other_formats() -> None:
    with pytest.raises(ValueError, match="YYYYMMDD"):
        common.parse_date("2026-09-14")


def test_today_and_yesterday() -> None:
    assert common.today() == date.today().strftime("%Y%m%d")
    assert common.yesterday() == (date.today() - timedelta(days=1)).strftime("%Y%m%d")


def test_envelope_key_order_and_constants() -> None:
    payload = common.envelope(
        company="HMC",
        vendor="D191",
        ifid="MMPM8006",
        document_type="ZFMMP_S_API_DAILY_GROSS_HQ",
        indata={"I_LIFNR": "D191"},
    )

    assert tuple(payload) == common.ENVELOPE_KEYS
    assert payload["RECORD_COUNT"] == "1"
    assert payload["TARGET_SYSTEM"] == "ERPMM"
    assert payload["SERVICE_CODE"] == "D191-MMH-B-80060"


def test_envelope_serializes_indata_without_spaces() -> None:
    payload = common.envelope(
        company="HMC",
        vendor="D191",
        ifid="MMPM8008",
        document_type="X",
        indata={"I_LIFNR": "D191", "I_ERDAT": "20260914"},
    )

    assert payload["INDATA_JSON"] == '{"I_LIFNR":"D191","I_ERDAT":"20260914"}'


def test_request_sends_acc_token_to_company_path(
    mock_client: Callable[[Handler], httpx.Client],
) -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["token"] = request.headers["AccToken"]
        return httpx.Response(200, json={"RESULT": "S"})

    payload = common.envelope(
        company="KIA", vendor="D191", ifid="MMPM8006", document_type="X", indata={}
    )
    with mock_client(handler) as client:
        assert common.request(client, TOKEN, payload) == {"RESULT": "S"}

    assert captured["path"] == "/KGERPVENDOR/apiGERPAPIGW/GERPVENDOR/Receive"
    assert captured["token"] == TOKEN


def test_session_issues_one_token_for_many_calls(
    patch_build_client: Callable[[Handler], None],
) -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path == common.TOKEN_PATH:
            return httpx.Response(200, json={"accToken": TOKEN})
        return httpx.Response(200, json={"RESULT": "S"})

    patch_build_client(handler)
    payload = common.envelope(
        company="HMC", vendor="D191", ifid="MMPM8006", document_type="X", indata={}
    )

    with common.session("HMC") as s:
        s.call(payload)
        s.call(payload)
        s.call(payload)

    assert paths.count(common.TOKEN_PATH) == 1
    assert len(paths) == 4


def test_session_carries_company_and_vendor(patch_build_client: Callable[[Handler], None]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"accToken": TOKEN})

    patch_build_client(handler)

    with common.session("KIA") as s:
        assert s.company == "KIA"
        assert s.vendor == VENDOR
        assert s.token == TOKEN


def test_api_run_opens_its_own_session(patch_build_client: Callable[[Handler], None]) -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path == common.TOKEN_PATH:
            return httpx.Response(200, json={"accToken": TOKEN})
        return httpx.Response(200, json={"RESULT": "S"})

    patch_build_client(handler)

    assert _api().run(date="20260914") == {"RESULT": "S"}
    assert paths == [common.TOKEN_PATH, "/HGERPVENDOR/apiGERPAPIGW/GERPVENDOR/Receive"]


def test_outdata_parses_nested_json() -> None:
    result = {"outData": {"OUTDATA_JSON": json.dumps({"OUT_LIST": [{"MATNR": "M1"}]})}}

    assert common.outdata(result) == {"OUT_LIST": [{"MATNR": "M1"}]}


def _api(**kwargs: object) -> common.Api:
    defaults: dict[str, object] = {
        "index": "000",
        "name": "Probe",
        "ifid": "MMPM8006",
        "document_type": "X",
        "indata": lambda *, vendor, date: {"I_LIFNR": vendor, "I_DISPD": date},
    }
    defaults.update(kwargs)
    return common.Api(**defaults)  # type: ignore[arg-type]


def test_resolve_date_defaults_to_base_date() -> None:
    assert _api().resolve_date(None) == common.today()
    assert _api(base_date=common.yesterday).resolve_date(None) == common.yesterday()


def test_resolve_date_accepts_override_when_not_fixed() -> None:
    assert _api().resolve_date("20260914") == "20260914"


def test_check_date_rejects_override_when_fixed() -> None:
    with pytest.raises(ValueError, match="날짜를 지정할 수 없다"):
        _api(date_fixed=True).check_date("20260914")


def test_check_date_rejects_date_on_dateless_api() -> None:
    with pytest.raises(ValueError, match="날짜를 쓰지 않는다"):
        _api(base_date=None).check_date("20260914")


def test_check_date_allows_none() -> None:
    assert _api(date_fixed=True).check_date(None) is None


def test_resolve_date_is_none_for_dateless_api() -> None:
    assert _api(base_date=None).resolve_date(None) is None


def test_resolve_date_validates_format() -> None:
    with pytest.raises(ValueError, match="YYYYMMDD"):
        _api().resolve_date("2026-09-14")


def test_plants_cover_both_companies() -> None:
    assert set(common.PLANTS) == set(common.COMPANIES)
    assert len(common.PLANTS["HMC"]) == 28
    assert len(common.PLANTS["KIA"]) == 29


def test_plant_codes_are_four_chars_and_company_prefixed() -> None:
    assert all(len(c) == 4 and c.startswith("1") for c in common.PLANTS["HMC"])
    assert all(len(c) == 4 and c.startswith("2") for c in common.PLANTS["KIA"])


def test_plant_codes_do_not_overlap() -> None:
    assert not set(common.PLANTS["HMC"]) & set(common.PLANTS["KIA"])


def test_succeeded_and_message() -> None:
    ok = {"outData": {"E_IFRESULT": "Z", "E_IFMSG": "SUCCESS", "RECORD_COUNT": "3"}}
    bad = {"outData": {"E_IFRESULT": "E", "E_IFMSG": "nope"}}

    assert common.succeeded(ok)
    assert not common.succeeded(bad)
    assert common.message(bad) == "nope"
    assert common.record_count(ok) == 3
    assert common.record_count(bad) == 0


def test_rows_returns_requested_keys() -> None:
    result = {
        "outData": {
            "E_IFRESULT": "Z",
            "OUTDATA_JSON": json.dumps({"ET_EXPORT1": [{"A": "1"}]}),
        }
    }

    assert common.rows(result, "ET_EXPORT1", "ET_EXPORT2") == {
        "ET_EXPORT1": [{"A": "1"}],
        "ET_EXPORT2": [],
    }


def test_rows_is_empty_when_call_failed() -> None:
    result = {"outData": {"E_IFRESULT": "E", "E_IFMSG": "nope"}}

    assert common.rows(result, "OUT_LIST") == {"OUT_LIST": []}
