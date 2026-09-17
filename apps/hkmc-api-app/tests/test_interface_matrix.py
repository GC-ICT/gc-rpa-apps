import pytest

from hkmc_api_app import registry

NORMAL = "O"
EMPTY = "X"
NONE = "-"
WRITE = "W"

MATRIX = {
    "001": (NORMAL, NORMAL),
    "002": (NORMAL, NORMAL),
    "003": (NORMAL, EMPTY),
    "004": (NORMAL, NORMAL),
    "005": (EMPTY, NORMAL),
    "006": (EMPTY, EMPTY),
    "007": (NONE, NORMAL),
    "008": (NORMAL, NORMAL),
    "009": (WRITE, WRITE),
    "010": (WRITE, WRITE),
    "011": (WRITE, WRITE),
    "012": (NORMAL, NORMAL),
    "013": (NORMAL, NORMAL),
    "014": (NORMAL, NORMAL),
    "015": (NORMAL, EMPTY),
    "016": (EMPTY, NONE),
}

CASES = [
    (index, company, state)
    for index, states in MATRIX.items()
    for company, state in zip(("HMC", "KIA"), states, strict=True)
]


def test_matrix_covers_every_api() -> None:
    assert set(MATRIX) == set(registry.BY_INDEX)


@pytest.mark.parametrize(("index", "company", "state"), CASES)
def test_matrix_matches_the_registry(index: str, company: str, state: str) -> None:
    api = registry.BY_INDEX[index]

    if state == WRITE:
        assert api.writes
        return

    assert not api.writes
    assert api.supports(company) is (state != NONE)
    assert registry.expected_empty(api, company) is (state == EMPTY)


def test_expected_empty_names_only_readable_apis() -> None:
    for index in registry.EXPECTED_EMPTY:
        assert not registry.BY_INDEX[index].writes


def test_ordered_keeps_index_order_and_drops_write_apis() -> None:
    chosen = registry.ordered(("016", "009", "001"))

    assert [api.index for api in chosen] == ["001", "016"]


def test_ordered_ignores_unknown_indexes() -> None:
    assert registry.ordered(("999",)) == ()
