# numtrack

Use your numpad as a mouse. NumLock turns it on and off.

Numtrack runs on Linux, including Hyprland and other Wayland desktops. It reads
the keypad through evdev and creates a virtual mouse through uinput. No
compositor keybinds, X11 tools, or Wayland extensions required.

| Numpad key | Action |
| :---: | --- |
| **8** | Move up |
| **4** | Move left |
| **6** | Move right |
| **2** | Move down |
| **7**, **5** | Hold left button while pressed; tap to click |
| **9** | Right click |
| **3** | Middle click |
| **1** | Toggle scroll mode: **8** scrolls up, **2** scrolls down |
| **NumLock** | Toggle mouse mode |

Hold a direction to keep moving. Combine directions for diagonals. Hold **5**
or **7** and a direction to drag; release to drop. If both are held, the left
button stays down until both are released. Right and middle clicks fire once
per press.

Tap **1** to enter scroll mode, then hold **8** or **2** for smooth vertical
scrolling. Tap **1** again to return to pointer movement. **4** and **6** do
nothing in scroll mode. Turning mouse mode off with NumLock resets scroll mode.
Scroll output uses high-resolution wheel events with legacy wheel compatibility.

Movement starts gently at 100 pointer units/sec and eases up to 850 over about
4.2 seconds. Straight and diagonal speeds match. Releasing all directions or
reversing direction resets the ramp for precise adjustments. Scrolling has its
own slower easing curve and speed settings.

By default, startup follows the physical keyboard's NumLock LED: if NumLock is
already on, mouse mode starts on. The LED then shows mouse mode. Other keys
pass through normally; with mouse mode off, the numpad passes through too.
Disabling the mode, unplugging the keypad, or stopping Numtrack releases its
held mouse buttons.

## Install

### Homebrew on Linux

```sh
brew install hamb1y/tap/numtrack
numtrack --check-config
numtrack
```

Installing does **not** start the daemon. Run `numtrack` in a terminal first;
it should log your physical keyboard and the initial mouse mode. Then use
the numpad. Numtrack is Linux-only, even when installed through Homebrew.

### From source

Requires Python 3.11+, a C compiler, Python development headers, and Linux input
headers. On Arch, install `base-devel python linux-api-headers` if needed.

```sh
git clone https://github.com/hamb1y/numtrack.git
cd numtrack
uv tool install .
~/.local/bin/numtrack
```

`pipx install .` also works. Add `~/.local/bin` to your shell's PATH if you want
to invoke `numtrack` without its full path.

### Input permissions

Your user needs read/write access to the selected `/dev/input/event*` devices
and `/dev/uinput`. Check your distribution's existing permissions first:

```sh
ls -l /dev/uinput /dev/input/event*
id
```

On distributions with an `input` group, the usual setup is:

```sh
sudo modprobe uinput
sudo usermod -aG input "$USER"
echo 'KERNEL=="uinput", SUBSYSTEM=="misc", GROUP="input", MODE="0660"' | sudo tee /etc/udev/rules.d/70-numtrack-uinput.rules
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=misc
```

Log out and back in after changing groups. For module loading after reboot,
put `uinput` in `/etc/modules-load.d/uinput.conf` if it is not loaded already.
Membership in `input` allows reading keyboards; only grant it to trusted users.
Run Numtrack as your normal user.

## Autostart

Choose **one** method. Stop any foreground Numtrack process first.

### Homebrew service

```sh
brew services start numtrack
brew services info numtrack
```

Stop with `brew services stop numtrack`. This uses a user service; do not use
`sudo brew services`.

### Hyprland

For a Homebrew install:

```ini
exec-once = /home/linuxbrew/.linuxbrew/bin/numtrack
```

For a uv or pipx install:

```ini
exec-once = ~/.local/bin/numtrack
```

If Homebrew uses a different prefix, use the executable path from
`command -v numtrack`. Adding `exec-once` takes effect on the next session;
run `numtrack` yourself to start it now.

### systemd user service for source installs

From the cloned repository:

```sh
mkdir -p ~/.config/systemd/user
cp contrib/numtrack.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now numtrack.service
```

The supplied unit expects `~/.local/bin/numtrack` and a desktop that manages
`graphical-session.target`. Stop it with `systemctl --user stop numtrack`.

## Configure

