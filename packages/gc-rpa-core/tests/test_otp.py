from typing import Any

import pytest

from gc_rpa_core import otp


class FakeSwitch:
    def __init__(self) -> None:
        self.frames: list[str] = []
        self.alert = None

    def default_content(self) -> None:
        self.frames.append("top")

    def frame(self, name: str) -> None:
        self.frames.append(name)


class FakeMail:
    def __init__(self) -> None:
        self.clicked = False

    def click(self) -> None:
        self.clicked = True


class FakeBody:
    def __init__(self, text: str) -> None:
        self.text = text


class FakeDriver:
    def __init__(self, counts: list[int], body: str = "", url: str = "") -> None:
        self.counts = counts
        self.body = body
        self.current_url = url
        self.switch_to = FakeSwitch()
        self.mails: list[FakeMail] = []

    def find_elements(self, by: str, locator: str) -> list[FakeMail]:
        count = self.counts.pop(0) if len(self.counts) > 1 else self.counts[0]
        self.mails = [FakeMail() for _ in range(count)]
        return self.mails

    def find_element(self, by: str, locator: str) -> FakeBody:
        return FakeBody(self.body)


@pytest.fixture
def quiet(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(otp, "click", lambda *_a, **_k: None)
    monkeypatch.setattr(otp, "fill", lambda *_a, **_k: None)
    monkeypatch.setattr(otp, "wait_ready", lambda *_a, **_k: None)
    monkeypatch.setattr(otp.time, "sleep", lambda _s: None)


@pytest.mark.parametrize(
    ("current", "expected"),
    [("gumchang01", "gumchang02"), ("pw9", "pw10"), ("pw099", "pw100"), ("a1b2", "a2b2")],
)
def test_the_next_password_raises_the_first_number(current: str, expected: str) -> None:
    assert otp.bumped(current) == expected


def test_a_password_without_a_number_cannot_be_raised() -> None:
    with pytest.raises(otp.OtpError, match="숫자가 없어"):
        otp.bumped("gumchang")


def test_the_vpn_mail_gives_up_its_code() -> None:
    assert otp.VPN.code.search("OTP : [ 483920 ]").group(1) == "483920"


def test_the_portal_mail_gives_up_its_code() -> None:
    body = "[현대제철 고객포탈]인증번호는 123456 입니다."
    assert otp.PORTAL.code.search(body).group(1) == "123456"


def test_a_profile_is_found_by_its_subject_text() -> None:
    assert otp.VPN.subject in otp.VPN.locator
    assert "MailListItem" not in otp.VPN.locator


def test_the_password_change_page_is_recognised() -> None:
    changing = FakeDriver([0], url="https://login.office.hiworks.com/password-change?x=1")
    normal = FakeDriver([0], url="https://mail.hiworks.com/main")

    assert otp.on_change_page(changing) is True
    assert otp.on_change_page(normal) is False


def test_the_mail_main_page_counts_as_signed_in() -> None:
    assert otp.signed_in_already(FakeDriver([0], url="https://mail.hiworks.com/webmail/main/"))
    assert not otp.signed_in_already(FakeDriver([0], url="https://mail.hiworks.com/login"))


def test_a_mail_that_was_already_there_is_not_taken(quiet: None) -> None:
    driver = FakeDriver([1], body="OTP : [ 111111 ]")
    box = otp.Mailbox(driver=driver, profile=otp.VPN)

    with pytest.raises(otp.OtpError, match="오지 않았습니다"):
        box.read(seen=1, timeout=0)


def test_a_mail_that_arrives_late_is_still_read(quiet: None) -> None:
    driver = FakeDriver([0, 0, 1], body="OTP : [ 483920 ]")
    box = otp.Mailbox(driver=driver, profile=otp.VPN)

    assert box.read(seen=0) == "483920"


def test_the_body_is_read_inside_the_view_frame(quiet: None) -> None:
    driver = FakeDriver([1], body="OTP : [ 483920 ]")

    otp.Mailbox(driver=driver, profile=otp.VPN).newest()

    assert otp.MAIL_BODY_FRAME in driver.switch_to.frames


def test_a_body_without_a_number_is_an_error(quiet: None) -> None:
    driver = FakeDriver([1], body="안녕하세요")

    with pytest.raises(otp.OtpError, match="번호를 찾지 못했습니다"):
        otp.Mailbox(driver=driver, profile=otp.VPN).newest()


def test_no_matching_mail_is_an_error(quiet: None) -> None:
    driver = FakeDriver([0])

    with pytest.raises(otp.OtpError, match="찾지 못했습니다"):
        otp.Mailbox(driver=driver, profile=otp.VPN).newest()


def test_the_password_procedure_is_called_with_the_new_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from gc_rpa_core import config

    sent: list[Any] = []

    class FakeCursor:
        def execute(self, statement: str, params: Any) -> None:
            sent.append((statement, params))

    from contextlib import contextmanager

    @contextmanager
    def fake(*_a: Any, **_k: Any) -> Any:
        yield FakeCursor()

    monkeypatch.setattr(config, "cursor", fake)

    config.save_password("17", "gumchang02")

    statement, params = sent[0]
    assert "@_rpa_pw" in statement
    assert params == (config.PASSWORD_SELECT_TYPE, "17", "gumchang02")
