import pytest

from inputs import (
    MAX_SCROLL,
    InputController,
    ScreenInfo,
    decode_input_packet,
    load_allowed_keys,
)
from tests.conftest import ROOT


@pytest.fixture
def controller(backend):
    screen = ScreenInfo()
    screen.update(2000, 1000)  # twice the size the backend reports
    return InputController(backend, screen, {"a", "shiftleft"})


def test_coordinates_are_scaled_to_backend_space(controller, backend):
    controller.apply([[0, 1000, 500]])
    assert backend.calls == [("moveTo", (500, 250), {})]


def test_coordinates_are_clamped_to_the_screen(controller, backend):
    controller.apply([[0, -50, 99999]])
    assert backend.calls == [("moveTo", (0, 499), {})]


def test_mouse_buttons(controller, backend):
    controller.apply([[1, 0, 0, 2], [2, 0, 0, 2]])
    assert [c[0] for c in backend.calls] == ["mouseDown", "mouseUp"]
    assert backend.calls[0][2] == {"button": "right"}


def test_unknown_buttons_and_event_types_are_dropped(controller, backend):
    controller.apply([[1, 0, 0, 3], [1, 0, 0, -1], [99], [], "junk", None, [0, "x", "y"]])
    assert backend.calls == []


def test_only_whitelisted_keys_are_pressed(controller, backend):
    controller.apply([[4, "a"], [4, "winleft"], [4, 5], [4, None]])
    assert backend.calls == [("keyDown", ("a",), {})]


def test_scroll_amount_is_limited(controller, backend):
    controller.apply([[3, 10, 10, 10**6], [3, 10, 10, 0]])
    assert backend.calls == [("scroll", (MAX_SCROLL, 5, 5), {})]


def test_nothing_happens_before_the_screen_is_known(backend):
    controller = InputController(backend, ScreenInfo(), {"a"})
    controller.apply([[0, 1, 1], [4, "a"]])
    assert backend.calls == []


def test_release_all_lets_go_of_held_inputs(controller, backend):
    controller.apply([[4, "a"], [4, "shiftleft"], [5, "a"], [1, 0, 0, 0]])
    backend.calls.clear()
    controller.release_all()
    assert sorted(c[0] for c in backend.calls) == ["keyUp", "mouseUp"]

    backend.calls.clear()
    controller.release_all()
    assert backend.calls == []


def test_apply_rejects_non_list_payloads(controller):
    with pytest.raises(ValueError):
        controller.apply({"not": "a list"})


def test_decode_input_packet():
    assert decode_input_packet(b"[[0,1,2]]") == [[0, 1, 2]]
    assert decode_input_packet(b"not json") is None
    assert decode_input_packet("ü".encode()) is None


def test_every_key_in_keys_json_is_a_real_pyautogui_key():
    try:
        import pyautogui
    except Exception as e:  # no display on headless machines
        pytest.skip(f"pyautogui is unavailable: {e}")
    keys = load_allowed_keys(ROOT / "src" / "keys.json")
    assert keys - set(pyautogui.KEYBOARD_KEYS) == set()
