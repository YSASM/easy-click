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
from PySide6.QtCore import Signal, QRect, QThread
from PySide6.QtGui import QPixmap, QPainter, QPen, qRgb
from PIL import Image
import cv2
import numpy as np
import uuid
if not os.path.exists("scripts"):
    os.mkdir("scripts")


def run_cmd(command):
    try:
        output = subprocess.check_output(command, shell=True, stderr=subprocess.STDOUT)
        return output.decode().encode("utf-8").decode("utf-8")
    except subprocess.CalledProcessError as e:
        return e.output.decode().encode("utf-8").decode("utf-8")


tasks = []


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
    on_close = Signal()

    def __init__(self, dir, address, *args, **kwargs):
        self.dir = dir
        self.address = address
        super().__init__(*args, **kwargs)
        self.setWindowTitle("运行")  # 设置窗口标题
        self.resize(500, 600)  # 设置窗口大小
        self.cmd_out = QTextEdit()
        self.cmd_out.setReadOnly(True)
        self.setCentralWidget(self.cmd_out)
        self.cmd_out_list = []
        with open(f"{self.dir}/index.txt", "r+", encoding="utf-8") as f:
            self.script = f.read().split("\n")
        self.xy = {}
        self.add_cmd_out_signal.connect(self.add_cmd_out)
        self.closed = False

    def add_cmd_out(self, cmd):
        self.cmd_out_list.append(cmd)
        self.cmd_out.setText("\n".join(self.cmd_out_list))
        bar = self.cmd_out.verticalScrollBar()
        bar.setValue(bar.maximum())

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
        return image,f"{self.dir}/temp/image{id}.png"

    def pillow_to_cv2(self, image: Image):
        return cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)

    def cv2_to_pillow(self, image: np.ndarray):
        return Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))

    def find_image(self, name):
        big_image,temp_path = self.cut_image()
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

    def start(self):
        th = Thread(target=self.run)
        tasks.append(th)
        th.start()

    def closeEvent(self, event):
        self.closed = True
        self.on_close.emit()
        return super().closeEvent(event)

    def get_tag(self, tag):
        for i, cmd in enumerate(self.script):
            cmd = re.sub(r"\s+", " ", cmd)
            if cmd == f"TAG {tag}":
                return i
        return None

    def run(self):
        line = 0
        self.add_cmd_out_signal.emit(f"开始")
        while True:
            if self.closed:
                break
            try:
                cmd = self.script[line]
            except:
                break
            try:
                if cmd.startswith("#"):
                    line += 1
                    continue
                cmd = re.sub(r"\s+", " ", cmd)
                if cmd == "" or cmd == " ":
                    line += 1
                    continue
                args = cmd.split(" ")
                if args[0] == "FIND_IMAGE":
                    pos = self.find_image(args[1])
                    try:
                        yes = self.get_tag(args[3])
                    except:
                        yes = None
                    try:
                        no = self.get_tag(args[4])
                    except:
                        no = None
                    if pos is None:
                        self.add_cmd_out_signal.emit(
                            f"{line}:{cmd} ERROR [找不到目标图标{args[1]}]"
                        )
                        if no is not None:
                            self.add_cmd_out_signal.emit(
                                f"{line}:{cmd} INFO [跳转{no}]"
                            )
                            line = no
                            line += 1
                            continue
                        else:
                            break
                    self.xy[args[2]] = pos
                    self.add_cmd_out_signal.emit(
                        f"{line}:{cmd} INFO [找到图片({pos[0]},{pos[1]})]"
                    )
                    if yes is not None:
                        self.add_cmd_out_signal.emit(f"{line}:{cmd} INFO [跳转{yes}]")
                        line = yes
                elif args[0] == "CLICK":
                    if args.__len__() == 2:
                        x, y = self.xy[args[1]]
                    else:
                        x, y = int(args[1]), int(args[2])
                    x = random_xy(x)
                    y = random_xy(y)
                    run_cmd(self.make_cmd(f"shell input tap {x} {y}"))
                    self.add_cmd_out_signal.emit(
                        f"{line}:{cmd} INFO [点击坐标({x},{y})]"
                    )
                elif args[0] == "GO":
                    tag = self.get_tag(args[1])
                    if tag is None:
                        self.add_cmd_out_signal.emit(
                            f"{line}:{cmd} ERROR [找不到标签{args[1]}]"
                        )
                        break
                    line = tag
                elif args[0] == "BACK":
                    self.back()
                    self.add_cmd_out_signal.emit(f"{line}:{cmd} INFO [返回]")
                elif args[0] == "HOME":
                    self.home()
                    self.add_cmd_out_signal.emit(f"{line}:{cmd} INFO [回到主页]")
                elif args[0] == "WAIT":
                    s_t = random_time(int(args[1]))
                    time.sleep(s_t)
                    self.add_cmd_out_signal.emit(
                        f"{line}:{cmd} INFO [等待{s_t}秒]"
                    )
                elif args[0] == "END":
                    break
            except Exception as e:
                self.add_cmd_out_signal.emit(f"{line}:{cmd} [{str(e)}]")
                break
            line += 1
            time.sleep(random_time(1))
        self.add_cmd_out_signal.emit(f"结束")


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
        pen.setColor(qRgb(255, 0, 0))
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


