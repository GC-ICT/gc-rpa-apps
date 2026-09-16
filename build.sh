#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

echo "================================"
echo "  GC RPA 빌드"
echo "================================"
echo

command -v uv >/dev/null || {
    echo "[오류] uv 가 설치되어 있지 않습니다."
    echo "       curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
}

mapfile -t apps < <(find apps -mindepth 2 -maxdepth 2 -name build.spec -printf '%h\n' | xargs -rn1 basename | sort)

if [ ${#apps[@]} -eq 0 ]; then
    echo "[오류] build.spec 이 있는 앱이 없습니다."
    exit 1
fi

for i in "${!apps[@]}"; do
    echo "  $((i + 1))) ${apps[i]}"
done

echo
read -rp "빌드할 앱 번호 [1-${#apps[@]}]: " choice

if ! [[ "$choice" =~ ^[0-9]+$ ]] || [ "$choice" -lt 1 ] || [ "$choice" -gt ${#apps[@]} ]; then
    echo "[오류] 잘못된 번호입니다: $choice"
    exit 1
fi

target="${apps[$((choice - 1))]}"

echo
echo "[1/4] 최신 코드 받기"
if git rev-parse --git-dir >/dev/null 2>&1; then
    if [ -n "$(git status --porcelain)" ]; then
        echo "  [경고] 로컬 변경사항이 있어 pull 을 건너뜁니다."
        git status --short
    else
        git pull --ff-only
    fi
else
    echo "  git 저장소가 아니라 건너뜁니다."
fi

echo
echo "[2/4] 의존성 설치"
uv sync --all-packages

echo
echo "[3/4] 검사"
uv run ruff check .
uv run mypy
uv run pytest -q

echo
echo "[4/4] 빌드: $target"
(cd "apps/$target" && uv run pyinstaller --clean --noconfirm build.spec)

echo
echo "================================"
echo "  완료"
echo "================================"
echo "  위치: apps/$target/dist"
ls -lh "apps/$target/dist"
echo
echo "  .env 파일을 실행파일과 같은 폴더에 두세요."
