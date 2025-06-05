import random
import uiautomator2 as u2
from . import BaseControl


class Uiautomator2(BaseControl):
    def __init__(self, address: str):
        self.d: u2.Device = None
        super().__init__(address)

    def connect(self):
        try:
            self.d = u2.connect(self.address)
            return None
        except Exception as e:
            return e

    def dis_connect(self):
        del self.d
        self.d = None
        return super().dis_connect()

    def click(self, xy):
        x, y = xy
        self.d.click(x, y)
        return super().click(xy)

    def swiper(self, xy1, xy2):
        fx, fy = xy1
        tx, ty = xy2
        duration = random.randint(0,1) + random.randint(5,9) / 10
        self.d.swipe(fx, fy, tx, ty, duration)
        return super().swiper(xy1, xy2)

    def screenshot(self):
        image = self.d.screenshot()
        return self.pillow_to_cv2(image)

    def screenshot_pillow(self):
        image = self.d.screenshot()
        return image
