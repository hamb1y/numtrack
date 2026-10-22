import os
import json
from pathlib import Path
import select
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import uuid


@unittest.skipUnless(os.environ.get("NUMTRACK_UINPUT_TEST") == "1", "set NUMTRACK_UINPUT_TEST=1 for kernel test")
class KernelTests(unittest.TestCase):
    def test_real_keypad_to_pointer_and_keyboard(self):
        import evdev
        codes = evdev.ecodes
        name = f"NT test {uuid.uuid4().hex[:8]}"
        key_names = ["KEY_NUMLOCK", "KEY_KP8", "KEY_KP4", "KEY_KP6", "KEY_KP2",
                     "KEY_KP7", "KEY_KP5", "KEY_KP9", "KEY_KP3", "KEY_KP1", "KEY_A"]
        source = evdev.UInput({codes.EV_KEY: [getattr(codes, key) for key in key_names],
                               codes.EV_LED: [codes.LED_NUML, codes.LED_CAPSL]}, name=name)
        self.addCleanup(source.close)
        process = None
        receivers = {}
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "keypad"
            source_path.symlink_to(source.device.path)
            config = Path(directory) / "config.toml"
            config.write_text(f'devices = ["{source_path}"]\nenabled = false\nacceleration = 0\n')
            with (Path(directory) / "log").open("w+") as log:
                try:
                    process = subprocess.Popen([sys.executable, "-m", "numtrack", "--config", str(config)],
                                               stdout=log, stderr=log)
                    deadline = time.monotonic() + 8
                    while len(receivers) < 2 and time.monotonic() < deadline:
                        if process.poll() is not None:
                            log.seek(0)
                            self.fail(log.read())
                        for path in evdev.list_devices():
                            device = evdev.InputDevice(path)
                            wanted = device.name in ("numtrack pointer", f"numtrack keyboard {name}")
                            if wanted and device.name not in receivers:
                                device.grab()
                                receivers[device.name] = device
                            else:
                                device.close()
                        time.sleep(0.02)
                    self.assertEqual(len(receivers), 2)
                    pointer = receivers["numtrack pointer"]
                    keyboard = receivers[f"numtrack keyboard {name}"]
                    time.sleep(0.15)
                    if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE") and shutil.which("hyprctl"):
                        desktop = json.loads(subprocess.check_output(["hyprctl", "-j", "devices"], text=True))
                        self.assertTrue(any(device["name"].startswith("numtrack-pointer") for device in desktop["mice"]))
                        self.assertTrue(any(device["name"] == f"numtrack-keyboard-{name.lower().replace(' ', '-')}"
                                            for device in desktop["keyboards"]))

                    def emit(key, value):
                        source.write(codes.EV_KEY, getattr(codes, key), value)
                        source.syn()

                    def collect(device, duration=0.08):
                        events = []
                        end = time.monotonic() + duration
                        while time.monotonic() < end:
                            ready, _, _ = select.select([device.fd], [], [], max(0, end - time.monotonic()))
                            if ready:
                                events.extend(device.read())
                        return events

                    def values(events, event_type, code):
                        return [event.value for event in events if event.type == event_type and event.code == code]

                    emit("KEY_KP8", 1)
                    emit("KEY_KP8", 0)
                    self.assertEqual(values(collect(keyboard), codes.EV_KEY, codes.KEY_KP8), [1, 0])
                    self.assertEqual(collect(pointer), [])
                    emit("KEY_NUMLOCK", 1)
                    emit("KEY_NUMLOCK", 2)
                    emit("KEY_NUMLOCK", 0)
                    time.sleep(0.05)
                    self.assertIn(codes.LED_NUML, source.device.leds())
                    for key, axis, sign in [("KEY_KP8", codes.REL_Y, -1), ("KEY_KP4", codes.REL_X, -1),
                                             ("KEY_KP6", codes.REL_X, 1), ("KEY_KP2", codes.REL_Y, 1)]:
                        emit(key, 1)
                        events = collect(pointer)
                        emit(key, 0)
                        collect(pointer, 0.02)
                        movement = values(events, codes.EV_REL, axis)
                        self.assertTrue(movement, key)
                        self.assertTrue(all(value * sign > 0 for value in movement), key)
                    for key, button in [("KEY_KP7", codes.BTN_LEFT), ("KEY_KP5", codes.BTN_LEFT),
                                         ("KEY_KP9", codes.BTN_RIGHT), ("KEY_KP3", codes.BTN_MIDDLE)]:
                        emit(key, 1)
                        emit(key, 2)
                        emit(key, 0)
                        self.assertEqual(values(collect(pointer), codes.EV_KEY, button), [1, 0], key)
                    emit("KEY_A", 1)
                    emit("KEY_A", 0)
                    relayed = collect(keyboard)
                    self.assertEqual(values(relayed, codes.EV_KEY, codes.KEY_A), [1, 0])
                    self.assertEqual(values(relayed, codes.EV_KEY, codes.KEY_KP8), [])
                    self.assertEqual(values(relayed, codes.EV_KEY, codes.KEY_NUMLOCK), [])
                    emit("KEY_KP1", 1)
                    emit("KEY_KP1", 2)
                    emit("KEY_KP1", 0)
                    for key, sign in [("KEY_KP8", 1), ("KEY_KP2", -1)]:
                        emit(key, 1)
                        events = collect(pointer, 0.8)
                        emit(key, 0)
                        collect(pointer, 0.02)
                        scrolling = values(events, codes.EV_REL, codes.REL_WHEEL_HI_RES)
                        self.assertTrue(scrolling, key)
                        self.assertTrue(all(0 < value * sign < 120 for value in scrolling), key)
                        self.assertTrue(values(events, codes.EV_REL, codes.REL_WHEEL), key)
                        self.assertEqual(values(events, codes.EV_REL, codes.REL_X), [])
                        self.assertEqual(values(events, codes.EV_REL, codes.REL_Y), [])
                    emit("KEY_KP4", 1)
                    self.assertEqual(collect(pointer), [])
                    emit("KEY_KP4", 0)
                    emit("KEY_KP1", 1)
                    emit("KEY_KP1", 0)
                    emit("KEY_KP5", 1)
                    self.assertEqual(values(collect(pointer), codes.EV_KEY, codes.BTN_LEFT), [1])
                    emit("KEY_KP6", 1)
                    self.assertTrue(values(collect(pointer), codes.EV_REL, codes.REL_X))
                    emit("KEY_KP6", 0)
                    emit("KEY_KP5", 0)
                    self.assertEqual(values(collect(pointer), codes.EV_KEY, codes.BTN_LEFT), [0])
                    emit("KEY_KP7", 1)
                    collect(pointer)
                    emit("KEY_NUMLOCK", 1)
                    emit("KEY_NUMLOCK", 0)
                    self.assertEqual(values(collect(pointer), codes.EV_KEY, codes.BTN_LEFT), [0])
                    emit("KEY_KP7", 0)
                    relayed = collect(keyboard)
                    self.assertEqual(values(relayed, codes.EV_KEY, codes.KEY_KP1), [])
                    self.assertEqual(values(relayed, codes.EV_KEY, codes.KEY_KP7), [])
                    self.assertNotIn(codes.LED_NUML, source.device.leds())
                    emit("KEY_NUMLOCK", 1)
                    emit("KEY_NUMLOCK", 0)
                    emit("KEY_KP5", 1)
                    self.assertEqual(values(collect(pointer), codes.EV_KEY, codes.BTN_LEFT), [1])
                    source.close()
                    self.assertEqual(values(collect(pointer, 0.2), codes.EV_KEY, codes.BTN_LEFT), [0])
                    keyboard.close()
                    del receivers[f"numtrack keyboard {name}"]
                    replacement = evdev.UInput({codes.EV_KEY: [getattr(codes, key) for key in key_names]}, name=name)
                    self.addCleanup(replacement.close)
                    source_path.unlink()
                    source_path.symlink_to(replacement.device.path)
                    deadline = time.monotonic() + 4
                    while time.monotonic() < deadline:
                        for path in evdev.list_devices():
                            device = evdev.InputDevice(path)
                            if device.name == f"numtrack keyboard {name}":
                                device.grab()
                                receivers[device.name] = device
                                break
                            device.close()
                        if len(receivers) == 2:
                            break
                        time.sleep(0.02)
                    self.assertEqual(len(receivers), 2, "Replacement keyboard did not attach")
                    time.sleep(0.1)
                    replacement.write(codes.EV_KEY, codes.KEY_KP7, 1)
                    replacement.syn()
                    self.assertEqual(values(collect(pointer), codes.EV_KEY, codes.BTN_LEFT), [1])
                    process.terminate()
                    self.assertEqual(process.wait(timeout=5), 0)
                finally:
                    if process is not None and process.poll() is None:
                        process.terminate()
                        process.wait(timeout=5)
                    for device in receivers.values():
                        device.close()
