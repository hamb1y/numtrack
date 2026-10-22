import math


DIRECTIONS = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}


class Controller:
    def __init__(self, config, pointer):
        self.config = config
        self.pointer = pointer
        self.enabled = config["enabled"] is True
        self.pressed = {}
        self.scroll_mode = False
        self.reset_motion()

    def reset_motion(self):
        self.elapsed = 0.0
        self.remainder = [0.0, 0.0]
        self.scroll_remainder = 0.0
        self.direction = None

    def toggle(self):
        self.enabled = not self.enabled
        self.clear()

    def clear(self, source=None):
        for token in list(self.pressed):
            if source is None or token[0] == source:
                self.key(token, self.pressed[token], 0)
        self.scroll_mode = False
        self.reset_motion()

    def key(self, token, action, value):
        if value == 2:
            return
        if value == 0:
            previous = self.pressed.pop(token, None)
            if previous and previous.endswith("_hold") and previous not in self.pressed.values():
                self.pointer.button(previous.removesuffix("_hold"), False)
            if previous in DIRECTIONS and not any(action in DIRECTIONS for action in self.pressed.values()):
                self.reset_motion()
            return
        if not self.enabled or token in self.pressed:
            return
        self.pressed[token] = action
        if action == "scroll_toggle":
            self.scroll_mode = not self.scroll_mode
            self.reset_motion()
        elif action.endswith("_click"):
            button = action.removesuffix("_click")
            if f"{button}_hold" not in self.pressed.values():
                self.pointer.button(button, True)
                self.pointer.button(button, False)
        elif action.endswith("_hold"):
            if list(self.pressed.values()).count(action) == 1:
                self.pointer.button(action.removesuffix("_hold"), True)

    def tick(self, seconds):
        horizontal = vertical = 0
        for action in self.pressed.values():
            if action in DIRECTIONS:
                delta_x, delta_y = DIRECTIONS[action]
                horizontal += delta_x
                vertical += delta_y
        if self.scroll_mode:
            horizontal = 0
        length = math.hypot(horizontal, vertical)
        if not self.enabled or not length:
            self.reset_motion()
            return
        direction = (horizontal / length, vertical / length)
        if self.direction is not None:
            alignment = sum(previous * current for previous, current in zip(self.direction, direction))
            if alignment <= 0:
                self.reset_motion()
        self.direction = direction
        seconds = min(seconds, 0.05)
        prefix = "scroll_" if self.scroll_mode else ""
        speed = self.config[f"{prefix}speed"]
        maximum = self.config[f"{prefix}max_speed"]
        acceleration = self.config[f"{prefix}acceleration"]
        if acceleration and maximum > speed:
            progress = min(1.0, self.elapsed * acceleration / (maximum - speed))
            speed += (maximum - speed) * progress * progress * (3 - 2 * progress)
        self.elapsed += seconds
        if self.scroll_mode:
            total = self.scroll_remainder - direction[1] * speed * seconds * 120
            whole = math.trunc(total)
            self.scroll_remainder = total - whole
            if whole:
                self.pointer.scroll(whole)
            return
        distances = [horizontal / length * speed * seconds, vertical / length * speed * seconds]
        movement = []
        for axis, distance in enumerate(distances):
            total = self.remainder[axis] + distance
            whole = math.trunc(total)
            self.remainder[axis] = total - whole
            movement.append(whole)
        if any(movement):
            self.pointer.move(*movement)
