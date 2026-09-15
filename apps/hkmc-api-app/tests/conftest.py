from collections.abc import Callable, Iterator

import httpx
import pytest

from hkmc_api_app import common

BASE_URL = "https://api.example.invalid"
VENDOR = "V123"
TOKEN = "tok-1"

Handler = Callable[[httpx.Request], httpx.Response]


@pytest.fixture(autouse=True)
def env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_BASE_URL", BASE_URL)
    monkeypatch.setenv("HMC_CLIENT_ID", "id")
    monkeypatch.setenv("HMC_CLIENT_SECRET", "secret")
    monkeypatch.setenv("KIA_CLIENT_ID", "kid")
    monkeypatch.setenv("KIA_CLIENT_SECRET", "ksecret")
    monkeypatch.setenv("VENDOR_CODE", VENDOR)


@pytest.fixture
def mock_client() -> Callable[[Handler], httpx.Client]:
    def factory(handler: Handler) -> httpx.Client:
        return common.build_client(transport=httpx.MockTransport(handler))

    return factory


@pytest.fixture
def patch_build_client(monkeypatch: pytest.MonkeyPatch) -> Callable[[Handler], None]:
    real_build_client = common.build_client

    def patch(handler: Handler) -> None:
        monkeypatch.setattr(
            common,
            "build_client",
            lambda: real_build_client(transport=httpx.MockTransport(handler)),
        )

    return patch


@pytest.fixture
def sent() -> dict[str, str]:
    return {}


@pytest.fixture
def capture_session(
    patch_build_client: Callable[[Handler], None], sent: dict[str, str]
) -> Iterator[dict[str, str]]:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == common.TOKEN_PATH:
            return httpx.Response(200, json={"accToken": TOKEN})
        sent["path"] = request.url.path
        sent["token"] = request.headers["AccToken"]
        sent["body"] = request.content.decode()
        return httpx.Response(200, json={"outData": {"E_IFRESULT": "Z"}})

    patch_build_client(handler)
    yield sent
