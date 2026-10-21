import logging
import os
import select
import signal
import time

from .core import Controller


LOG = logging.getLogger("numtrack")


class Pointer:
    def __init__(self, evdev):
        self.codes = evdev.ecodes
        self.device = evdev.UInput({
            self.codes.EV_KEY: [self.codes.BTN_LEFT, self.codes.BTN_RIGHT, self.codes.BTN_MIDDLE],
            self.codes.EV_REL: [self.codes.REL_X, self.codes.REL_Y],
        }, name="numtrack pointer")

    def button(self, name, pressed):
        self.device.write(self.codes.EV_KEY, getattr(self.codes, f"BTN_{name.upper()}"), int(pressed))
        self.device.syn()

    def move(self, horizontal, vertical):
        self.device.write(self.codes.EV_REL, self.codes.REL_X, horizontal)
        self.device.write(self.codes.EV_REL, self.codes.REL_Y, vertical)
        self.device.syn()


class Keyboard:
    def __init__(self, device, evdev, controller, bindings):
        self.device = device
        self.codes = evdev.ecodes
        self.controller = controller
        self.bindings = bindings
        self.consumed = set()
        self.forwarded = set()
        self.initial_keys = set()
        self.original_leds = device.leds()
        self.relay = evdev.UInput.from_device(device, name=f"numtrack keyboard {device.name}"[:79])
        try:
            device.grab()
            self.initial_keys = set(device.active_keys())
            if self.initial_keys:
                LOG.info("Ignoring keys already held on %s until release: %s", device.name, sorted(self.initial_keys))
            self.update_led()
        except BaseException:
            try:
                device.ungrab()
            except OSError:
                pass
            self.relay.close()
            raise

    def update_led(self):
        if self.codes.LED_NUML in self.device.capabilities().get(self.codes.EV_LED, []):
            self.device.set_led(self.codes.LED_NUML, int(self.controller.enabled))

    def feedback(self):
        for event in self.relay.read():
            if event.type == self.codes.EV_LED:
                if event.code == self.codes.LED_NUML:
                    self.update_led()
                else:
                    self.device.write_event(event)

    def event(self, event):
        codes = self.codes
        if event.type == codes.EV_SYN and event.code == codes.SYN_DROPPED:
            raise OSError("Input overflow; reopening keyboard to reset key state")
        if event.type == codes.EV_KEY:
            if event.code in self.initial_keys:
                if event.value == 0:
                    self.initial_keys.discard(event.code)
                return
            token = (self.device.path, event.code)
            if event.code == codes.KEY_NUMLOCK:
                if event.value == 1:
                    self.controller.toggle()
                    LOG.info("Mouse mode %s", "enabled" if self.controller.enabled else "disabled")
                return
            action = self.bindings.get(event.code)
            if event.code in self.consumed or (
                action and self.controller.enabled and event.value == 1 and event.code not in self.forwarded
            ):
                self.controller.key(token, action, event.value)
                if event.value == 0:
                    self.consumed.discard(event.code)
                else:
                    self.consumed.add(event.code)
                return
            if event.value == 1:
                self.forwarded.add(event.code)
            elif event.value == 0:
                self.forwarded.discard(event.code)
        if event.type != codes.EV_MSC:
            self.relay.write_event(event)

    def close(self):
        self.controller.clear(self.device.path)
        try:
            for code in self.forwarded:
                self.relay.write(self.codes.EV_KEY, code, 0)
            self.relay.syn()
        except OSError:
            pass
        finally:
            self.relay.close()
            try:
                self.device.set_led(self.codes.LED_NUML, int(self.codes.LED_NUML in self.original_leds))
                self.device.ungrab()
            except OSError:
                pass
            self.device.close()


def resolve_bindings(config, codes):
    result = {}
    for name, action in config["bindings"].items():
        code = getattr(codes, name, None)
        if code is None:
            raise ValueError(f"Unknown Linux key code: {name}")
        if action != "passthrough":
            result[code] = action
    return result


def run(config, evdev):
    codes = evdev.ecodes
    bindings = resolve_bindings(config, codes)
    pointer = Pointer(evdev)
    controller = Controller(config, pointer)
    keyboards = {}
    running = True
    interval = 1 / config["tick_rate"]
    last_tick = time.monotonic()
    next_scan = 0.0
    previous_handlers = {}
    failures = {}
    initialized = config["enabled"] != "numlock"

    def stop(signum, frame):
        nonlocal running
        running = False

    try:
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous_handlers[signum] = signal.signal(signum, stop)
        while running:
            now = time.monotonic()
            if now >= next_scan:
                next_scan = now + 1
                paths = config["devices"] or evdev.list_devices()
                for path in paths:
                    canonical = os.path.realpath(path)
                    if canonical in keyboards:
                        continue
                    device = None
                    try:
                        device = evdev.InputDevice(canonical)
                        keys = device.capabilities().get(codes.EV_KEY, [])
                        if device.name.startswith("numtrack "):
                            device.close()
                            continue
                        if not config["devices"] and is_virtual_device(canonical):
                            device.close()
                            continue
                        if not config["devices"] and not {codes.KEY_NUMLOCK, codes.KEY_KP8, codes.KEY_KP2}.issubset(keys):
                            device.close()
                            continue
                        if codes.KEY_NUMLOCK not in keys:
                            raise ValueError("Selected device has no NumLock key")
                        if not initialized:
                            controller.enabled = codes.LED_NUML in device.leds()
                        keyboards[canonical] = Keyboard(device, evdev, controller, bindings)
                        if not initialized:
                            initialized = True
                            LOG.info("Initial mouse mode %s (NumLock)", "enabled" if controller.enabled else "disabled")
                        failures.pop(path, None)
                        LOG.info("Attached %s (%s)", device.name, path)
                    except (OSError, ValueError) as error:
                        if device is not None:
                            device.close()
                        if failures.get(path) != str(error):
                            LOG.warning("Cannot attach %s: %s", path, error)
                            failures[path] = str(error)
                if not keyboards:
                    LOG.debug("Waiting for an accessible keypad keyboard")
            descriptors = [descriptor for keyboard in keyboards.values()
                           for descriptor in (keyboard.device.fd, keyboard.relay.fd)]
            readable, _, _ = select.select(descriptors, [], [], interval)
            enabled_before = controller.enabled
            for path, keyboard in list(keyboards.items()):
                try:
                    if keyboard.device.fd in readable:
                        for event in keyboard.device.read():
                            keyboard.event(event)
                    if keyboard.relay.fd in readable:
                        keyboard.feedback()
                except BlockingIOError:
                    pass
                except OSError as error:
                    LOG.warning("Detaching %s: %s", path, error)
                    keyboard.close()
                    del keyboards[path]
            if controller.enabled != enabled_before:
                for keyboard in keyboards.values():
                    try:
                        keyboard.update_led()
                    except OSError:
                        pass
            now = time.monotonic()
            controller.tick(now - last_tick)
            last_tick = now
    finally:
        try:
            for keyboard in keyboards.values():
                keyboard.close()
            controller.clear()
        finally:
            pointer.device.close()
            for signum, handler in previous_handlers.items():
                signal.signal(signum, handler)


def is_virtual_device(path):
    device_path = os.path.realpath(f"/sys/class/input/{os.path.basename(path)}/device")
    return device_path.startswith("/sys/devices/virtual/")
