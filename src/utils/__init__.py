import os
import random
import subprocess

import cv2
import numpy as np
from PIL import Image

class Bean:
    cmd_out_list = []
    adb_devices = []


if not os.path.exists("scripts"):
    os.mkdir("scripts")


def run_cmd(command):
    try:
        output = subprocess.check_output(command, shell=True, stderr=subprocess.STDOUT)
        return output.decode().encode("utf-8").decode("utf-8")
    except subprocess.CalledProcessError as e:
        return str(e)


def check_adb():
    Bean.adb_devices.clear()
    for line in run_cmd("adb devices").splitlines():
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


def random_time(t):
    if t <= 0:
        t = 1
    if random.randint(0, 10) % 2:
        return t + random.randint(0, 1) / 10
    return t - random.randint(0, 9) / 10


def random_xy(t):
    int_num = random.randint(-2, 2)
    float_num = random.randint(-9, 9) / 10
    random_num = int_num + float_num
    return t + random_num


class BaseControl:
    def __init__(self, address: str):
        self.address = address
        self.connected = False

    def connect(self) -> bool:
        self.connected = True

    def dis_connect(self) -> bool:
        self.connected = False

    def screenshot(self) -> cv2:
        pass

    def click(self, xy: list[float]) -> bool:
        pass

    def swiper(self, xy1: list[float], xy2: list[float]) -> bool:
        pass

    def pillow_to_cv2(self, image: Image):
        return cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)

    def cv2_to_pillow(self, image: np.ndarray):
        return Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