Configuration is optional. Defaults are built in. To edit them:

```sh
mkdir -p ~/.config/numtrack
numtrack --print-config > ~/.config/numtrack/config.toml
numtrack --check-config
```

The default path is `$XDG_CONFIG_HOME/numtrack/config.toml`, falling back to
`~/.config/numtrack/config.toml`. Use `--config PATH` for another file. Restart
Numtrack after changes.

```toml
enabled = "numlock"
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
```

| Setting | Meaning |
| --- | --- |
| `enabled` | `"numlock"` follows the first attached keyboard's NumLock LED at startup; `true` or `false` forces the initial mode. A keyboard without an LED starts off in `"numlock"` mode. |
| `devices` | Empty means discover physical keyboards with NumLock, KP8, and KP2. Set explicit paths to limit capture. |
| `speed` | Starting pointer units per second. |
| `max_speed` | Maximum pointer units per second; at least `speed`. |
| `acceleration` | Ramp rate: time to maximum is `(max_speed - speed) / acceleration`, with smooth easing; `0` gives constant starting speed. |
| `scroll_speed` | Starting scroll speed in wheel detents per second. |
| `scroll_max_speed` | Maximum scroll speed in detents per second. |
| `scroll_acceleration` | Scroll ramp rate, using the same easing formula; `0` gives constant starting speed. |
| `tick_rate` | Update frequency, from 10 to 1000 Hz. |

Compositor pointer acceleration and sensitivity still apply. Discovery checks
once per second and reconnects unplugged devices. Auto-discovery excludes
virtual devices such as ydotool; an explicit device path can opt one in.
Prefer stable `/dev/input/by-id/...-event-kbd` paths over numbered event nodes:

```toml
devices = ["/dev/input/by-id/usb-YOUR_KEYPAD-event-kbd"]
```

Bindings merge with defaults. To remove a mapping, set it to `"passthrough"`:

```toml
[bindings]
KEY_KP5 = "passthrough"
KEY_KP0 = "left_hold"
```

Any Linux `KEY_*` name can be bound except the reserved `KEY_NUMLOCK` toggle.
Actions are `up`, `down`, `left`, `right`, `left_click`, `right_click`,
`middle_click`, `left_hold`, `right_hold`, `middle_hold`, `scroll_toggle`, and
`passthrough`. Hold actions last while their key is pressed. `scroll_toggle`
switches modes once per press.

Upgrading from 0.1: existing config files still override the new defaults.
Update KP5/KP7 to `left_hold` and KP1 to `scroll_toggle`, or remove those
overrides. Remove old speed overrides to use the gentler movement defaults.

## Troubleshooting

**It types numbers instead of moving.** Make sure Numtrack is running, then
check its log for `Attached` followed by your physical keyboard's name. Press
NumLock once to toggle the mode. If you configured `enabled = false`, it always
starts off regardless of the LED. Run `numtrack --verbose` for diagnostics.

**It attaches to the wrong device.** Use `numtrack --list-devices` and set
`devices` explicitly. Another program's exclusive keyboard grab can prevent
Numtrack from attaching. Keys already held at attachment are ignored until
released, so a stale media-key state cannot prevent discovery.

**Permission denied or missing uinput.** Follow the input-permissions setup,
then log out and back in. `modprobe uinput` creates the uinput device when the
module is available.

**Numpad types arrows when mouse mode is off.** Numtrack reserves NumLock for
its own toggle. Normal typing uses the desktop's separate numeric-lock setting.
For Hyprland, set `numlock_by_default = true` in your `input` block if desired.
The physical LED indicates Numtrack's mode, independently of numeric typing.

**Changes do not apply.** Restart the daemon. Avoid running multiple instances
or configuring more than one autostart method.

## Development

```sh
uv venv .venv
uv pip install --python .venv/bin/python -e .
.venv/bin/python -m unittest discover -s tests -v
```

Kernel integration tests create temporary virtual input devices and require
input/uinput access. Run with no other Numtrack instance active:

```sh
NUMTRACK_UINPUT_TEST=1 .venv/bin/python -m unittest discover -s tests -v
```

They exercise every default binding, keyboard forwarding, dragging, mode
changes, unplug/reconnect cleanup, and shutdown. When run inside Hyprland,
they also check that Hyprland recognizes the virtual mouse and keyboard.
