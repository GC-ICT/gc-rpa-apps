@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
cd /d "%~dp0"

echo ================================
echo   GC RPA 빌드
echo ================================
echo.

where uv >nul 2>nul
if errorlevel 1 (
    echo [오류] uv 가 설치되어 있지 않습니다.
    echo        powershell -c "irm https://astral.sh/uv/install.ps1 ^| iex"
    echo.
    pause
    exit /b 1
)

set count=0
for /d %%D in (apps\*) do (
    if exist "%%D\build.spec" (
        set /a count+=1
        set "app[!count!]=%%~nxD"
        echo   !count!^) %%~nxD
    )
)

if %count%==0 (
    echo [오류] build.spec 이 있는 앱이 없습니다.
    echo.
    pause
    exit /b 1
)

echo.
set /p choice=빌드할 앱 번호 [1-%count%]: 

if not defined app[%choice%] (
    echo [오류] 잘못된 번호입니다: %choice%
    echo.
    pause
    exit /b 1
)

for /f "tokens=*" %%A in ("!app[%choice%]!") do set "target=%%A"

echo.
echo [1/4] 최신 코드 받기
git rev-parse --git-dir >nul 2>nul
if errorlevel 1 (
    echo   git 저장소가 아니므로 건너뜁니다.
) else (
    for /f "delims=" %%S in ('git status --porcelain') do set "dirty=1"
    if defined dirty (
        echo   [경고] 로컬 변경사항이 있어 pull 을 건너뜁니다.
        git status --short
    ) else (
        call git pull --ff-only
        if errorlevel 1 goto failed
    )
)

echo.
echo [2/4] 의존성 설치
call uv sync --all-packages
if errorlevel 1 goto failed

echo.
echo [3/4] 검사
call uv run ruff check .
if errorlevel 1 goto failed
call uv run mypy
if errorlevel 1 goto failed
call uv run pytest -q
if errorlevel 1 goto failed

echo.
echo [4/4] 빌드: %target%
if exist "apps\%target%\dist" rmdir /s /q "apps\%target%\dist"
if exist "apps\%target%\build" rmdir /s /q "apps\%target%\build"
pushd "apps\%target%"
call uv run pyinstaller --clean --noconfirm build.spec
if errorlevel 1 (
    popd
    goto failed
)
popd

echo.
echo ================================
echo   완료
echo ================================
echo   위치: apps\%target%\dist
echo.
dir /b "apps\%target%\dist"
echo.
echo   .env 파일을 exe 와 같은 폴더에 두세요.
echo.
pause
exit /b 0

:failed
echo.
echo ================================
echo   실패
echo ================================
echo.
pause
exit /b 1
