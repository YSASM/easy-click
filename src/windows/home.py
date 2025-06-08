import os
import re
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
    QMessageBox,
)
from PySide6.QtCore import Signal

from src.utils import Bean
from src.utils.adb import Adb
from src.widgets.listItem import ListItem
from src.widgets.page import Page
from src.widgets.switch import Switch
from src.windows.chooseDevice import ChooseDevice
from src.windows.editor import ScriptEditorWindow
from src.windows.scriptRunner import ScriptRunner
import platform

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
    def __init__(self, page: Page, text, default_devices, get_after_run_close_script, *args, **kwargs):
        super().__init__(page, text, *args, **kwargs)
        self.widget = QWidget()
        self.layout = QHBoxLayout(self.widget)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.default_devices = default_devices
        if platform.release() == "10":
            name = QLabel()
        else:
            name = QLabel(text)
        run_button = QPushButton("运行")
        run_more_button = QPushButton("多开")
        editor_button = QPushButton("编辑")
        delete_button = QPushButton("删除")
        self.layout.addWidget(name)
        self.layout.addWidget(run_button)
        self.layout.addWidget(run_more_button)
        self.layout.addWidget(editor_button)
        self.layout.addWidget(delete_button)
        run_button.clicked.connect(self.on_click_run)
        run_more_button.clicked.connect(self.on_click_run_more)
        editor_button.clicked.connect(self.on_click_edit)
        delete_button.clicked.connect(self.on_click_delete)
        self.get_after_run_close_script = get_after_run_close_script

    def on_click_run_more(self):
        for devices in self.default_devices:
            self.on_changed_device(devices)

    def on_changed_device(self, address):
        try:
            sr = ScriptRunner(address, self.text(), self.get_after_run_close_script())
            self.page.open_page(sr)
            sr.start()
        except Exception as e:
            Bean.cmd_out_list.append(str(e))

    def on_click_run(self):
        Adb.check_adb()
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
        self.default_devices_txt = ""
        if os.path.exists("default_devices.txt"):
            with open("default_devices.txt", "r", encoding="utf-8") as f:
                self.default_devices_txt = f.read()
                self.default_devices = self.default_devices_txt.split("\n")
                self.default_devices = list(
                    filter(lambda x: x != "", self.default_devices)
                )
        else:
            with open("default_devices.txt", "w+", encoding="utf-8") as f:
                self.default_devices = []
        for device in self.default_devices:
            Adb(device).connect()

        self.after_run_close_script = True

        # 创建垂直布局管理器
        vbox_layout = QVBoxLayout()
        # 将布局设置为中央控件的布局
        central_widget.setLayout(vbox_layout)

        head_tools_box = QHBoxLayout()
        add_script = QPushButton("新建")
        after_run_close_script_switch = Switch(True, False,"完成后关闭","完成后保留",self.after_run_close_script)
        head_tools_box.addWidget(add_script)
        head_tools_box.addWidget(after_run_close_script_switch)
        vbox_layout.addLayout(head_tools_box)
        self.script_list = QListWidget()
        self.script_list.setStyleSheet(
            "QListWidget::item { padding: 5px;height:40px; }"
        )
        self.update_script_list()

        vbox_layout.addWidget(self.script_list)
        connect_adb_box = QHBoxLayout()
        vbox_layout.addLayout(connect_adb_box)
        input_label = QLabel("输入设备地址")
        connect_adb_box.addWidget(input_label)
        self.input_address = QLineEdit("127.0.0.1:7555")
        connect_adb_box.addWidget(self.input_address)
        connect_adb_button = QPushButton("连接")
        restart_adb_button = QPushButton("重启ADB")
        connect_adb_box.addWidget(connect_adb_button)
        connect_adb_box.addWidget(restart_adb_button)
        connect_adb_button.clicked.connect(self.connect_adb)
        restart_adb_button.clicked.connect(self.restart_adb)
        add_script.clicked.connect(self.on_click_add_script)
        after_run_close_script_switch.changed.connect(
            self.on_after_run_close_script_switch_change
        )

        self.cmd_out = QTextEdit()
        self.cmd_out.setReadOnly(True)
        self.cmd_out.setFixedHeight(200)
        clear_cmd_out = QPushButton("清空")
        cmd_box = QVBoxLayout()
        cmd_box.addWidget(self.cmd_out)
        cmd_box.addWidget(clear_cmd_out)
        clear_cmd_out.clicked.connect(self.clear_cmd_out)

        self.default_device_editor = QTextEdit(self.default_devices_txt)
        self.default_device_editor.setFixedHeight(200)
        self.default_device_editor.setFixedWidth(160)

        device_buttons_box = QHBoxLayout()

        save_default_device_btn = QPushButton("保存")
        connect_all_default_device_btn = QPushButton("链接")

        device_buttons_box.addWidget(save_default_device_btn)
        device_buttons_box.addWidget(connect_all_default_device_btn)

        device_box = QVBoxLayout()
        device_box.addWidget(self.default_device_editor)
        device_box.addLayout(device_buttons_box)
        save_default_device_btn.clicked.connect(self.save_defalut_devices)
        connect_all_default_device_btn.clicked.connect(self.connect_all_default_device)

        cmd_and_device_box = QHBoxLayout()
        cmd_and_device_box.addLayout(cmd_box)
        cmd_and_device_box.addLayout(device_box)
        vbox_layout.addLayout(cmd_and_device_box)
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

        self.update_cmd_out_signal.connect(self.update_cmd_out)
        self.start_reflash_cmd_out()
        Adb.check_adb()

    def on_after_run_close_script_switch_change(self, value):
        self.after_run_close_script = value

    def get_after_run_close_script(self):
        return self.after_run_close_script

    def connect_all_default_device(self):
        for device in self.default_devices:
            Adb(device).connect()

        Adb.check_adb()

    def save_defalut_devices(self):
        with open("default_devices.txt", "w+", encoding="utf-8") as f:
            self.default_devices_txt = self.default_device_editor.toPlainText()
            f.write(self.default_devices_txt)
            self.default_devices = self.default_devices_txt.split("\n")
            self.default_devices = list(filter(lambda x: x != "", self.default_devices))
            msg = QMessageBox()
            msg.setText("保存成功")
            msg.exec_()

    def restart_adb(self):
        Adb.kill()
        Adb.start()
        self.add_cmd_out(self,"重启成功")

    def connect_adb(self):
        Adb(self.input_address.text()).connect()
        Adb.check_adb()

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
        self.reflash_thread = Thread(target=self.reflash_cmd_out, daemon=True)
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
            ScriptListWidgetItem(self, name, self.default_devices, self.get_after_run_close_script)
            for name in os.listdir("scripts")
        ]:
            item.update_script_list = self.update_script_list
            self.script_list.addItem(item)
            self.script_list.setItemWidget(item, item.widget)
