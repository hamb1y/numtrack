import math


DIRECTIONS = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}


class Controller:
    def __init__(self, config, pointer):
        self.config = config
        self.pointer = pointer
        self.enabled = config["enabled"] is True
        self.pressed = {}
        self.elapsed = 0.0
        self.remainder = [0.0, 0.0]

    def toggle(self):
        self.enabled = not self.enabled
        self.clear()

    def clear(self, source=None):
        for token in list(self.pressed):
            if source is None or token[0] == source:
                self.key(token, self.pressed[token], 0)
        self.elapsed = 0.0
        self.remainder = [0.0, 0.0]

    def key(self, token, action, value):
        if value == 2:
            return
        if value == 0:
            previous = self.pressed.pop(token, None)
            if previous and previous.endswith("_hold") and previous not in self.pressed.values():
                self.pointer.button(previous.removesuffix("_hold"), False)
            return
        if not self.enabled or token in self.pressed:
            return
        self.pressed[token] = action
        if action.endswith("_click"):
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
        length = math.hypot(horizontal, vertical)
        if not self.enabled or not length:
            self.elapsed = 0.0
            self.remainder = [0.0, 0.0]
            return
        seconds = min(seconds, 0.05)
        speed = min(self.config["max_speed"], self.config["speed"] + self.config["acceleration"] * self.elapsed)
        self.elapsed += seconds
        distances = [horizontal / length * speed * seconds, vertical / length * speed * seconds]
        movement = []
        for axis, distance in enumerate(distances):
            total = self.remainder[axis] + distance
            whole = math.trunc(total)
            self.remainder[axis] = total - whole
            movement.append(whole)
        if any(movement):
            self.pointer.move(*movement)
