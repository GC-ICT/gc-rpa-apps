from pathlib import Path

import pytest

from mobis_as import common


def test_download_dir_uses_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "nested" / "downloads"
    monkeypatch.setenv(common.DOWNLOAD_DIR_ENV, str(target))

    assert common.download_dir() == target.resolve()
    assert target.is_dir()


def test_download_dir_defaults_to_downloads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(common.DOWNLOAD_DIR_ENV, raising=False)

    assert common.download_dir() == (tmp_path / "downloads").resolve()


def test_login_locators_target_the_otp_form() -> None:
    assert common.USER_ID_INPUT.endswith("edtUsrId:input")
    assert common.PASSWORD_INPUT.endswith("edtPwd:input")
    assert common.OTP_INPUT.endswith("edtOtpKey:input")
    assert common.LOGIN_BUTTON.endswith("btnOtpLogin")
    assert common.LOGIN_BOX.startswith("mainframe.VFrameSet.LoginFrame")
