import json
import os
import random
import re
import shutil
import subprocess
from threading import Thread
import time
from PySide6.QtWidgets import (
    QListWidget,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QPushButton,
    QHBoxLayout,
    QLineEdit,
    QListWidgetItem,
    QLabel,
    QTextEdit,
    QGridLayout,
    QMessageBox,
)
from PySide6.QtCore import Signal, QRect, Qt, QSize
from PySide6.QtGui import QPixmap, QPainter, QPen, qRgb, QTextCharFormat, QTextCursor
from PIL import Image
import cv2
import numpy as np
import uuid

from src.widgets.label import Label
from src.widgets.image import Image as ImageView

if not os.path.exists("scripts"):
    os.mkdir("scripts")


def run_cmd(command):
    try:
        output = subprocess.check_output(command, shell=True, stderr=subprocess.STDOUT)
        return output.decode().encode("utf-8").decode("utf-8")
    except subprocess.CalledProcessError as e:
        return e.output.decode().encode("utf-8").decode("utf-8")


tasks = []
RED = qRgb(255, 0, 0)


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


class ScriptRunner(QMainWindow):
    add_cmd_out_signal = Signal(str)
    update_cmd_out_signal = Signal()
    on_close = Signal()
    import_script_signal = Signal(str)
    close_import_script_runner_signal = Signal()

    def __init__(self, dir, address, name, *args, **kwargs):
        self.dir = dir
        self.address = address
        super().__init__(*args, **kwargs)
        self.setWindowTitle(f"运行 {address} {name}")  # 设置窗口标题
        self.resize(500, 600)  # 设置窗口大小
        self.cmd_out = QTextEdit()
        self.cmd_out.setReadOnly(True)
        self.setCentralWidget(self.cmd_out)
        self.cmd_out_list = []
        with open(f"{self.dir}/index.txt", "r+", encoding="utf-8") as f:
            self.script = f.read().split("\n")
        self.variable = {}
        self.add_cmd_out_signal.connect(self.add_cmd_out)
        self.update_cmd_out_signal.connect(self.update_cmd_out)
        self.import_script_signal.connect(self.import_script)
        self.close_import_script_runner_signal.connect(self.close_import_script_runner)
        self.closed = False
        self.th = None
        self.import_script_runner = None
        self.end = False

    def set_cmd_out_color(self):
        cursor = self.cmd_out.textCursor()
        self.cmd_out.setFocus()
        count = 0
        for cmd in self.cmd_out_list:
            fmt = QTextCharFormat()
            if cmd.startswith("INFO"):
                fmt.setForeground(Qt.GlobalColor.gray)
            elif cmd.startswith("ERROR"):
                fmt.setForeground(Qt.GlobalColor.red)
            elif cmd.startswith("WARN"):
                fmt.setForeground(Qt.GlobalColor.yellow)
            elif cmd.startswith("LOG"):
                fmt.setForeground(Qt.GlobalColor.blue)
            else:
                fmt.setForeground(Qt.GlobalColor.black)
            cursor.setPosition(count, QTextCursor.MoveMode.MoveAnchor)
            count = count + len(cmd)
            cursor.setPosition(count, QTextCursor.MoveMode.KeepAnchor)
            cursor.mergeCharFormat(fmt)
            self.cmd_out.mergeCurrentCharFormat(fmt)
            count += 1

    def update_cmd_out(self):
        if self.cmd_out_list.__len__() > 100:
            self.cmd_out_list = self.cmd_out_list[-100:]
        self.cmd_out.setText("\n".join(self.cmd_out_list))
        bar = self.cmd_out.verticalScrollBar()
        bar.setValue(bar.maximum())
        self.set_cmd_out_color()

    def add_cmd_out(self, cmd):
        self.cmd_out_list.append(cmd)
        if self.cmd_out_list.__len__() > 100:
            self.cmd_out_list.pop(0)
        self.cmd_out.setText("\n".join(self.cmd_out_list))
        bar = self.cmd_out.verticalScrollBar()
        bar.setValue(bar.maximum())
        self.set_cmd_out_color()

    def make_cmd(self, cmd):
        return f"adb -s {self.address} {cmd}"

    def cut_image(self):
        if not os.path.exists(self.dir + "/temp"):
            os.mkdir(self.dir + "/temp")
        id = uuid.uuid4()
        run_cmd(self.make_cmd("shell screencap -p /sdcard/screenshot.png"))
        run_cmd(
            self.make_cmd(f"pull /sdcard/screenshot.png {self.dir}/temp/image{id}.png")
        )
        image = Image.open(f"{self.dir}/temp/image{id}.png")
        return image, f"{self.dir}/temp/image{id}.png"

    def pillow_to_cv2(self, image: Image):
        return cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)

    def cv2_to_pillow(self, image: np.ndarray):
        return Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))

    def find_image(self, name):
        big_image, temp_path = self.cut_image()
        big_image = self.pillow_to_cv2(big_image)
        small_image = self.pillow_to_cv2(Image.open(f"{self.dir}/images/{name}"))
        result = cv2.matchTemplate(big_image, small_image, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
        os.remove(temp_path)
        if max_val > 0.95:
            x, y = max_loc
            x += small_image.shape[1] // 2
            y += small_image.shape[0] // 2
            return [x, y]  # 返回最佳匹配左上角坐标
        return None

    def back(self):
        run_cmd(self.make_cmd("shell input keyevent 4"))

    def home(self):
        run_cmd(self.make_cmd("shell input keyevent 3"))

    def start_app(self, package):
        res = run_cmd(self.make_cmd("shell ps"))
        if not package in res:
            run_cmd(
                self.make_cmd(
                    f"shell monkey -p {package} -c android.intent.category.LAUNCHER 1"
                )
            )

    def start(self):
        self.th = Thread(target=self.run)
        tasks.append(self.th)
        self.th.start()

    def closeEvent(self, event):
        self.closed = True
        self.on_close.emit()
        return super().closeEvent(event)

    def get_tag(self, tag, line):
        if tag == "CONTINU":
            return line
        if tag == "END":
            return -2
        for i, cmd in enumerate(self.script):
            cmd = re.sub(r"\s+", " ", cmd)
            cmd = cmd.strip()
            cmd = cmd.lstrip()
            if cmd == f"TAG {tag}":
                return i
        return -3

    def is_num(self, s):
        try:
            float(s)
            return True
        except ValueError:
            return False

    def close_import_script_runner(self):
        if self.import_script_runner is not None:
            self.import_script_runner.close()

    def import_script(self, name):
        try:
            self.import_script_runner = ScriptRunner(
                f"scripts/{name}", self.address, name
            )
            self.import_script_runner.start()
            self.import_script_runner.show()
        except Exception as e:
            HomeWindow.add_cmd_out(self, str(e))

    def run(self):
        line = 0
        self.add_cmd_out_signal.emit(f"开始")
        running_import = False
        while True:
            if line == -1:
                break
            if line == -2:
                self.add_cmd_out_signal.emit(f"ERROR [未知TAG]")
                break
            if self.closed:
                break
            try:
                cmd = self.script[line]
            except:
                break
            try:
                if running_import:
                    if self.import_script_runner and self.import_script_runner.end:
                        self.cmd_out_list += self.import_script_runner.cmd_out_list[
                            1:-1
                        ]
                        self.update_cmd_out_signal.emit()
                        self.close_import_script_runner_signal.emit()
                        self.import_script_runner = None
                        running_import = False
                    continue
                if cmd.startswith("#"):
                    line += 1
                    continue
                cmd = re.sub(r"\s+", " ", cmd)
                cmd = cmd.strip()
                cmd = cmd.lstrip()
                if cmd == "" or cmd == " ":
                    line += 1
                    continue
                args = cmd.split(" ")
                if args[0] == "IMPORT":
                    running_import = True
                    self.import_script_signal.emit(args[1])
                elif args[0] == "START":
                    self.start_app(args[1])
                    self.add_cmd_out_signal.emit(f"INFO {line}:{cmd} [启动{args[1]}]")
                elif args[0] == "FIND_IMAGE":
                    pos = self.find_image(args[1])
                    if pos is None:
                        try:
                            ord_line = line
                            line = self.get_tag(args[4], line)
                            self.add_cmd_out_signal.emit(
                                f"INFO {ord_line}:{cmd} [跳转{line}]"
                            )
                        except:
                            self.add_cmd_out_signal.emit(
                                f"ERROR {line}:{cmd} [找不到目标图标{args[1]}]"
                            )
                        line += 1
                        continue
                    self.variable[args[2]] = pos
                    self.add_cmd_out_signal.emit(
                        f"INFO {line}:{cmd} [找到图片({pos[0]},{pos[1]})]"
                    )
                    try:
                        ord_line = line
                        line = self.get_tag(args[3], line)
                        self.add_cmd_out_signal.emit(
                            f"INFO {ord_line}:{cmd} [跳转{line}]"
                        )
                    except:
                        pass
                elif args[0] == "CLICK":
                    if args.__len__() == 2:
                        x, y = self.variable[args[1]]
                    else:
                        x, y = float(args[1]), float(args[2])
                    x = random_xy(x)
                    y = random_xy(y)
                    run_cmd(self.make_cmd(f"shell input tap {x} {y}"))
                    self.add_cmd_out_signal.emit(
                        f"INFO {line}:{cmd} [点击坐标({x},{y})]"
                    )
                elif args[0] == "SWIP":
                    x1, y1 = self.variable[args[1]]
                    x2, y2 = self.variable[args[2]]
                    x1 = random_xy(x1)
                    y1 = random_xy(y1)
                    x2 = random_xy(x2)
                    y2 = random_xy(y2)
                    run_cmd(
                        self.make_cmd(
                            f"shell input swipe {x1} {y1} {x2} {y2} {random.randint(5,9)}00"
                        )
                    )
                    self.add_cmd_out_signal.emit(
                        f"INFO {line}:{cmd} [滑动坐标({x1},{y1})到({x2},{y2})]"
                    )
                elif args[0] in ["LOG", "ERROR", "WARN", "INFO"]:
                    value = args[1]
                    if args[1] in self.variable.keys():
                        value = self.variable[args[1]]
                    self.add_cmd_out_signal.emit(f"{args[0]} {value}")
                elif args[0] == "GO":
                    ord_line = line
                    line = self.get_tag(args[1], line)
                    self.add_cmd_out_signal.emit(f"INFO {ord_line}:{cmd} [跳转{line}]")
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
                        line = self.get_tag(args[4], line)
                    else:
                        line = self.get_tag(args[5], line)
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
                        self.add_cmd_out_signal.emit(
                            f"INFO {line}:{cmd} [计算结果{self.variable[args[5]]}]"
                        )
                    elif args[1] == "XY":
                        xy = [self.variable[args[2]][0], self.variable[args[2]][1]]
                        if args[3] == "x":
                            i = 0
                        elif args[3] == "y":
                            i = 1
                        else:
                            self.add_cmd_out_signal.emit(
                                f"ERROR {line}:{cmd} [未知变量{args[3]}]"
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
                        self.add_cmd_out_signal.emit(
                            f"INFO {line}:{cmd} [计算结果{xy}]"
                        )
                elif args[0] == "BACK":
                    self.back()
                    self.add_cmd_out_signal.emit(f"INFO {line}:{cmd} [返回]")
                elif args[0] == "HOME":
                    self.home()
                    self.add_cmd_out_signal.emit(f"INFO {line}:{cmd} [回到主页]")
                elif args[0] == "WAIT":
                    s_t = random_time(float(args[1]))
                    self.add_cmd_out_signal.emit(f"INFO {line}:{cmd} [等待{s_t}秒]")
                    time.sleep(s_t)
                elif args[0] == "END":
                    break
            except Exception as e:
                self.add_cmd_out_signal.emit(f"{line}:{cmd} [{str(e)}]")
                HomeWindow.add_cmd_out(self, str(e))
                break
            line += 1
        self.add_cmd_out_signal.emit(f"结束")
        self.end = True


# 创建一个主窗口类，继承自 QMainWindow
class AddScriptWindow(QMainWindow):
    added = Signal()

    def __init__(self):
        super().__init__()  # 调用父类 QMainWindow 的初始化方法
        self.resize(200, 100)  # 设置窗口大小
        self.setWindowTitle("新建")  # 设置窗口标题
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        h_box = QHBoxLayout()
        central_widget.setLayout(h_box)
        self.name = QLineEdit()
        h_box.addWidget(self.name)
        ok = QPushButton("确定")
        h_box.addWidget(ok)
        ok.clicked.connect(self.on_click_ok)

    def on_click_ok(self):
        name = self.name.text()
        os.mkdir(f"scripts/{name}")
        open(f"scripts/{name}/index.txt", "w+", encoding="utf-8").close()
        self.name.clear()
        self.close()
        self.added.emit()


class Drawing(QWidget):
    def __init__(self, parent=None):
        super(Drawing, self).__init__(parent)
        self.resize(600, 400)
        self.setWindowTitle("拖拽绘制矩形")
        self.rect = None

    # 重写绘制函数
    def paintEvent(self, event):
        # 初始化绘图工具
        qp = QPainter()
        # 开始在窗口绘制
        qp.begin(self)
        # 自定义画点方法
        if self.rect:
            self.drawRect(qp)
        # 结束在窗口的绘制
        qp.end()

    def drawRect(self, qp: QPainter):
        # 创建红色，宽度为4像素的画笔
        pen = QPen()
        pen.setColor(RED)
        pen.setWidth(4)
        qp.setPen(pen)
        qp.drawRect(*self.rect)

    # 重写三个时间处理
    def mousePressEvent(self, event):
        print("mouse press")
        self.rect = (event.x(), event.y(), 0, 0)

    def mouseReleaseEvent(self, event):
        print("mouse release")

    def mouseMoveEvent(self, event):
        start_x, start_y = self.rect[0:2]
        self.rect = (start_x, start_y, event.x() - start_x, event.y() - start_y)
        self.update()


class GetXYWindow(QMainWindow):
    getted = Signal(list)

    def __init__(self, dir,address):
        self.dir = dir
        self.address = address
        super().__init__()  # 调用父类 QMainWindow 的初始化方法
        if not os.path.exists(dir + "/temp"):
            os.mkdir(dir + "/temp")
        id = os.listdir(dir + "/temp").__len__()
        run_cmd(self.make_cmd("shell screencap -p /sdcard/screenshot.png"))
        run_cmd(self.make_cmd(f"pull /sdcard/screenshot.png {dir}/temp/image{id}.png"))
        time.sleep(1)
        self.resize(200, 100)  # 设置窗口大小
        self.setWindowTitle("取点")  # 设置窗口标题
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        self.image = QPixmap(f"{dir}/temp/image{id}.png")
        os.remove(f"{dir}/temp/image{id}.png")
        self.show_image = Label()
        self.show_image.setPixmap(self.image)
        self.show_image.setFixedSize(self.image.size())
        v_box = QGridLayout()
        central_widget.setLayout(v_box)
        v_box.addWidget(self.show_image, 0, 0)
        self.show_image.clicked.connect(self.on_click)
    
    def make_cmd(self, cmd):
        if self.address == "":
            return f"adb {cmd}"
        return f"adb -s {self.address} {cmd}"

    def on_click(self, event):
        xy = [event.x(), event.y()]
        self.getted.emit(xy)
        self.close()


class CutImageWindow(QMainWindow):
    def __init__(self, dir,address):
        self.dir = dir
        self.address = address
        super().__init__()  # 调用父类 QMainWindow 的初始化方法
        if not os.path.exists(dir + "/temp"):
            os.mkdir(dir + "/temp")
        id = os.listdir(dir + "/temp").__len__()
        run_cmd(self.make_cmd("shell screencap -p /sdcard/screenshot.png"))
        run_cmd(self.make_cmd(f"pull /sdcard/screenshot.png {dir}/temp/image{id}.png"))
        time.sleep(1)
        self.resize(200, 100)  # 设置窗口大小
        self.setWindowTitle("截图")  # 设置窗口标题
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        self.show_image = ImageView(f"{dir}/temp/image{id}.png")
        os.remove(f"{dir}/temp/image{id}.png")
        # self.show_image.setPixmap(self.image)
        # self.show_image.setFixedSize(self.image.size())
        v_box = QGridLayout()
        central_widget.setLayout(v_box)
        self.cut_box = Drawing()
        self.cut_box.setFixedSize(self.show_image.image.size())
        v_box.addWidget(self.show_image, 0, 0)
        v_box.addWidget(self.cut_box, 0, 0)
        self.cut_box.raise_()
        ok = QPushButton("确定")
        v_box.addWidget(ok)
        ok.clicked.connect(self.on_click_ok)

    def make_cmd(self, cmd):
        if self.address == "":
            return f"adb {cmd}"
        return f"adb -s {self.address} {cmd}"

    def on_click_ok(self):
        x, y, w, h = self.cut_box.rect
        rect = QRect(x, y, w, h)
        if (
            rect.x() + rect.width() > self.show_image.image.width()
            or rect.y() + rect.height() > self.show_image.image.height()
        ):
            print("错误：截取区域超出图像范围")
            return

        # 截取子图像
        cropped_pixmap = self.show_image.image.copy(rect)

        # 保存截图（示例路径）
        if not os.path.exists(self.dir + "/images"):
            os.mkdir(self.dir + "/images")
        id = os.listdir(self.dir + "/images").__len__()
        save_path = self.dir + f"/images/image{id}.png"
        cropped_pixmap.save(save_path)
        self.update_image_list()
        self.close()

    def update_image_list(self):
        pass


class ScriptEditoImagesWidgetItem(QListWidgetItem):
    def __init__(self, text, dir, parent=None):
        super().__init__(parent)
        self.setText(text)
        self.widget = QWidget()
        self.layout = QHBoxLayout(self.widget)
        self.layout.setContentsMargins(0, 0, 0, 0)
        image = ImageView(f"{dir}/images/{text}")
        image.setSize(100, 100)
        self.name = QLineEdit(text)
        self.name.setFixedSize(QSize(80, 20))
        self.change_name_button = QPushButton("修改名称")
        self.click_button = QPushButton("点击图片")
        self.add_button = QPushButton("寻找图片")
        self.delete_button = QPushButton("删除图片")
        self.layout.addWidget(image)
        self.layout.addWidget(self.name)
        self.layout.addWidget(self.change_name_button)
        self.layout.addWidget(self.add_button)
        self.layout.addWidget(self.click_button)
        self.layout.addWidget(self.delete_button)


class ScriptEditorWindow(QMainWindow):
    def __init__(self, dir):
        super().__init__()  # 调用父类 QMainWindow 的初始化方法
        self.resize(1200, 600)  # 设置窗口大小
        self.setWindowTitle("编辑")
        self.dir = dir
        self.file = dir + "/index.txt"
        self.content = open(self.file, "r+", encoding="utf-8").read()
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        h_box = QHBoxLayout()
        central_widget.setLayout(h_box)

        # 左边栏
        v_box = QVBoxLayout()
        h_box.addLayout(v_box)
        # TAG XXX | 一个标签
        # GOTO XXX | 跳转到 XXX
        # FIND_IMAGE XXX argname 3 | 找到图片 XXX 超时3秒
        # FIND_TEXT XXX argname 3 | 找到文本 XXX
        # CLICK argname | 点击 argname
        # SEND_TEXT "ssdasda" | 输入 XXX
        # WAIT 3 | 等待 3 秒
        HomeWindow.check_adb()
        self.adb_address = QLineEdit(
            HomeWindow.adb_devices[0] if len(HomeWindow.adb_devices) > 0 else ""
        )
        v_box.addWidget(self.adb_address)
        click_xy_box = QVBoxLayout()
        v_box.addLayout(click_xy_box)
        
        click_xy_get_box = QHBoxLayout()
        click_xy_box.addLayout(click_xy_get_box)
        click_xy_get_button = QPushButton("获取坐标")
        click_xy_get_box.addWidget(click_xy_get_button)
        click_xy_get_button.clicked.connect(self.on_click_click_xy_get)
        

        click_xy_input_box = QHBoxLayout()
        click_xy_label = QLabel("点击坐标")
        click_xy_box.addWidget(click_xy_label)
        click_xy_box.addLayout(click_xy_input_box)
        click_xy_x_label = QLabel("x:")
        click_xy_y_label = QLabel("y:")
        self.click_xy_x = QLineEdit()
        self.click_xy_y = QLineEdit()
        click_xy_input_box.addWidget(click_xy_x_label)
        click_xy_input_box.addWidget(self.click_xy_x)
        click_xy_input_box.addWidget(click_xy_y_label)
        click_xy_input_box.addWidget(self.click_xy_y)
        click_xy_button = QPushButton("插入")
        click_xy_input_box.addWidget(click_xy_button)
        click_xy_button.clicked.connect(self.on_click_click_xy)

        add_image_box = QHBoxLayout()
        v_box.addLayout(add_image_box)
        add_image_label = QLabel("点击图片")
        add_image_box.addWidget(add_image_label)
        add_image_button = QPushButton("截图")
        add_image_box.addWidget(add_image_button)
        self.image_list = QListWidget()
        self.image_list.setStyleSheet(
            """
            QListWidget { 
                height: 200px; 
            }
            QListWidget::item {
                padding: 5px;height:40px; 
            }
            """
        )
        v_box.addWidget(self.image_list)
        self.update_image_list()

        save_button = QPushButton("保存")
        v_box.addWidget(save_button)
        save_button.clicked.connect(self.on_click_save)

        # 编辑器
        self.editor = QTextEdit()
        self.editor.setText(self.content)
        self.editor.setFixedSize(QSize(600, 600))
        h_box.addWidget(self.editor)
        self.editor.setStyleSheet("QTextEdit { width: 500px; }")
        add_image_button.clicked.connect(self.on_click_add_image)

    def on_click_save(self):
        with open(self.file, "w+", encoding="utf-8") as f:
            self.content = self.editor.toPlainText()
            f.write(self.content)
        msg = QMessageBox()
        msg.setText("保存成功")
        msg.exec_()

    def on_click_click_xy(self):
        x = self.click_xy_x.text()
        y = self.click_xy_y.text()
        if x == "" or y == "":
            msg = QMessageBox()
            msg.setText("请输入x,y坐标")
            msg.exec_()
            return
        self.editor.setText(self.editor.toPlainText() + f"\nCLICK {x} {y}")

    def on_click_add_image(self):
        self.cut_image_window = CutImageWindow(self.dir,self.adb_address.text())
        self.cut_image_window.update_image_list = self.update_image_list
        self.cut_image_window.show()

    def on_getted(self, xy):
        self.click_xy_x.setText(str(xy[0]))
        self.click_xy_y.setText(str(xy[1]))

    def on_click_click_xy_get(self):
        self.get_xy_window = GetXYWindow(self.dir,self.adb_address.text())
        self.get_xy_window.getted.connect(self.on_getted)
        self.get_xy_window.show()

    def on_click_image_list_add_image(self, item):
        def func():
            file_name = item.text()
            name = file_name.replace(".png", "")
            self.editor.setText(
                self.editor.toPlainText() + f"\nFIND_IMAGE {file_name} {name}"
            )

        return func

    def on_click_image_list_delete_image(self, item):
        def func():
            path = self.dir + "/images/" + item.text()
            os.remove(path)
            self.update_image_list()

        return func

    def on_click_image_list_click_image(self, item):
        def func():
            file_name = item.text()
            name = file_name.replace(".png", "")
            self.editor.setText(self.editor.toPlainText() + f"\nCLICK {name}")

        return func

    def on_click_change_name(self, item):
        def func():
            path = self.dir + "/images/" + item.text()
            new = self.dir + "/images/" + item.name.text()
            item.setText(item.name.text())
            os.rename(path, new)

        return func

    def update_image_list(self):
        try:
            self.image_list.clear()
            for item in [
                ScriptEditoImagesWidgetItem(name, self.dir)
                for name in os.listdir(self.dir + "/images") or []
            ]:
                item.change_name_button.clicked.connect(self.on_click_change_name(item))
                item.click_button.clicked.connect(
                    self.on_click_image_list_click_image(item)
                )
                item.add_button.clicked.connect(
                    self.on_click_image_list_add_image(item)
                )
                item.delete_button.clicked.connect(
                    self.on_click_image_list_delete_image(item)
                )
                self.image_list.addItem(item)
                self.image_list.setItemWidget(item, item.widget)
        except:
            pass


class ScriptRunChooseDevice(QMainWindow):
    def __init__(self, dir, name):
        self.name = name
        self.sr = None
        super().__init__()
        self.dir = dir
        self.resize(800, 600)
        self.setWindowTitle("选择设备")
        self.device_list = QListWidget()
        self.device_list.setStyleSheet(
            "QListWidget::item { padding: 5px;height:40px; }"
        )
        self.device_list.itemDoubleClicked.connect(self.on_click_device_list)
        HomeWindow.check_adb()
        for device in HomeWindow.adb_devices:
            self.device_list.addItem(device)
        self.setCentralWidget(self.device_list)

    def on_click_device_list(self, item):
        try:
            self.sr = ScriptRunner(self.dir, item.text(), self.name)
            self.sr.on_close.connect(self.on_sr_close)
            self.close()
            self.sr.show()
            self.sr.start()
        except Exception as e:
            HomeWindow.add_cmd_out(self, str(e))

    def childEvent(self, event):
        if self.sr is None:
            self.on_sr_close()
        return super().childEvent(event)

    def on_sr_close(self):
        pass


class ScriptListWidgetItem(QListWidgetItem):
    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.setText(text)
        self.widget = QWidget()
        self.layout = QHBoxLayout(self.widget)
        self.layout.setContentsMargins(0, 0, 0, 0)
        name = QLabel(text)
        run_button = QPushButton("运行")
        editor_button = QPushButton("编辑")
        delete_button = QPushButton("删除")
        self.layout.addWidget(name)
        self.layout.addWidget(run_button)
        self.layout.addWidget(editor_button)
        self.layout.addWidget(delete_button)
        run_button.clicked.connect(self.on_click_run)
        editor_button.clicked.connect(self.on_click_edit)
        delete_button.clicked.connect(self.on_click_delete)
        self.srcds = []

    def on_srcd_close(self, srcd):
        def func():
            if srcd in self.srcds:
                self.srcds.remove(srcd)

        return func

    def on_click_run(self):
        HomeWindow.check_adb()
        if len(HomeWindow.adb_devices) == 0:
            return HomeWindow.add_cmd_out(self, "没有设备")
        try:
            dir = f"scripts/{self.text()}"
            srcd = ScriptRunChooseDevice(dir, self.text())
            srcd.on_sr_close = self.on_srcd_close(srcd)
            srcd.show()
            self.srcds.append(srcd)
        except Exception as e:
            HomeWindow.add_cmd_out(self, str(e))

    def on_click_delete(self):
        dir = f"scripts/{self.text()}"
        shutil.rmtree(dir)
        time.sleep(1)
        self.update_script_list()

    def on_click_edit(self):
        self.editor_window = ScriptEditorWindow(f"scripts/{self.text()}")
        self.editor_window.show()

    def update_script_list():
        pass


class HomeWindow(QMainWindow):
    cmd_out_list = []
    adb_devices = []
    update_cmd_out_signal = Signal()

    @classmethod
    def add_cmd_out(cls, obj: object, cmd_out):
        cls.cmd_out_list.append(f"{obj.__class__.__name__} {cmd_out}")

    def __init__(self):
        super().__init__()  # 调用父类 QMainWindow 的初始化方法
        self.resize(800, 600)  # 设置窗口大小
        self.setWindowTitle("easy click")  # 设置窗口标题
        self.add_script_window = AddScriptWindow()
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)

        # 创建垂直布局管理器
        vbox_layout = QVBoxLayout()
        # 将布局设置为中央控件的布局
        central_widget.setLayout(vbox_layout)

        add_script = QPushButton("新建")
        vbox_layout.addWidget(add_script)
        self.script_list = QListWidget()
        self.script_list.setStyleSheet(
            "QListWidget::item { padding: 5px;height:40px; }"
        )
        vbox_layout.addWidget(self.script_list)
        connect_adb_box = QHBoxLayout()
        vbox_layout.addLayout(connect_adb_box)
        input_label = QLabel("输入设备地址")
        connect_adb_box.addWidget(input_label)
        self.input_address = QLineEdit("127.0.0.1:7555")
        connect_adb_box.addWidget(self.input_address)
        connect_adb_button = QPushButton("连接")
        connect_adb_box.addWidget(connect_adb_button)
        connect_adb_button.clicked.connect(self.connect_adb)
        add_script.clicked.connect(self.on_click_add_script)
        self.add_script_window.added.connect(self.on_add_script)
        self.update_script_list()
        self.cmd_out = QTextEdit()
        self.cmd_out.setReadOnly(True)
        self.cmd_out.setFixedHeight(200)
        vbox_layout.addWidget(self.cmd_out)
        clear_cmd_out = QPushButton("清空")
        vbox_layout.addWidget(clear_cmd_out)
        about_box = QHBoxLayout()
        vbox_layout.addLayout(about_box)
        about_name = QLabel("声明：本软件仅供学习交流，不收取任何费用！！！！ by: 杳末钎散 ")
        about_box.addWidget(about_name)
        connect = QLineEdit("QQ: 1613921123 Github: https://github.com/YSASM/easy-click")
        connect.setReadOnly(True)
        about_box.addWidget(connect)
        clear_cmd_out.clicked.connect(self.clear_cmd_out)
        self.update_cmd_out_signal.connect(self.update_cmd_out)
        self.start_reflash_cmd_out()
        HomeWindow.check_adb()

    def connect_adb(self):
        res = run_cmd("adb connect " + self.input_address.text())
        self.add_cmd_out(self, res)
        HomeWindow.check_adb()

    def clear_cmd_out(self):
        self.cmd_out_list.clear()

    @classmethod
    def check_adb(self):
        self.adb_devices.clear()
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
            self.adb_devices.append(device)
            HomeWindow.add_cmd_out(self, f"检测到设备 {device}")

    def update_cmd_out(self):
        info = "\n".join(self.cmd_out_list)
        if info != self.cmd_out.toPlainText():
            self.cmd_out.setText(info)

    def reflash_cmd_out(self):
        while True:
            self.update_cmd_out_signal.emit()
            time.sleep(1)

    def start_reflash_cmd_out(self):
        self.reflash_thread = Thread(target=self.reflash_cmd_out)
        self.reflash_thread.setDaemon(True)
        self.reflash_thread.start()

    def get_tasks(self):
        return tasks

    def remove_task(self, task: Thread):
        tasks.remove(task)

    def on_click_add_script(self):
        self.add_script_window.show()

    def on_add_script(self):
        self.update_script_list()

    def update_script_list(self):
        self.script_list.clear()
        for item in [ScriptListWidgetItem(name) for name in os.listdir("scripts")]:
            item.update_script_list = self.update_script_list
            self.script_list.addItem(item)
            self.script_list.setItemWidget(item, item.widget)
