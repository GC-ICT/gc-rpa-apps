from __future__ import annotations

import re

NAME_LIMIT = 60
FALLBACK = "본문"
UNSAFE = re.compile(r'[\\/:*?"<>|]')


def safe_name(value: str) -> str:
    return UNSAFE.sub("_", value or "").strip()[:NAME_LIMIT]


def pdf_name(title: str) -> str:
    cleaned = safe_name(title).rstrip(". ")
    return f"{cleaned or FALLBACK}.pdf"
