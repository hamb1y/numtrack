import argparse
import logging
import sys

from .config import DEFAULT_CONFIG, load_config


def main():
    parser = argparse.ArgumentParser(description="NumLock-toggled keypad mouse for Wayland/Linux")
    parser.add_argument("--version", action="version", version="numtrack 0.1.0")
    parser.add_argument("--config", metavar="PATH", help="TOML configuration path")
    parser.add_argument("--print-config", action="store_true", help="print defaults and exit")
    parser.add_argument("--check-config", action="store_true", help="validate configuration and exit")
    parser.add_argument("--list-devices", action="store_true", help="list accessible input devices")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="numtrack: %(message)s")
    try:
        if args.print_config:
            print(DEFAULT_CONFIG, end="")
            return 0
        config = load_config(args.config)
        try:
            import evdev
        except ImportError:
            parser.error("python-evdev is required; install with: pip install .")
        from .backend import resolve_bindings, run
        resolve_bindings(config, evdev.ecodes)
        if args.check_config:
            print("Configuration valid")
            return 0
        if args.list_devices:
            for path in sorted(evdev.list_devices()):
                try:
                    device = evdev.InputDevice(path)
                    try:
                        print(f"{path}\t{device.name}")
                    finally:
                        device.close()
                except OSError:
                    continue
            return 0
        run(config, evdev)
        return 0
    except (OSError, ValueError) as error:
        print(f"numtrack: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0
