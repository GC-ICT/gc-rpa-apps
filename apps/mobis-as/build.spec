from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = [], [], []
for package in ("selenium", "pymssql", "pysignalr", "dotenv"):
    package_datas, package_binaries, package_hidden = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden

a = Analysis(
    ["src/mobis_as/__main__.py"],
    pathex=["src", "../../packages/gc-rpa-core/src"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports + ["mobis_as", "mobis_as.common", "mobis_as.pu010", "gc_rpa_core"],
    excludes=["tkinter", "pytest", "mypy", "ruff", "IPython"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name="mobisAS",
    console=True,
    upx=False,
)
