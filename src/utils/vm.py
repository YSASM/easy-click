import os
import re
from threading import Thread
import time
from PIL import Image
import cv2
import traceback
from src.utils import BaseControl, Bean, random_xy
from src.utils.adb import Adb
from pathlib import Path
import shutil
from src.utils.uiautomator2Manger import Uiautomator2,u2


class Vm(Thread):
    def __init__(self, page, dir, address: BaseControl, code: list[str]):
        super().__init__(daemon=True)
        self.code = [""] + code
        self.page = page
        self.killed = False
        self.variable = {}
        self.end = False
        assets = os.path.join(Path(u2.__file__).parent,"assets")
        if not os.path.exists(assets):
            shutil.copytree("lib/uiautomator2",assets)
        else:
            if os.listdir(assets) != os.listdir("lib/uiautomator2"):
                shutil.rmtree(assets)
                shutil.copytree("lib/uiautomator2",assets)
        self.control = Uiautomator2(address)
        err = self.control.connect()
        if err is not None :
            self.add_cmd_out(str(err))
            raise Exception(f"链接失败{str(err)}")
        
        self.add_cmd_out(f"INFO {self.control.d.info}")
        self.adb = Adb(address)
        self.address = address
        self.dir = dir
        for index, cmd in enumerate(self.code):
            cmd = re.sub(r"\s+", " ", cmd)
            cmd = cmd.strip()
            cmd = cmd.lstrip()
            if cmd.startswith("#") or cmd == " ":
                cmd = ""
                continue
            self.code[index] = cmd
        self.code = list(map(lambda x: x.split(" "), self.code))

        self.tags = {}
        for line, args in enumerate(self.code):
            if args[0] == "TAG":
                self.tags[args[1]] = line

        self.images = {}
        for name in os.listdir(f"{dir}/images"):
            image = self.control.pillow_to_cv2(Image.open(f"{dir}/images/{name}"))
            self.images[name] = image

    def kill(self):
        self.killed = True

    def add_cmd_out(self, cmd):
        self.page.cmd_out_list.append(cmd)
        self.page.update_cmd_out_signal.emit()

    def find_image(self, name):
        big_image = self.control.screenshot()
        small_image = self.images[name]
        result = cv2.matchTemplate(big_image, small_image, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
        if max_val > 0.95:
            x, y = max_loc
            x += small_image.shape[1] // 2
            y += small_image.shape[0] // 2
            return [x, y]  # 返回最佳匹配左上角坐标
        return None

    def has_images(self, names):
        big_image = self.control.screenshot()
        for name in names:
            small_image = self.images[name]
            result = cv2.matchTemplate(big_image, small_image, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
            if max_val < 0.95:
                return False
        return True

    def wait_image(self, name, time_out=5):
        count = 0
        while True:
            res = self.find_image(name)
            if res is not None:
                return res
            emd_time = int(time.time())
            if count > time_out:
                return None
            count += 1

    def back(self):
        self.adb.cmd("shell input keyevent 4")

    def home(self):
        self.adb.cmd("shell input keyevent 3")

    def start_app(self, package):
        res = self.adb.cmd("shell ps")
        if not package in res:
            self.adb.cmd(
                f"shell monkey -p {package} -c android.intent.category.LAUNCHER 1"
            )

    def get_tag(self, tag, line, pos=None):
        if tag == "CONTINU" or tag is None:
            return line
        if tag == "END":
            return -2
        if tag == "CLICK":
            x, y = pos
            x = random_xy(x)
            y = random_xy(y)
            self.control.click([x, y])
            self.add_cmd_out(f"INFO [点击坐标({x},{y})]")
            return line
        return self.tags.get(tag, -3)

    def is_num(self, s):
        try:
            float(s)
            return True
        except ValueError:
            return False

    def import_script(self, name):
        try:
            with open(f"scripts/{name}/index.txt", "r+", encoding="utf-8") as f:
                code = f.read().split("\n")
            self.import_script_runner = Vm(
                self.page, f"scripts/{name}", self.address, code
            )
            self.import_script_runner.start()
            self.import_script_runner.join()
        except Exception as e:
            Bean.cmd_out_list.append(str(e))

    def getArg(self, args, index):
        try:
            return args[index]
        except:
            return None

    def run(self):
        script_name = self.dir.replace("/","\\").split("\\")[-1]
        self.end = False
        line = 0
        self.add_cmd_out(f"LOG 开始{script_name}")
        while True:
            if line == -1:
                break
            if line == -2:
                self.add_cmd_out(f"ERROR [未知TAG]")
                break
            if self.killed:
                break
            try:
                args = self.code[line]
            except:
                break
            try:
                cmd_name = self.getArg(args, 0)
                if cmd_name == "P":
                    args = args[1:]
                cmd_name = self.getArg(args, 0)
                if cmd_name == "":
                    line += 1
                    continue
                if cmd_name == "IMPORT":
                    self.import_script(args[1])
                elif cmd_name == "START":
                    self.start_app(args[1])
                    self.add_cmd_out(f"INFO [启动{args[1]}]")

                elif cmd_name == "HAS_IMAGE":
                    # HAS_IMAGE xx xx xx t1 t2
                    names = []
                    tags = []
                    for arg in args[1:]:
                        if ".png" in arg:
                            names.append(arg)
                        else:
                            tags.append(arg)
                    yes = self.getArg(tags, 0)
                    no = self.getArg(tags, 1)
                    if self.has_images(names):
                        line = self.get_tag(yes, line, pos)
                    else:
                        line = self.get_tag(no, line)
                elif cmd_name == "WAIT_IMAGE":
                    # WAIT_IMAGE xxx xxx t1 t2
                    # WAIT_IMAGE 5 xxx xxx t1 t2
                    if self.is_num(self.getArg(args, 1)):
                        time_out = float(self.getArg(args, 1))
                        name = self.getArg(args, 2)
                        var = self.getArg(args, 3)
                        yes = self.getArg(args, 4)
                        no = self.getArg(args, 5)
                    else:
                        time_out = 5
                        name = self.getArg(args, 1)
                        var = self.getArg(args, 2)
                        yes = self.getArg(args, 3)
                        no = self.getArg(args, 4)

                    pos = self.wait_image(name, time_out)
                    if pos:
                        self.variable[var] = pos
                        self.add_cmd_out(
                            f"INFO {line}:{' '.join(args)} [找到图片({pos[0]},{pos[1]})]"
                        )
                        line = self.get_tag(yes, line, pos)
                    else:
                        # self.add_cmd_out(
                        #     f"ERROR {line}:{' '.join(args)} [找不到目标图标{name}]"
                        # )
                        line = self.get_tag(no, line)

                elif args[0] == "FIND_IMAGE":
                    name = self.getArg(args, 1)
                    var = self.getArg(args, 2)
                    yes = self.getArg(args, 3)
                    no = self.getArg(args, 4)

                    pos = self.find_image(name)
                    if pos:
                        self.variable[var] = pos
                        self.add_cmd_out(
                            f"INFO {line}:{' '.join(args)} [找到图片({pos[0]},{pos[1]})]"
                        )
                        line = self.get_tag(yes, line, pos)
                    else:
                        # self.add_cmd_out(
                        #     f"ERROR {line}:{' '.join(args)} [找不到目标图标{name}]"
                        # )
                        line = self.get_tag(no, line)

                elif args[0] == "CLICK":
                    try:
                        if args.__len__() == 2:
                            x, y = self.variable[args[1]]
                        else:
                            x, y = float(args[1]), float(args[2])
                        x = random_xy(x)
                        y = random_xy(y)
                        self.control.click([x, y])
                        self.add_cmd_out(
                            f"INFO {line}:{' '.join(args)} [点击坐标({x},{y})]"
                        )
                    except Exception as e:
                        f"ERROR {line}:{' '.join(args)} [{str(e)}]"
                elif args[0] == "SWIP":
                    x1, y1 = self.variable[args[1]]
                    x2, y2 = self.variable[args[2]]
                    x1 = random_xy(x1)
                    y1 = random_xy(y1)
                    x2 = random_xy(x2)
                    y2 = random_xy(y2)
                    try:
                        self.control.swiper([x1, y1], [x2, y2])
                    except Exception as e:
                        pass
                    self.add_cmd_out(
                        f"INFO {line}:{' '.join(args)} [滑动坐标({x1},{y1})到({x2},{y2})]"
                    )
                elif args[0] in ["LOG", "ERROR", "WARN", "INFO"]:
                    value = args[1]
                    if args[1] in self.variable.keys():
                        value = self.variable[args[1]]
                    self.add_cmd_out(f"{args[0]} {value}")
                elif args[0] == "GO":
                    line = self.get_tag(args[1], line)
                    self.add_cmd_out(f"INFO {line}:{' '.join(args)} [跳转{line}]")
                elif args[0] == "SET":
                    if args[1] == "VAR":
                        self.variable[args[2]] = float(args[3])
                    elif args[1] == "XY":
                        self.variable[args[2]] = [float(args[3]), float(args[4])]
                elif args[0] == "IF":
                    value1 = (
                        float(args[1])
                        if self.is_num(args[1])
                        else self.variable[args[1]]
                    )
                    value2 = (
                        float(args[3])
                        if self.is_num(args[3])
                        else self.variable[args[3]]
                    )
                    res = False
                    if args[2] == "==":
                        res = value1 == value2
                    elif args[2] == "!=":
                        res = value1 != value2
                    elif args[2] == ">":
                        res = value1 > value2
                    elif args[2] == ">=":
                        res = value1 >= value2
                    elif args[2] == "<":
                        res = value1 < value2
                    elif args[2] == "<=":
                        res = value1 <= value2
                    if res:
                        line = self.get_tag(self.getArg(args, 4), line)
                    else:
                        line = self.get_tag(self.getArg(args, 5), line)
                elif args[0] == "CALC":
                    if args[1] == "VAR":
                        value1 = (
                            float(args[2])
                            if self.is_num(args[2])
                            else self.variable[args[2]]
                        )
                        value2 = (
                            float(args[4])
                            if self.is_num(args[4])
                            else self.variable[args[4]]
                        )
                        if args[3] == "+":
                            self.variable[args[5]] = value1 + value2
                        elif args[3] == "-":
                            self.variable[args[5]] = value1 - value2
                        elif args[3] == "*":
                            self.variable[args[5]] = value1 * value2
                        elif args[3] == "/":
                            self.variable[args[5]] = value1 / value2
                        self.add_cmd_out(
                            f"INFO {line}:{' '.join(args)} [计算结果{self.variable[args[5]]}]"
                        )
                    elif args[1] == "XY":
                        xy = [self.variable[args[2]][0], self.variable[args[2]][1]]
                        if args[3] == "x":
                            i = 0
                        elif args[3] == "y":
                            i = 1
                        else:
                            self.add_cmd_out(
                                f"ERROR {line}:{' '.join(args)} [未知变量{args[3]}]"
                            )
                            break
                        value2 = (
                            float(args[5])
                            if self.is_num(args[5])
                            else self.variable[args[5]]
                        )
                        if args[4] == "+":
                            xy[i] += value2
                        elif args[4] == "-":
                            xy[i] -= value2
                        elif args[4] == "*":
                            xy[i] *= value2
                        elif args[4] == "/":
                            xy[i] /= value2
                        self.variable[args[6]] = xy
                        self.add_cmd_out(f"INFO {line}:{' '.join(args)} [计算结果{xy}]")
                elif args[0] == "BACK":
                    self.back()
                    self.add_cmd_out(f"INFO {line}:{' '.join(args)} [返回]")
                elif args[0] == "HOME":
                    self.home()
                    self.add_cmd_out(f"INFO {line}:{' '.join(args)} [回到主页]")
                elif args[0] == "WAIT":
                    s_t = float(args[1])
                    self.add_cmd_out(f"INFO {line}:{' '.join(args)} [等待{s_t}秒]")
                    time.sleep(s_t)
                elif args[0] == "END":
                    break
            except Exception as e:
                self.add_cmd_out(f"ERROR {line}:{' '.join(args)} [{traceback.format_exc()}]")
                Bean.cmd_out_list.append(str(e))
                break
            line += 1
        self.end = True
        self.add_cmd_out(f"LOG 结束{script_name}")
        if self.page.after_run_close_script:
            self.page.close_self.emit()
