from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date as date_cls
from datetime import datetime, timedelta
from typing import Any

import httpx

BASE_URL_ENV = "API_BASE_URL"
VENDOR_ENV = "VENDOR_CODE"

COMPANIES = ("HMC", "KIA")
TOKEN_PATH = "/oauth/token"
RECEIVE_PATH = {
    "HMC": "/HGERPVENDOR/apiGERPAPIGW/GERPVENDOR/Receive",
    "KIA": "/KGERPVENDOR/apiGERPAPIGW/GERPVENDOR/Receive",
}
SYSTEM = {"HMC": "MMH", "KIA": "MMK"}
TARGET_SYSTEM = "ERPMM"
DEFAULT_TIMEOUT = 30.0
SUCCESS_RESULT = "Z"

PLANTS = {
    "HMC": {
        "1000": "HMC 본사",
        "1011": "HMC 울산 완성차 1공장",
        "1012": "HMC 울산 완성차 2공장",
        "1013": "HMC 울산 완성차 3공장",
        "1014": "HMC 울산 완성차 4공장",
        "1015": "HMC 울산 완성차 5공장",
        "101A": "HMC 울산 EV 공장",
        "1019": "HMC 울산 TSD 공장",
        "1021": "HMC 아산 완성차 공장",
        "1031": "HMC 전주 완성차 공장",
        "1041": "GGM 광주 완성차 공장",
        "1070": "HMC 울산 엔진 공장",
        "1071": "HMC 아산 엔진 공장",
        "1072": "HMC 전주 엔진 공장",
        "1073": "HMC 울산 변속기 공장",
        "1074": "HMC 울산 소재 공장",
        "1075": "HMC 아산 소재 공장",
        "1076": "HMC 전주 소재 공장",
        "1077": "HMC 울산 시트 1/2공장",
        "1078": "HMC 울산 시트 3공장",
        "1079": "HMC 충주 수소연료전지 공장",
        "1081": "HMC 울산 KD 포장공장",
        "1082": "HMC 아산 KD 포장공장",
        "1083": "HMC 전주 KD 포장공장",
        "1091": "HMC 울산 제품2 공장",
        "1092": "HMC 울산 공통 공장",
        "1093": "HMC 아산 공통 공장",
        "1094": "HMC 전주 공통 공장",
    },
    "KIA": {
        "2900": "Kia 공통",
        "2911": "Kia 광명 완성차 1공장",
        "2912": "Kia 광명 EVO Plant",
        "2921": "Kia 화성 완성차 1공장",
        "2922": "Kia 화성 완성차 2공장",
        "2923": "Kia 화성 완성차 3공장",
        "2924": "Kia 화성 EVO East Plant",
        "2925": "Kia 화성 EVO West Plant",
        "2931": "Kia 광주 완성차 1공장",
        "2932": "Kia 광주 완성차 2공장",
        "2933": "Kia 광주 완성차 3공장",
        "2934": "Kia 광주 완성차 버스 공장",
        "2935": "Kia 광주 완성차 군수 공장",
        "2941": "DH 서산 완성차 공장",
        "2971": "Kia 광명 엔진 공장",
        "2972": "Kia 화성 엔진 공장",
        "2973": "Kia 화성 변속기 공장",
        "2974": "Kia 화성 소재 공장",
        "2975": "Kia 광주 소재 공장",
        "2981": "Kia 화성 KD 포장공장",
        "2982": "Kia 광주 KD 포장공장",
        "2983": "Kia 광주 KD 상용 포장공장",
        "2984": "Kia 광주 KD 버스 포장공장",
        "2985": "Kia 화성 KD 특수 포장공장",
        "2991": "Kia 광명 공통 공장",
        "2992": "Kia 화성 공통 공장",
        "2993": "Kia 광주 공통 공장",
        "2994": "DH 서산 공통 공장",
        "2995": "Kia 광명 제품2 공장",
    },
}

ENVELOPE_KEYS = (
    "COMPANY",
    "SENDER",
    "RECORD_COUNT",
    "IFID",
    "SERVICE_CODE",
    "DOCUMENTTYPE",
    "TARGET_SYSTEM",
    "INDATA_JSON",
)


class MissingConfigError(RuntimeError):
    pass


class TokenError(RuntimeError):
    pass


class InterfaceError(RuntimeError):
    pass


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise MissingConfigError(f"환경변수 {name} 가 설정되지 않았습니다")
    return value


def vendor() -> str:
    return require_env(VENDOR_ENV)


def service_code(company: str, vendor: str, ifid: str) -> str:
    return f"{vendor}-{SYSTEM[company]}-B-{ifid[4:]}0"


def today() -> str:
    return date_cls.today().strftime("%Y%m%d")


def yesterday() -> str:
    return (date_cls.today() - timedelta(days=1)).strftime("%Y%m%d")


def parse_date(value: str) -> str:
    try:
        datetime.strptime(value, "%Y%m%d")
    except ValueError as exc:
        raise ValueError(f"날짜는 YYYYMMDD 형식이어야 합니다: {value!r}") from exc
    return value


def build_client(
    *,
    timeout: float = DEFAULT_TIMEOUT,
    transport: httpx.BaseTransport | None = None,
) -> httpx.Client:
    return httpx.Client(
        base_url=require_env(BASE_URL_ENV),
        headers={"Accept": "application/json"},
        timeout=timeout,
        transport=transport,
    )


