import pytest

from backend.app.hardware.power_button import PowerButton


def sample(button, pressed, time):
    button.update(pressed, time)
    return button.update(pressed, time + 0.06)


@pytest.mark.parametrize(
    "duration,action",
    [(0.1, None), (1.99, None), (2, "reboot"), (4.99, "reboot"), (5, "poweroff"), (20, "poweroff")],
)
def test_action_only_occurs_after_release(duration, action):
    button = PowerButton()
    sample(button, False, 0)
    sample(button, True, 1)
    assert button.update(True, 1 + duration) is None
    assert sample(button, False, 1 + duration) == action
    assert button.update(False, 100) is None


def test_startup_hold_never_triggers_action():
    button = PowerButton()
    sample(button, True, 0)
    assert sample(button, False, 30) is None
    sample(button, True, 31)
    assert sample(button, False, 36) == "poweroff"


def test_long_hold_does_not_reboot_when_crossing_two_seconds():
    button = PowerButton()
    sample(button, False, 0)
    sample(button, True, 1)
    for time in [3, 4, 5, 6, 7]:
        assert button.update(True, time) is None
    assert button.feedback(7)["action"] == "poweroff"
    assert sample(button, False, 7) == "poweroff"


def test_switch_bounce_does_not_release_or_trigger_twice():
    button = PowerButton()
    sample(button, False, 0)
    sample(button, True, 1)
    assert button.update(False, 3) is None
    assert button.update(True, 3.02) is None
    assert button.update(True, 3.08) is None
    assert sample(button, False, 7) == "poweroff"
    assert button.update(True, 7.07) is None
    assert button.update(False, 7.08) is None
    assert button.update(False, 7.2) is None
