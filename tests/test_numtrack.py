import tempfile
import contextlib
import io
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from numtrack.config import load_config
from numtrack.core import Controller
from numtrack.backend import Keyboard, resolve_bindings
from numtrack.cli import main


class FakePointer:
    def __init__(self):
        self.buttons = []
        self.moves = []

    def button(self, name, pressed):
        self.buttons.append((name, pressed))

    def move(self, horizontal, vertical):
        self.moves.append((horizontal, vertical))


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.pointer = FakePointer()
        self.config = load_config()
        self.controller = Controller(self.config, self.pointer)

    def press(self, key, action, value=1, source="keyboard"):
        self.controller.key((source, key), action, value)

    def test_default_bindings(self):
        self.assertEqual(self.config["bindings"], {
            "KEY_KP8": "up", "KEY_KP4": "left", "KEY_KP6": "right", "KEY_KP2": "down",
            "KEY_KP7": "left_click", "KEY_KP5": "left_click", "KEY_KP9": "right_click",
            "KEY_KP3": "middle_click", "KEY_KP1": "left_hold",
        })

    def test_disabled_until_toggle_and_movement_directions(self):
        self.press(8, "up")
        self.controller.tick(0.02)
        self.assertEqual(self.pointer.moves, [])
        self.controller.toggle()
        for key, action, expected in [(8, "up", (0, -7)), (4, "left", (-7, 0)),
                                      (6, "right", (7, 0)), (2, "down", (0, 7))]:
            self.press(key, action)
            self.controller.tick(0.02)
            self.assertEqual(self.pointer.moves[-1], expected)
            self.controller.clear()

    def test_clicks_once_per_press(self):
        self.controller.toggle()
        for key, action, button in [(7, "left_click", "left"), (5, "left_click", "left"),
                                     (9, "right_click", "right"), (3, "middle_click", "middle")]:
            start = len(self.pointer.buttons)
            self.press(key, action)
            self.press(key, action, 2)
            self.press(key, action, 0)
            self.assertEqual(self.pointer.buttons[start:], [(button, True), (button, False)])

    def test_hold_drag_toggle_release(self):
        self.controller.toggle()
        self.press(1, "left_hold")
        self.press(6, "right")
        self.controller.tick(0.02)
        self.assertEqual(self.pointer.buttons, [("left", True)])
        self.assertTrue(self.pointer.moves)
        self.press(5, "left_click")
        self.assertEqual(self.pointer.buttons, [("left", True)])
        self.controller.toggle()
        self.assertEqual(self.pointer.buttons[-1], ("left", False))
        self.assertEqual(self.controller.pressed, {})

    def test_multiple_keyboards_hold_and_disconnect(self):
        self.controller.toggle()
        self.press(1, "left_hold", source="first")
        self.press(1, "left_hold", source="second")
        self.controller.clear("first")
        self.assertEqual(self.pointer.buttons, [("left", True)])
        self.controller.clear("second")
        self.assertEqual(self.pointer.buttons, [("left", True), ("left", False)])

    def test_normalized_diagonal_and_acceleration_cap(self):
        self.controller.toggle()
        self.press(8, "up")
        self.press(6, "right")
        self.controller.tick(0.02)
        horizontal, vertical = self.pointer.moves[-1]
        self.assertEqual(horizontal, -vertical)
        self.assertLessEqual((horizontal ** 2 + vertical ** 2) ** 0.5, 7)
        for step in range(300):
            self.controller.tick(0.01)
        self.assertLessEqual(max(abs(axis) for move in self.pointer.moves for axis in move), 11)
        self.press(4, "left")
        self.press(2, "down")
        count = len(self.pointer.moves)
        self.controller.tick(0.02)
        self.assertEqual(len(self.pointer.moves), count)


