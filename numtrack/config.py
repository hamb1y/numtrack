import math
import os
from pathlib import Path
import tomllib


DEFAULT_CONFIG = '''# ~/.config/numtrack/config.toml
# Follow the physical NumLock LED at startup. Or use true/false to override.
enabled = "numlock"
# Empty list auto-discovers keyboards with a numpad; by-id paths also work.
devices = []
speed = 100.0
max_speed = 850.0
acceleration = 180.0
scroll_speed = 1.5
scroll_max_speed = 12.0
scroll_acceleration = 3.0
tick_rate = 120

[bindings]
KEY_KP8 = "up"
KEY_KP4 = "left"
KEY_KP6 = "right"
KEY_KP2 = "down"
KEY_KP7 = "left_hold"
KEY_KP5 = "left_hold"
KEY_KP9 = "right_click"
KEY_KP3 = "middle_click"
KEY_KP1 = "scroll_toggle"
'''

ACTIONS = {
    "up", "left", "right", "down", "left_click", "right_click",
    "middle_click", "left_hold", "right_hold", "middle_hold", "scroll_toggle", "passthrough",
}


def config_path():
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "numtrack/config.toml"


def load_config(path=None):
    config = tomllib.loads(DEFAULT_CONFIG)
    target = Path(path) if path else config_path()
    if path or target.exists():
        with target.open("rb") as handle:
            supplied = tomllib.load(handle)
        unknown = supplied.keys() - config.keys()
        if unknown:
            raise ValueError(f"Unknown configuration options: {', '.join(sorted(unknown))}")
        bindings = supplied.pop("bindings", {})
        if not isinstance(bindings, dict):
            raise ValueError("bindings must be a table")
        config.update(supplied)
        config["bindings"].update(bindings)
    if not isinstance(config["enabled"], bool) and config["enabled"] != "numlock":
        raise ValueError('enabled must be true, false, or "numlock"')
    if not isinstance(config["devices"], list) or any(
        not isinstance(device, str) or not device for device in config["devices"]
    ):
        raise ValueError("devices must be an array of nonempty paths")
    for option in ("speed", "max_speed", "acceleration", "scroll_speed", "scroll_max_speed",
                   "scroll_acceleration", "tick_rate"):
        value = config[option]
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
            raise ValueError(f"{option} must be a finite number")
        if value < 0 or (not option.endswith("acceleration") and value == 0):
            raise ValueError(f"Invalid {option}: {value}")
    if not 10 <= config["tick_rate"] <= 1000:
        raise ValueError("tick_rate must be between 10 and 1000")
    if config["max_speed"] < config["speed"]:
        raise ValueError("max_speed must be at least speed")
    if config["scroll_max_speed"] < config["scroll_speed"]:
        raise ValueError("scroll_max_speed must be at least scroll_speed")
    for key, action in config["bindings"].items():
        if not key.startswith("KEY_") or not isinstance(action, str) or action not in ACTIONS:
            raise ValueError(f"Invalid binding: {key} = {action!r}")
        if key == "KEY_NUMLOCK":
            raise ValueError("KEY_NUMLOCK is reserved for toggling")
    return config
