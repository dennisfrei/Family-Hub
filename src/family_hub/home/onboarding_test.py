import pytest

from family_hub.home.onboarding import SetupState, StepKey, is_complete, setup_steps

EMPTY = SetupState(adults=0, children=0, duties_with_rules=0, reference_files=0, backup_bucket=False)


def test_empty_install_needs_everything() -> None:
    steps = setup_steps(EMPTY)

    assert [step.key for step in steps if not step.done] == list(StepKey)
    assert not is_complete(steps)


@pytest.mark.parametrize(
    ("adults", "children", "duties", "complete"),
    [(1, 1, 1, True), (1, 1, 0, False), (0, 2, 1, False), (2, 0, 1, False)],
)
def test_optional_steps_do_not_block(adults: int, children: int, duties: int, complete: bool) -> None:
    state = SetupState(
        adults=adults, children=children, duties_with_rules=duties, reference_files=0, backup_bucket=False
    )

    assert is_complete(setup_steps(state)) is complete
