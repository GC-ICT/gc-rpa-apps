from pathlib import Path

from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = [], [], []

FALLBACK_NAME = "hkmc_api"

env_file = Path(SPECPATH) / ".env"
if env_file.is_file():
    datas += [(str(env_file), ".")]
    print(f"[build.spec] .env 를 실행파일에 포함합니다: {env_file}")
else:
    print("[build.spec] .env 가 없어 실행파일에 포함하지 않습니다.")

for package in ("httpx", "pymssql", "pysignalr", "dotenv"):
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

        settings = config.load(optional_env("HKMC_SCHEDULE_ID", "4"))
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
    ["src/hkmc_api_app/__main__.py"],
    pathex=["src", "../../packages/gc-rpa-core/src"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports + ["hkmc_api_app", "hkmc_api_app.common", "hkmc_api_app.loader", "hkmc_api_app.registry", "gc_rpa_core"],
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