class ConfigTests(unittest.TestCase):
    def load(self, contents):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.toml"
            path.write_text(contents)
            return load_config(path)

    def test_override_merges_bindings(self):
        config = self.load('speed = 200\n[bindings]\nKEY_KP5 = "passthrough"\nKEY_KP0 = "left_hold"\n')
        self.assertEqual(config["speed"], 200)
        self.assertEqual(config["bindings"]["KEY_KP8"], "up")
        self.assertEqual(config["bindings"]["KEY_KP5"], "passthrough")

    def test_reject_invalid_config(self):
        for contents in ['speed = -1', 'speed = nan', 'enabled = 1', 'devices = "bad"',
                         'tick_rate = 0', 'tick_rate = 2000', 'max_speed = 1', 'unknown = true',
                         '[bindings]\nKEY_KP5 = "bad"', '[bindings]\nKEY_NUMLOCK = "up"']:
            with self.subTest(contents=contents), self.assertRaises(ValueError):
                self.load(contents)


class RelayTests(unittest.TestCase):
    def setUp(self):
        import evdev
        self.codes = evdev.ecodes
        self.config = load_config()
        self.pointer = FakePointer()
        self.controller = Controller(self.config, self.pointer)
        self.forwarded = []
        self.keyboard = Keyboard.__new__(Keyboard)
        self.keyboard.device = SimpleNamespace(path="keyboard")
        self.keyboard.codes = self.codes
        self.keyboard.controller = self.controller
        self.keyboard.bindings = resolve_bindings(self.config, self.codes)
        self.keyboard.consumed = set()
        self.keyboard.forwarded = set()
        self.keyboard.initial_keys = set()
        self.keyboard.relay = SimpleNamespace(write_event=self.forwarded.append)

    def key(self, code, value):
        self.keyboard.event(SimpleNamespace(type=self.codes.EV_KEY, code=code, value=value))

    def toggle(self):
        self.key(self.codes.KEY_NUMLOCK, 1)
        self.key(self.codes.KEY_NUMLOCK, 2)
        self.key(self.codes.KEY_NUMLOCK, 0)

    def test_passthrough_and_toggle_repeat(self):
        self.key(self.codes.KEY_KP8, 1)
        self.key(self.codes.KEY_KP8, 0)
        self.toggle()
        self.assertTrue(self.controller.enabled)
        self.key(self.codes.KEY_A, 1)
        self.key(self.codes.KEY_A, 0)
        self.key(self.codes.KEY_KP8, 1)
        self.key(self.codes.KEY_KP8, 2)
        self.controller.tick(0.02)
        self.assertEqual(self.pointer.moves, [(0, -7)])
        self.toggle()
        self.key(self.codes.KEY_KP8, 0)
        self.assertEqual(len(self.forwarded), 4)
        self.assertFalse(self.keyboard.consumed)

    def test_key_held_before_enable_has_matching_release(self):
        self.key(self.codes.KEY_KP8, 1)
        self.toggle()
        self.key(self.codes.KEY_KP8, 2)
        self.key(self.codes.KEY_KP8, 0)
        self.assertEqual([event.value for event in self.forwarded], [1, 2, 0])
        self.assertEqual(self.controller.pressed, {})

    def test_overflow_triggers_reconnect(self):
        with self.assertRaises(OSError):
            self.keyboard.event(SimpleNamespace(type=self.codes.EV_SYN, code=self.codes.SYN_DROPPED))

    def test_keys_held_during_attachment_are_ignored_until_release(self):
        self.keyboard.initial_keys.add(self.codes.KEY_VOLUMEDOWN)
        self.key(self.codes.KEY_VOLUMEDOWN, 2)
        self.key(self.codes.KEY_VOLUMEDOWN, 0)
        self.assertEqual(self.forwarded, [])
        self.key(self.codes.KEY_VOLUMEDOWN, 1)
        self.key(self.codes.KEY_VOLUMEDOWN, 0)
        self.assertEqual([event.value for event in self.forwarded], [1, 0])


class CliTests(unittest.TestCase):
    def test_list_devices_closes_handles(self):
        device = SimpleNamespace(name="Test keypad", close=lambda: closed.append(True))
        closed = []
        output = io.StringIO()
        with patch("sys.argv", ["numtrack", "--list-devices"]), contextlib.redirect_stdout(output), \
                patch("evdev.list_devices", return_value=["/dev/input/event99"]), \
                patch("evdev.InputDevice", return_value=device):
            self.assertEqual(main(), 0)
        self.assertEqual(output.getvalue(), "/dev/input/event99\tTest keypad\n")
        self.assertEqual(closed, [True])


if __name__ == "__main__":
    unittest.main()
