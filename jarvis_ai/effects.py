import random

from PIL import ImageTk

from .theme import Theme

class DvdLogoBouncer:
    def __init__(self, canvas, logo_image, init_w, init_h, spawn_hint: int = 0):
        self.canvas = canvas
        self.logo_image = logo_image if isinstance(logo_image, ImageTk.PhotoImage) else None
        self.dead = False
        self.margin = 22
        self.spawn_hint = int(spawn_hint or 0) % 4
        self.canvas_w = max(int(init_w), 1)
        self.canvas_h = max(int(init_h), 1)
        self.retiring = False
        self.retire_mode = "edge"
        self.entering = True
        self.enter_progress = 0.0
        self.enter_speed = random.uniform(0.22, 0.30)
        self.vx = random.choice([-1, 1]) * random.uniform(2.15, 3.40)
        self.vy = random.choice([-1, 1]) * random.uniform(1.85, 3.00)

        if self.logo_image:
            self.w = max(24, int(self.logo_image.width()))
            self.h = max(24, int(self.logo_image.height()))
            self.item = self.canvas.create_image(0, 0, image=self.logo_image, anchor="nw")
        else:
            self.w = 70
            self.h = 34
            self.item = self.canvas.create_text(0, 0, text="NOOB", anchor="nw", fill=Theme.ACCENT, font=("Segoe UI", 18, "bold"))

        self.target_x, self.target_y = self._pick_target_position()
        self.start_x, self.start_y = self._pick_start_position()
        self.x = self.start_x
        self.y = self.start_y
        self.retire_vx = 0.0
        self.retire_vy = 0.0
        self._draw()

    def _bounds(self, canvas_w=None, canvas_h=None):
        w = max(int(canvas_w if canvas_w is not None else self.canvas_w), 1)
        h = max(int(canvas_h if canvas_h is not None else self.canvas_h), 1)
        left = self.margin
        right = max(left, w - self.w - self.margin)
        top = self.margin
        bottom = max(top, h - self.h - self.margin)
        return left, right, top, bottom

    def _pick_target_position(self):
        left, right, top, bottom = self._bounds()
        return random.uniform(left, right), random.uniform(top, bottom)

    def _pick_start_position(self):
        left, right, top, bottom = self._bounds()
        spread_x = max(36.0, min(220.0, (right - left) * 0.32))
        spread_y = max(36.0, min(220.0, (bottom - top) * 0.32))
        if self.spawn_hint == 0:
            sx = self.target_x - random.uniform(0.0, spread_x)
            sy = self.target_y - random.uniform(0.0, spread_y)
        elif self.spawn_hint == 1:
            sx = self.target_x + random.uniform(0.0, spread_x)
            sy = self.target_y - random.uniform(0.0, spread_y)
        elif self.spawn_hint == 2:
            sx = self.target_x - random.uniform(0.0, spread_x)
            sy = self.target_y + random.uniform(0.0, spread_y)
        else:
            sx = self.target_x + random.uniform(0.0, spread_x)
            sy = self.target_y + random.uniform(0.0, spread_y)
        return min(max(sx, left), right), min(max(sy, top), bottom)

    def _draw(self):
        if self.dead or not self.item:
            return
        try:
            self.canvas.coords(self.item, int(round(self.x)), int(round(self.y)))
        except Exception:
            pass

    def set_obstacle(self, obstacle_rect):
        # keep compatibility with caller, currently not used for noob drift
        return

    def apply_theme(self):
        if not self.logo_image and self.item:
            try:
                self.canvas.itemconfig(self.item, fill=Theme.ACCENT)
            except Exception:
                pass

    def begin_retire(self, mode: str = "edge"):
        if self.dead:
            return
        self.retiring = True
        self.entering = False
        self.retire_mode = str(mode or "edge").strip().lower()
        if self.retire_mode == "drop":
            self.retire_vx = random.uniform(-1.10, 1.10)
            self.retire_vy = random.uniform(5.20, 7.10)
            return
        left, right, top, bottom = self._bounds()
        cx = self.x + (self.w * 0.5)
        cy = self.y + (self.h * 0.5)
        to_left = cx - left
        to_right = right - cx
        to_top = cy - top
        to_bottom = bottom - cy
        nearest = min(("left", to_left), ("right", to_right), ("top", to_top), ("bottom", to_bottom), key=lambda x: x[1])[0]
        speed = random.uniform(4.10, 6.20)
        if nearest == "left":
            self.retire_vx, self.retire_vy = -speed, random.uniform(-0.70, 0.70)
        elif nearest == "right":
            self.retire_vx, self.retire_vy = speed, random.uniform(-0.70, 0.70)
        elif nearest == "top":
            self.retire_vx, self.retire_vy = random.uniform(-0.70, 0.70), -speed
        else:
            self.retire_vx, self.retire_vy = random.uniform(-0.70, 0.70), speed

    def destroy(self):
        if self.item:
            try:
                self.canvas.delete(self.item)
            except Exception:
                pass
        self.item = None
        self.dead = True

    def ensure_visible(self, canvas_w, canvas_h):
        if self.dead:
            return
        self.canvas_w = max(int(canvas_w), 1)
        self.canvas_h = max(int(canvas_h), 1)
        left, right, top, bottom = self._bounds()
        self.x = min(max(self.x, left), right)
        self.y = min(max(self.y, top), bottom)
        self._draw()

    def move(self, canvas_w, canvas_h):
        if self.dead:
            return
        self.canvas_w = max(int(canvas_w), 1)
        self.canvas_h = max(int(canvas_h), 1)

        if self.entering:
            self.enter_progress = min(1.0, self.enter_progress + self.enter_speed)
            t = self.enter_progress
            ease = t * t * (3 - 2 * t)
            self.x = self.start_x + (self.target_x - self.start_x) * ease
            self.y = self.start_y + (self.target_y - self.start_y) * ease
            self._draw()
            if self.enter_progress >= 0.999:
                self.entering = False
            return

        if self.retiring:
            if self.retire_mode == "drop":
                self.retire_vy = min(11.5, self.retire_vy + 0.22)
                self.retire_vx = max(min(self.retire_vx + random.uniform(-0.10, 0.10), 1.80), -1.80)
                self.x += self.retire_vx
                self.y += self.retire_vy
            else:
                self.x += self.retire_vx
                self.y += self.retire_vy
            self._draw()
            if (
                self.x < -self.w - 120
                or self.y < -self.h - 120
                or self.x > self.canvas_w + 120
                or self.y > self.canvas_h + 120
            ):
                self.destroy()
            return

        self.x += self.vx
        self.y += self.vy
        left, right, top, bottom = self._bounds()

        if self.x <= left:
            self.x = left
            self.vx = abs(self.vx)
        elif self.x >= right:
            self.x = right
            self.vx = -abs(self.vx)
        if self.y <= top:
            self.y = top
            self.vy = abs(self.vy)
        elif self.y >= bottom:
            self.y = bottom
            self.vy = -abs(self.vy)
        self._draw()

__all__ = ["DvdLogoBouncer"]
