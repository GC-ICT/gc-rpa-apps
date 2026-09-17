from __future__ import annotations

BANNER_WIDTH = 46
EMPTY_DETAILS = ("", "Message:", "Message: None", "None")
NO_DETAIL = "상세 메시지가 없습니다"


def describe_error(exc: Exception) -> str:
    text = str(exc).strip()
    detail = text.splitlines()[0].strip() if text else ""
    if detail in EMPTY_DETAILS:
        detail = NO_DETAIL
    return f"{type(exc).__name__}: {detail}"


def print_banner(text: str) -> None:
    line = "=" * BANNER_WIDTH
    print(line)
    print(f"  {text}")
    print(line, flush=True)
