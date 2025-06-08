import os
import random
import uuid
from src.utils import BaseControl, Bean, run_cmd
from PIL import Image

ADB_PATH = "lib/adb/adb.exe"
if not os.path.exists(ADB_PATH):
    ADB_PATH = "adb"


class Adb(BaseControl):
    def __init__(self, address):
        super().__init__(address)

    @classmethod
    def check_adb(self):
        Bean.adb_devices.clear()
        for line in run_cmd(f'"{ADB_PATH}" devices').splitlines():
            if line.startswith("List"):
                continue
            if line.startswith("*"):
                continue
            if line == "\n":
                continue
            device = line.split("\t")[0]
            if device == "":
                continue
            Bean.adb_devices.append(device)
            Bean.cmd_out_list.append(f"检测到设备 {device}")

    @classmethod
    def start(self):
        run_cmd(f'"{ADB_PATH}" start-server')

    @classmethod
    def kill(self):
        run_cmd(f'"{ADB_PATH}" kill-server')

    def connect(self):
        res = run_cmd(f'"{ADB_PATH}" connect ' + self.address)
        if "connected" in res:
            return True
        return False

    def cmd(self, cmd):
        return run_cmd(self.make_cmd(cmd))

    def dis_connect(self):
        run_cmd(f'"{ADB_PATH}" disconnect ' + self.address)
        return super().dis_connect()

    def click(self, xy):
        x, y = xy
        run_cmd(self.make_cmd(f"shell input tap {x} {y}"))
        return super().click(xy)

    def swiper(self, xy1, xy2):
        fx, fy = xy1
        tx, ty = xy2
        run_cmd(
            self.make_cmd(
                f"shell input swipe {fx} {fy} {tx} {ty} {random.randint(5,9)}00"
            )
        )
        return super().swiper(xy1, xy2)

    def screenshot(self):
        uid = uuid.uuid4()
        run_cmd(self.make_cmd("shell screencap -p /sdcard/screenshot.png"))
        run_cmd(self.make_cmd(f"pull /sdcard/screenshot.png temp/image{uid}.png"))
        image = Image.open(f"temp/image{uid}.png")
        os.remove(f"temp/image{uid}.png")
        return self.pillow_to_cv2(image)

    def make_cmd(self, cmd):
        return f'"{ADB_PATH}" -s {self.address} {cmd}'
