import os
import shutil
from threading import Thread
import time
from PySide6.QtWidgets import (
    QListWidget,
    QWidget,
    QVBoxLayout,
    QPushButton,
    QHBoxLayout,
    QLineEdit,
    QLabel,
    QTextEdit,
)
from PySide6.QtCore import Signal

from src.utils import Bean, check_adb, run_cmd
from src.widgets.listItem import ListItem
from src.widgets.page import Page
from src.windows.chooseDevice import ChooseDevice
from src.windows.editor import ScriptEditorWindow
from src.windows.scriptRunner import ScriptRunner


# 创建一个主窗口类，继承自 QMainWindow
class AddScriptWindow(Page):
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


class ScriptListWidgetItem(ListItem):
    def __init__(self, page: Page, text, *args, **kwargs):
        super().__init__(page, text, *args, **kwargs)
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

    def on_listen(self, frame):
        pass

    def on_changed_device(self, address):
        try:
            sr = ScriptRunner(address, self.text())
            self.page.open_page(sr)
            sr.start()
        except Exception as e:
            Bean.cmd_out_list.append(str(e))

    def on_click_run(self):
        check_adb()
        if len(Bean.adb_devices) == 0:
            return HomeWindow.add_cmd_out(self, "没有设备")
        try:
            cd = ChooseDevice()
            self.page.open_page(cd)
            cd.on_closed.connect(self.on_changed_device)
            # return None
        except Exception as e:
            HomeWindow.add_cmd_out(self, str(e))
            # return None

    def on_click_delete(self):
        shutil.rmtree(f"scripts/{self.text()}")
        time.sleep(1)
        self.update_script_list()

    def on_click_edit(self):
        editor_window = ScriptEditorWindow(f"scripts/{self.text()}")
        self.page.open_page(editor_window)

    def update_script_list(self):
        pass


class HomeWindow(Page):

    update_cmd_out_signal = Signal()

    @classmethod
    def add_cmd_out(cls, obj: object, cmd_out):
        Bean.cmd_out_list.append(f"{obj.__class__.__name__} {cmd_out}")

    def __init__(self):
        super().__init__()  # 调用父类 QMainWindow 的初始化方法
        self.reflash_thread = None
        self.resize(800, 600)  # 设置窗口大小
        self.setWindowTitle("easy click")  # 设置窗口标题
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

        self.update_script_list()
        self.cmd_out = QTextEdit()
        self.cmd_out.setReadOnly(True)
        self.cmd_out.setFixedHeight(200)
        vbox_layout.addWidget(self.cmd_out)
        clear_cmd_out = QPushButton("清空")
        vbox_layout.addWidget(clear_cmd_out)
        about_box = QHBoxLayout()
        vbox_layout.addLayout(about_box)
        about_name = QLabel(
            "声明：本软件仅供学习交流，不收取任何费用！！！！ by: 杳末钎散 "
        )
        about_box.addWidget(about_name)
        connect = QLineEdit(
            "QQ: 1613921123 Github: https://github.com/YSASM/easy-click"
        )
        connect.setReadOnly(True)
        about_box.addWidget(connect)
        clear_cmd_out.clicked.connect(self.clear_cmd_out)
        self.update_cmd_out_signal.connect(self.update_cmd_out)
        self.start_reflash_cmd_out()
        check_adb()

    def connect_adb(self):
        res = run_cmd("adb connect " + self.input_address.text())
        self.add_cmd_out(self, res)
        check_adb()

    def clear_cmd_out(self):
        Bean.cmd_out_list.clear()

    def update_cmd_out(self):
        info = "\n".join(Bean.cmd_out_list)
        if info != self.cmd_out.toPlainText():
            self.cmd_out.setText(info)

    def reflash_cmd_out(self):
        while True:
            self.update_cmd_out_signal.emit()
            time.sleep(1)

    def start_reflash_cmd_out(self):
        self.reflash_thread = Thread(target=self.reflash_cmd_out,daemon=True)
        self.reflash_thread.start()

    def on_click_add_script(self):
        add_script_window = AddScriptWindow()
        add_script_window.added.connect(self.on_add_script)
        self.open_page(add_script_window)

    def on_add_script(self):
        self.update_script_list()

    def update_script_list(self):
        self.script_list.clear()
        for item in [
            ScriptListWidgetItem(self, name) for name in os.listdir("scripts")
        ]:
            item.update_script_list = self.update_script_list
            self.script_list.addItem(item)
            self.script_list.setItemWidget(item, item.widget)
