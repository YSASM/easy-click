import os

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

from src.utils import Bean, check_adb, run_cmd
from src.utils.uiautomator2Manger import Uiautomator2
from src.widgets.label import Label
from src.widgets.image import Image as ImageView
from src.widgets.listItem import ListItem
from src.widgets.page import Page
from src.windows.chooseDevice import ChooseDevice
from src.windows.scriptRunner import ScriptRunner

RED = qRgb(255, 0, 0)


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


class GetXYWindow(Page):
    getted = Signal(list)

    def __init__(self, dir, address):
        super().__init__()  # 调用父类 QMainWindow 的初始化方法
        self.dir = dir
        self.address = address
        u2 = Uiautomator2(address)
        u2.connect()
        image = u2.screenshot_pillow()
        self.resize(200, 100)  # 设置窗口大小
        self.setWindowTitle("取点")  # 设置窗口标题
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        self.show_image = ImageView(image)
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


class CutImageWindow(Page):
    def __init__(self, dir, address):
        self.dir = dir
        self.address = address
        super().__init__()  # 调用父类 QMainWindow 的初始化方法
        u2 = Uiautomator2(address)
        u2.connect()
        image = u2.screenshot_pillow()
        self.resize(200, 100)  # 设置窗口大小
        self.setWindowTitle("截图")  # 设置窗口标题
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        self.show_image = ImageView(image)
        # self.show_image.setPixmap(self.image)
        # self.show_image.setFixedSize(self.image.size())
        v_box = QGridLayout()
        central_widget.setLayout(v_box)
        self.cut_box = Drawing()
        self.cut_box.setFixedSize(self.show_image.pixmap().size())
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


class ScriptEditoImagesWidgetItem(ListItem):
    def __init__(self, page: Page, text, dir, *args, **kwargs):
        super().__init__(page, text, *args, **kwargs)
        self.widget = QWidget()
        self.layout = QHBoxLayout(self.widget)
        self.layout.setContentsMargins(0, 0, 0, 0)
        image = ImageView(f"{dir}/images/{text}")
        image.setSize(100, 100)
        self.name = QLabel(text)
        self.name.setFixedSize(QSize(80, 20))
        self.change_name_button = QPushButton("修改名称")
        self.click_button = QPushButton("点击图片")
        self.add_button = QPushButton("寻找图片")
        self.re_cut_image_button = QPushButton("重新截图")
        self.delete_button = QPushButton("删除图片")
        self.layout.addWidget(image)
        self.layout.addWidget(self.name)
        self.layout.addWidget(self.change_name_button)
        self.layout.addWidget(self.add_button)
        self.layout.addWidget(self.click_button)
        self.layout.addWidget(self.re_cut_image_button)
        self.layout.addWidget(self.delete_button)


# 创建一个主窗口类，继承自 QMainWindow
class ChangeNameWindow(Page):
    change = Signal(str)

    def __init__(self,name):
        super().__init__()  # 调用父类 QMainWindow 的初始化方法
        self.resize(200, 100)  # 设置窗口大小
        self.setWindowTitle("修改名称")  # 设置窗口标题
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        h_box = QHBoxLayout()
        central_widget.setLayout(h_box)
        self.name = QLineEdit(name)
        h_box.addWidget(self.name)
        ok = QPushButton("确定")
        h_box.addWidget(ok)
        ok.clicked.connect(self.on_click_ok)

    def on_click_ok(self):
        name = self.name.text()
        self.change.emit(name)
        self.close()

class ScriptEditorWindow(Page):
    def __init__(self, dir):
        super().__init__()  # 调用父类 QMainWindow 的初始化方法
        self.resize(1200, 600)  # 设置窗口大小
        self.name = dir.replace("/","\\").split("\\")[-1]
        self.setWindowTitle(f"编辑-{self.name}")
        
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
        check_adb()
        adb_label = QLabel("设备")
        self.adb_address = QLineEdit(
            Bean.adb_devices[0] if len(Bean.adb_devices) > 0 else ""
        )
        v_box.addWidget(adb_label)
        v_box.addWidget(self.adb_address)
        click_xy_box = QVBoxLayout()
        v_box.addLayout(click_xy_box)

        click_xy_get_box = QHBoxLayout()
        click_xy_box.addLayout(click_xy_get_box)
        

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
        click_xy_get_button = QPushButton("获取坐标")
        click_xy_button = QPushButton("插入")
        click_xy_input_box.addWidget(click_xy_get_button)
        click_xy_input_box.addWidget(click_xy_button)
        click_xy_button.clicked.connect(self.on_click_click_xy)
        click_xy_get_button.clicked.connect(self.on_click_click_xy_get)
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
        run_button = QPushButton("运行")
        tools_buttons = QHBoxLayout()
        v_box.addLayout(tools_buttons)
        tools_buttons.addWidget(save_button)
        tools_buttons.addWidget(run_button)
        save_button.clicked.connect(self.on_click_save)
        run_button.clicked.connect(self.on_click_run)

        # 编辑器
        self.editor = QTextEdit()
        self.editor.setText(self.content)
        self.editor.setFixedSize(QSize(600, 600))
        h_box.addWidget(self.editor)
        self.editor.setStyleSheet("QTextEdit { width: 500px; }")
        add_image_button.clicked.connect(self.on_click_add_image)

    def on_changed_device(self, address):
        try:
            sr = ScriptRunner(address, self.name)
            self.open_page(sr)
            sr.start()
        except Exception as e:
            Bean.cmd_out_list.append(str(e))

    def on_click_run(self):
        with open(self.file, "w+", encoding="utf-8") as f:
            self.content = self.editor.toPlainText()
            f.write(self.content)
        sr = ScriptRunner(self.adb_address.text(), self.name)
        self.open_page(sr)
        sr.start()

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
        cut_image_window = CutImageWindow(self.dir, self.adb_address.text())
        cut_image_window.update_image_list = self.update_image_list
        self.open_page(cut_image_window)

    def on_getted(self, xy):
        self.click_xy_x.setText(str(xy[0]))
        self.click_xy_y.setText(str(xy[1]))

    def on_click_click_xy_get(self):
        get_xy_window = GetXYWindow(self.dir, self.adb_address.text())
        get_xy_window.getted.connect(self.on_getted)
        self.open_page(get_xy_window)

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
    
    def on_change_name(self,old):
        def func(new):
            os.rename(os.path.join(self.dir,"images",old), os.path.join(self.dir,"images",new))
            self.update_image_list()
        return func

    def on_click_change_name(self, item):
        def func():
            cnw = ChangeNameWindow(item.text())
            cnw.change.connect(self.on_change_name(item.text()))
            self.open_page(cnw)
        return func

    def update_image_list(self):
        try:
            self.image_list.clear()
            for item in [
                ScriptEditoImagesWidgetItem(self, name, self.dir)
                for name in os.listdir(self.dir + "/images") or []
            ]:
                item.change_name_button.clicked.connect(self.on_click_change_name(item))
                item.click_button.clicked.connect(
                    self.on_click_image_list_click_image(item)
                )
                item.add_button.clicked.connect(
                    self.on_click_image_list_add_image(item)
                )
                # item.re_cut_image_button.connect()
                item.delete_button.clicked.connect(
                    self.on_click_image_list_delete_image(item)
                )
                self.image_list.addItem(item)
                self.image_list.setItemWidget(item, item.widget)
        except:
            pass
