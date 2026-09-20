from datetime import date

import pytest

from gc_rpa_core.statement import UnknownTokenError, bind


def test_bind_turns_a_token_into_a_placeholder() -> None:
    assert bind("EXEC A_PROC @run_dt = {run_dt}", {"run_dt": date(2026, 9, 16)}) == (
        "EXEC A_PROC @run_dt = %s",
        (date(2026, 9, 16),),
    )


def test_bind_repeats_the_value_for_every_mention() -> None:
    statement, params = bind("SELECT {run_dt}, {run_dt}", {"run_dt": date(2026, 9, 16)})

    assert statement == "SELECT %s, %s"
    assert params == (date(2026, 9, 16), date(2026, 9, 16))


def test_bind_keeps_the_order_the_tokens_appear_in() -> None:
    statement, params = bind("{b} {a} {b}", {"a": 1, "b": 2})

    assert statement == "%s %s %s"
    assert params == (2, 1, 2)


def test_bind_leaves_a_statement_without_tokens_alone() -> None:
    assert bind("EXEC A_PROC", {"run_dt": date(2026, 9, 16)}) == ("EXEC A_PROC", ())


def test_bind_complains_about_a_token_it_has_no_value_for() -> None:
    with pytest.raises(UnknownTokenError, match="acpt_dt"):
        bind("EXEC A_PROC @acpt_dt = {acpt_dt}", {"run_dt": date(2026, 9, 16)})
