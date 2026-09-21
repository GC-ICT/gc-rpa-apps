from pathlib import Path

from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = [], [], []

FALLBACK_NAME = "autowayMail"

env_file = Path(SPECPATH) / ".env"
if env_file.is_file():
    datas += [(str(env_file), ".")]
    print(f"[build.spec] .env 를 실행파일에 포함합니다: {env_file}")
else:
    print("[build.spec] .env 가 없어 실행파일에 포함하지 않습니다.")

for package in ("pymssql", "pysignalr", "dotenv", "selenium", "pdf2image"):
    package_datas, package_binaries, package_hidden = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden

def executable_name():
    import os
    import sys

    sys.path.insert(0, str(Path(SPECPATH).parents[1] / "packages" / "gc-rpa-core" / "src"))
    os.chdir(SPECPATH)
    try:
        from gc_rpa_core import config
        from gc_rpa_core.env import optional_env

        settings = config.load(optional_env("AUTOWAY_MAIL_SCHEDULE_ID", "5"))
        name = Path(settings.exe_name).stem
        if not name:
            raise ValueError("file_nm 이 비어 있다")
    except Exception as exc:
        print(f"[build.spec] 프로시저에서 이름을 읽지 못해 {FALLBACK_NAME} 로 빌드합니다: {exc}")
        return FALLBACK_NAME
    print(f"[build.spec] 실행파일 이름을 프로시저에서 읽었습니다: {name}")
    return name


app_name = executable_name()

a = Analysis(
    ["src/autoway_mail/__main__.py"],
    pathex=["src", "../../packages/gc-rpa-core/src", "../../packages/gc-rpa-autoway/src"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports
    + [
        "autoway_mail",
        "autoway_mail.capture",
        "autoway_mail.common",
        "autoway_mail.history",
        "autoway_mail.inbox",
        "autoway_mail.mail",
        "gc_rpa_autoway",
        "gc_rpa_autoway.erp",
        "gc_rpa_autoway.poppler",
        "gc_rpa_autoway.site",
        "gc_rpa_core",
    ],
    excludes=["tkinter", "pytest", "mypy", "ruff", "IPython"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name=app_name,
    console=True,
    upx=False,
)
