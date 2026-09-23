from gc_rpa_autoway import naming


def test_safe_name_replaces_path_characters() -> None:
    assert naming.safe_name("보낸이/이름:주소") == "보낸이_이름_주소"


def test_safe_name_is_capped() -> None:
    assert len(naming.safe_name("가" * 200)) == naming.NAME_LIMIT


def test_pdf_name_uses_the_title() -> None:
    assert naming.pdf_name("9월 정산 통보 件") == "9월 정산 통보 件.pdf"


def test_pdf_name_strips_path_characters() -> None:
    assert naming.pdf_name("가/나:다") == "가_나_다.pdf"


def test_pdf_name_falls_back_when_the_title_is_empty() -> None:
    assert naming.pdf_name("   ") == f"{naming.FALLBACK}.pdf"


def test_pdf_name_does_not_end_with_a_dot() -> None:
    assert naming.pdf_name("제목...") == "제목.pdf"
