import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def load_web_rdp():
    """web-rdp.py has a dash in its name, so it can not be imported normally."""
    spec = importlib.util.spec_from_file_location("web_rdp", ROOT / "web-rdp.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeBackend:
    """Stands in for pyautogui and records every call."""

    def __init__(self, size=(1000, 500)):
        self._size = size
        self.calls = []

    def size(self):
        return self._size

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)

        def record(*args, **kwargs):
            self.calls.append((name, args, kwargs))

        return record


@pytest.fixture
def backend():
    return FakeBackend()


@pytest.fixture
def web_rdp():
    return load_web_rdp()