class CutImageWindow(QMainWindow):
    def __init__(self, dir):
        self.dir = dir
        super().__init__()  # 调用父类 QMainWindow 的初始化方法
        if not os.path.exists(dir + "/temp"):
            os.mkdir(dir + "/temp")
        id = os.listdir(dir + "/temp").__len__()
        run_cmd("adb shell screencap -p /sdcard/screenshot.png")
        run_cmd(f"adb pull /sdcard/screenshot.png {dir}/temp/image{id}.png")
        time.sleep(1)
        self.resize(200, 100)  # 设置窗口大小
        self.setWindowTitle("截图")  # 设置窗口标题
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        self.image = QPixmap(f"{dir}/temp/image{id}.png")
        os.remove(f"{dir}/temp/image{id}.png")
        self.show_image = QLabel()
        self.show_image.setPixmap(self.image)
        self.show_image.setFixedSize(self.image.size())
        v_box = QGridLayout()
        central_widget.setLayout(v_box)
        self.cut_box = Drawing()
        self.cut_box.setFixedSize(self.image.size())
        v_box.addWidget(self.show_image, 0, 0)
        v_box.addWidget(self.cut_box, 0, 0)
        self.cut_box.raise_()
        ok = QPushButton("确定")
        v_box.addWidget(ok)
        ok.clicked.connect(self.on_click_ok)

    def on_click_ok(self):
        x, y, w, h = self.cut_box.rect
        rect = QRect(x, y, w, h)
        if (
            rect.x() + rect.width() > self.image.width()
            or rect.y() + rect.height() > self.image.height()
        ):
            print("错误：截取区域超出图像范围")
            return

        # 截取子图像
        cropped_pixmap = self.image.copy(rect)

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
    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.setText(text)
        self.widget = QWidget()
        self.layout = QHBoxLayout(self.widget)
        self.layout.setContentsMargins(0, 0, 0, 0)
        name = QLabel(text)
        self.click_button = QPushButton("点击图片")
        self.add_button = QPushButton("寻找图片")
        self.delete_button = QPushButton("删除图片")
        self.layout.addWidget(name)
        self.layout.addWidget(self.add_button)
        self.layout.addWidget(self.click_button)
        self.layout.addWidget(self.delete_button)


class ScriptEditorWindow(QMainWindow):
    def __init__(self, dir):
        super().__init__()  # 调用父类 QMainWindow 的初始化方法
        self.resize(800, 600)  # 设置窗口大小
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
        click_xy_box = QVBoxLayout()
        v_box.addLayout(click_xy_box)
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
        self.cut_image_window = CutImageWindow(self.dir)
        self.cut_image_window.update_image_list = self.update_image_list
        self.cut_image_window.show()

    def on_click_image_list_add_image(self, file_name):
        name = file_name.replace(".png", "")

        def func():
            self.editor.setText(
                self.editor.toPlainText() + f"\nFIND_IMAGE {file_name} {name}"
            )

        return func

    def on_click_image_list_delete_image(self, name):
        def func():
            path = self.dir + "/images/" + name
            os.remove(path)
            self.update_image_list()

        return func

    def on_click_image_list_click_image(self, file_name):
        name = file_name.replace(".png", "")

        def func():
            self.editor.setText(self.editor.toPlainText() + f"\nCLICK {name}")

        return func

    def update_image_list(self):
        try:
            self.image_list.clear()
            for item in [
                ScriptEditoImagesWidgetItem(name)
                for name in os.listdir(self.dir + "/images") or []
            ]:
                item.click_button.clicked.connect(
                    self.on_click_image_list_click_image(item.text())
                )
                item.add_button.clicked.connect(
                    self.on_click_image_list_add_image(item.text())
                )
                item.delete_button.clicked.connect(
                    self.on_click_image_list_delete_image(item.text())
                )
                self.image_list.addItem(item)
                self.image_list.setItemWidget(item, item.widget)
        except:
            pass


class ScriptRunChooseDevice(QMainWindow):
    def __init__(self, dir):
        super().__init__()
        self.dir = dir
        self.resize(800, 600)
        self.setWindowTitle("选择设备")
        self.device_list = QListWidget()
        self.device_list.setStyleSheet(
            "QListWidget::item { padding: 5px;height:40px; }"
        )
        self.device_list.itemDoubleClicked.connect(self.on_click_device_list)
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
            self.device_list.addItem(device)
        self.setCentralWidget(self.device_list)

    def on_click_device_list(self, item):
        self.sr = ScriptRunner(self.dir, item.text())
        self.sr.on_close.connect(self.on_sr_close)
        self.close()
        self.sr.show()
        self.sr.start()

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

    def on_srcd_close(self,srcd):
        def func():
            self.srcds.remove(srcd)
        return func

    def on_click_run(self):
        dir = f"scripts/{self.text()}"
        srcd = ScriptRunChooseDevice(dir)
        srcd.on_sr_close = self.on_srcd_close(srcd)
        srcd.show()
        self.srcds.append(srcd)

    def on_click_delete(self):
        dir = f"scripts/{self.text()}"
        shutil.rmtree(dir)
        self.update_script_list()

    def on_click_edit(self):
        self.editor_window = ScriptEditorWindow(f"scripts/{self.text()}")
        self.editor_window.show()

    def update_script_list():
        pass


class HomeWindow(QMainWindow):
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
        add_script.clicked.connect(self.on_click_add_script)
        self.add_script_window.added.connect(self.on_add_script)
        self.update_script_list()

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
