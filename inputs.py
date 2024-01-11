"""Validates input events from the browser and replays them on this computer."""

import json
import logging
import sys
from pathlib import Path
from typing import Iterable, Optional, Sequence

log = logging.getLogger(__name__)

EVENT_MOUSE_MOVE = 0
EVENT_MOUSE_DOWN = 1
EVENT_MOUSE_UP = 2
EVENT_MOUSE_SCROLL = 3
EVENT_KEY_DOWN = 4
EVENT_KEY_UP = 5

BUTTONS = ("left", "middle", "right")

# Largest scroll amount accepted in a single event
MAX_SCROLL = 1200

# Upper bound of events accepted in a single packet
MAX_EVENTS_PER_PACKET = 512


def load_allowed_keys(path: Path) -> frozenset:
    """Key names pyautogui may press: the values of keys.json."""
    with open(path, "r", encoding="utf-8") as f:
        return frozenset(json.load(f).values())


def enable_dpi_awareness():
    """Make Windows report real pixels, so capture and input agree on scaled displays."""
    if sys.platform != "win32":
        return
    import ctypes

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per monitor
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            log.warning("could not enable DPI awareness")


def create_backend():
    """Return the pyautogui module configured for low latency remote control."""
    import pyautogui

    pyautogui.FAILSAFE = False  # the pointer is allowed to touch screen corners
    pyautogui.PAUSE = 0  # the default 0.1s pause after every call made input laggy
    pyautogui.MINIMUM_DURATION = 0
    return pyautogui


class ScreenInfo:
    """Size of the captured screen, written by the stream socket."""

    def __init__(self):
        self.width = 0
        self.height = 0

    def update(self, width: int, height: int):
        self.width, self.height = width, height

    @property
    def known(self) -> bool:
        return self.width > 0 and self.height > 0


class InputController:
    """Applies input events and remembers what is held down."""

    def __init__(self, backend, screen: ScreenInfo, allowed_keys: Iterable[str]):
        self.backend = backend
        self.screen = screen
        self.allowed_keys = frozenset(allowed_keys)
        self.pressed_keys = set()
        self.pressed_buttons = set()

    def _to_screen(self, x, y):
        """Map capture pixels to the coordinate space of the input backend.

        They differ on scaled displays (retina, Windows DPI scaling).
        """
        width, height = self.backend.size()
        x = max(0, min(self.screen.width - 1, int(x)))
        y = max(0, min(self.screen.height - 1, int(y)))
        x = round(x * width / self.screen.width)
        y = round(y * height / self.screen.height)
        return max(0, min(width - 1, x)), max(0, min(height - 1, y))

    def apply(self, events: Sequence):
        if not isinstance(events, list):
            raise ValueError("events must be a list")
        if not self.screen.known:
            return  # nothing was streamed yet, coordinates would be meaningless

        for event in events[:MAX_EVENTS_PER_PACKET]:
            try:
                self._apply_one(event)
            except (TypeError, ValueError, IndexError, KeyError) as e:
                log.debug("dropped invalid input event %r: %s", event, e)

    def _apply_one(self, event):
        kind = event[0]

        if kind == EVENT_MOUSE_MOVE:
            x, y = self._to_screen(event[1], event[2])
            self.backend.moveTo(x, y)
        elif kind in (EVENT_MOUSE_DOWN, EVENT_MOUSE_UP):
            x, y = self._to_screen(event[1], event[2])
            button = BUTTONS[self._button_index(event[3])]
            if kind == EVENT_MOUSE_DOWN:
                self.backend.mouseDown(x, y, button=button)
                self.pressed_buttons.add(button)
            else:
                self.backend.mouseUp(x, y, button=button)
                self.pressed_buttons.discard(button)
        elif kind == EVENT_MOUSE_SCROLL:
            x, y = self._to_screen(event[1], event[2])
            amount = max(-MAX_SCROLL, min(MAX_SCROLL, int(event[3])))
            if amount:
                self.backend.scroll(amount, x, y)
        elif kind == EVENT_KEY_DOWN:
            key = self._key(event[1])
            self.backend.keyDown(key)
            self.pressed_keys.add(key)
        elif kind == EVENT_KEY_UP:
            key = self._key(event[1])
            self.backend.keyUp(key)
            self.pressed_keys.discard(key)
        else:
            raise ValueError(f"unknown event type {kind!r}")

    @staticmethod
    def _button_index(value) -> int:
        index = int(value)
        if not 0 <= index < len(BUTTONS):
            raise ValueError(f"unsupported mouse button {index}")
        return index

    def _key(self, value) -> str:
        if not isinstance(value, str) or value not in self.allowed_keys:
            raise ValueError(f"unsupported key {value!r}")
        return value

    def release_all(self):
        """Let go of everything still held, used when the client goes away."""
        for key in list(self.pressed_keys):
            try:
                self.backend.keyUp(key)
            except Exception:
                log.exception("failed to release key %s", key)
        for button in list(self.pressed_buttons):
            try:
                self.backend.mouseUp(button=button)
            except Exception:
                log.exception("failed to release mouse button %s", button)
        self.pressed_keys.clear()
        self.pressed_buttons.clear()


def decode_input_packet(payload: bytes) -> Optional[list]:
    """Decode the JSON event list of an input packet, None when malformed."""
    try:
        return json.loads(payload.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
