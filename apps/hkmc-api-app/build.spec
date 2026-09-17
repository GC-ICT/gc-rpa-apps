import json
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = [], [], []

settings_file = Path(SPECPATH) / "build-settings.json"
document = json.loads(settings_file.read_text(encoding="utf-8"))
datas += [(str(settings_file), ".")]

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


def indexes_for(name):
    return [
        index
        for index, entry in sorted(document["apis"].items())
        if entry["output"]["include"] and entry["output"].get("fileName") == name
    ]


targets = [(name, str(entry["scheduleId"]), indexes_for(name)) for name, entry in document["builds"].items()]

if not targets:
    raise SystemExit("[build.spec] build-settings.json 에 builds 가 비어 있습니다")

for name, schedule, indexes in targets:
    if not indexes:
        raise SystemExit(f"[build.spec] {name} 에 포함된 API 가 없습니다")
    print(f"[build.spec] {name} (schedule_id={schedule}) API {', '.join(indexes)}")

a = Analysis(
    ["src/hkmc_api_app/__main__.py"],
    pathex=["src", "../../packages/gc-rpa-core/src"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports
    + [
        "hkmc_api_app",
        "hkmc_api_app.build_settings",
        "hkmc_api_app.common",
        "hkmc_api_app.loader",
        "hkmc_api_app.registry",
        "gc_rpa_core",
    ],
    excludes=["tkinter", "pytest", "mypy", "ruff", "IPython"],
    noarchive=False,
)
pyz = PYZ(a.pure)

executables = [
    EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        name=name,
        console=True,
        upx=False,
    )
    for name, _, _ in targets
]