def issue_token(client: httpx.Client, company: str) -> str:
    response = client.post(
        TOKEN_PATH,
        data={"grant_type": "client_credentials"},
        auth=httpx.BasicAuth(
            require_env(f"{company}_CLIENT_ID"),
            require_env(f"{company}_CLIENT_SECRET"),
        ),
    )
    response.raise_for_status()

    data: Any = response.json()
    token = data.get("accToken") if isinstance(data, dict) else None
    if not token:
        raise TokenError(f"토큰 응답에 accToken이 없습니다: {data}")

    return str(token)


def envelope(
    *,
    company: str,
    vendor: str,
    ifid: str,
    document_type: str,
    indata: dict[str, Any],
) -> dict[str, str]:
    return {
        "COMPANY": company,
        "SENDER": vendor,
        "RECORD_COUNT": "1",
        "IFID": ifid,
        "SERVICE_CODE": service_code(company, vendor, ifid),
        "DOCUMENTTYPE": document_type,
        "TARGET_SYSTEM": TARGET_SYSTEM,
        "INDATA_JSON": json.dumps(indata, ensure_ascii=False, separators=(",", ":")),
    }


def request(client: httpx.Client, token: str, payload: dict[str, str]) -> Any:
    response = client.post(
        RECEIVE_PATH[payload["COMPANY"]],
        json=payload,
        headers={"AccToken": token},
    )
    response.raise_for_status()
    return response.json()


def outdata(result: Any) -> dict[str, Any]:
    parsed: dict[str, Any] = json.loads(result["outData"]["OUTDATA_JSON"])
    return parsed


def succeeded(result: Any) -> bool:
    return bool(result["outData"]["E_IFRESULT"] == SUCCESS_RESULT)


def message(result: Any) -> str:
    return str(result["outData"]["E_IFMSG"])


def record_count(result: Any) -> int:
    return int(result["outData"].get("RECORD_COUNT") or 0)


def rows(result: Any, *keys: str) -> dict[str, list[dict[str, Any]]]:
    if not succeeded(result):
        return {key: [] for key in keys}
    parsed = outdata(result)
    return {key: parsed.get(key) or [] for key in keys}


@dataclass
class Session:
    client: httpx.Client
    token: str
    company: str
    vendor: str

    def call(self, payload: dict[str, str]) -> Any:
        return request(self.client, self.token, payload)


def open_session(client: httpx.Client, company: str) -> Session:
    return Session(
        client=client,
        token=issue_token(client, company),
        company=company,
        vendor=vendor(),
    )


@contextmanager
def session(company: str = "HMC") -> Iterator[Session]:
    with build_client() as client:
        yield open_session(client, company)


@dataclass(frozen=True)
class Api:
    index: str
    name: str
    ifid: str
    document_type: str
    indata: Callable[..., dict[str, Any]]
    base_date: Callable[[], str] | None = field(default=today)
    date_fixed: bool = False
    companies: tuple[str, ...] = COMPANIES
    out_keys: tuple[str, ...] = ("OUT_LIST",)

    @property
    def writes(self) -> bool:
        return "_R_API_" in self.document_type

    def supports(self, company: str) -> bool:
        return company in self.companies

    def check_company(self, company: str) -> None:
        if not self.supports(company):
            raise ValueError(f"{self.index} {self.name} 는 {company} 에 인터페이스가 없습니다")

    def check_date(self, date: str | None) -> None:
        if date is None:
            return
        if self.base_date is None:
            raise ValueError(f"{self.index} {self.name} 는 날짜를 쓰지 않습니다")
        if self.date_fixed:
            raise ValueError(f"{self.index} {self.name} 는 날짜를 지정할 수 없습니다")

    def resolve_date(self, date: str | None) -> str | None:
        if date is not None:
            return parse_date(date)
        return self.base_date() if self.base_date else None

    def payload(
        self, *, company: str, vendor: str, date: str | None = None, **params: Any
    ) -> dict[str, str]:
        resolved = self.resolve_date(date)
        dated = {} if resolved is None else {"date": resolved}
        return envelope(
            company=company,
            vendor=vendor,
            ifid=self.ifid,
            document_type=self.document_type,
            indata=self.indata(vendor=vendor, **dated, **params),
        )

    def fetch(self, session: Session, *, date: str | None = None, **params: Any) -> Any:
        self.check_company(session.company)
        self.check_date(date)
        return session.call(
            self.payload(company=session.company, vendor=session.vendor, date=date, **params)
        )

    def run(self, *, company: str = "HMC", date: str | None = None, **params: Any) -> Any:
        self.check_company(company)
        with session(company) as opened:
            return self.fetch(opened, date=date, **params)

    def sweep(
        self, session: Session, *, plants: Iterable[str] | None = None, **params: Any
    ) -> dict[str, Any]:
        codes = PLANTS[session.company] if plants is None else plants
        return {werks: self.fetch(session, werks=werks, **params) for werks in codes}

    def collect(self, result: Any) -> dict[str, list[dict[str, Any]]]:
        return rows(result, *self.out_keys)

    def collect_all(self, results: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
        merged: dict[str, list[dict[str, Any]]] = {key: [] for key in self.out_keys}
        for result in results.values():
            for key, value in self.collect(result).items():
                merged[key].extend(value)
        return merged
