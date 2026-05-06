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
from PySide6.QtCore import Qt, Signal, QModelIndex

from src.utils import Bean
from src.utils.adb import Adb
from src.widgets.listItem import ListItem
from src.widgets.modern_button import apply_modern_button
from src.widgets.page import Page
from src.widgets.switch import Switch
from src.windows.chooseDevice import ChooseDevice
from src.windows.editor import ScriptEditorWindow
from src.windows.scriptRunner import ScriptRunner
from pathlib import Path
import shutil
import uiautomator2 as u2
assets = os.path.join(Path(u2.__file__).parent, "assets")
Bean.cmd_out_list.append(f"{assets}")
if not os.path.exists(assets):
    shutil.copytree("lib/uiautomator2", assets)
    Bean.cmd_out_list.append("uiautomator2 加载成功")
else:
    if os.listdir(assets) != os.listdir("lib/uiautomator2"):
        shutil.rmtree(assets)
        shutil.copytree("lib/uiautomator2", assets)
        Bean.cmd_out_list.append("uiautomator2 加载成功")
    else:
        Bean.cmd_out_list.append("uiautomator2 已加载")
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
        apply_modern_button(ok, "blue")
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
    def __init__(
        self,
        page: Page,
        text,
        default_devices,
        get_after_run_close_script,
        *,
        row_index=0,
        row_count=1,
        **kwargs,
    ):
        super().__init__(page, text, **kwargs)
        self.widget = QWidget()
        self.layout = QHBoxLayout(self.widget)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.default_devices = default_devices
        name = QLabel(text)
        run_button = QPushButton("运行")
        run_more_button = QPushButton("多开")
        editor_button = QPushButton("编辑")
        delete_button = QPushButton("删除")
        apply_modern_button(run_button, "teal")
        apply_modern_button(run_more_button, "violet")
        apply_modern_button(editor_button, "blue")
        apply_modern_button(delete_button, "rose")
        self.up_btn = QPushButton("↑")
        self.up_btn.setToolTip("上移")
        self.down_btn = QPushButton("↓")
        self.down_btn.setToolTip("下移")
        apply_modern_button(self.up_btn, "slate")
        apply_modern_button(self.down_btn, "slate")
        self.up_btn.setFixedWidth(32)
        self.down_btn.setFixedWidth(32)
        self.up_btn.setEnabled(row_index > 0)
        self.down_btn.setEnabled(row_index < row_count - 1)
        self.layout.addWidget(self.up_btn)
        self.layout.addWidget(self.down_btn)
        self.layout.addWidget(name)
        self.layout.addWidget(run_button)
        self.layout.addWidget(run_more_button)
        self.layout.addWidget(editor_button)
        self.layout.addWidget(delete_button)
        run_button.clicked.connect(self.on_click_run)
        run_more_button.clicked.connect(self.on_click_run_more)
        editor_button.clicked.connect(self.on_click_edit)
        delete_button.clicked.connect(self.on_click_delete)
        self.up_btn.clicked.connect(self._on_move_up)
        self.down_btn.clicked.connect(self._on_move_down)
        self.get_after_run_close_script = get_after_run_close_script

    def _on_move_up(self):
        if hasattr(self.page, "script_move_up"):
            self.page.script_move_up(self.text())

    def _on_move_down(self):
        if hasattr(self.page, "script_move_down"):
            self.page.script_move_down(self.text())

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
        name = self.text()
        path = f"scripts/{name}"
        r1 = QMessageBox.question(
            self.page,
            "删除确认",
            f"确定要删除脚本「{name}」吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if r1 != QMessageBox.StandardButton.Yes:
            return
        r2 = QMessageBox.question(
            self.page,
            "再次确认",
            "删除后无法恢复，是否继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if r2 != QMessageBox.StandardButton.Yes:
            return
        shutil.rmtree(path)
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
        self.resize(1000, 600)  # 设置窗口大小
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

        root_hbox = QHBoxLayout()
        central_widget.setLayout(root_hbox)

        left_panel = QWidget()
        left_vbox = QVBoxLayout(left_panel)
        left_vbox.setContentsMargins(0, 0, 0, 0)
        left_panel.setMinimumWidth(500)

        self.script_list = QListWidget()
        self.script_list.setStyleSheet(
            "QListWidget::item { padding: 4px 6px; min-height: 28px; }"
        )
        self._script_items: dict = {}
        self._script_snapshot: tuple | None = None
        self.update_script_list()
        left_vbox.addWidget(self.script_list)

        right_panel = QWidget()
        right_vbox = QVBoxLayout(right_panel)
        root_hbox.addWidget(left_panel, 2)
        root_hbox.addWidget(right_panel, 3)

        head_tools_box = QHBoxLayout()
        add_script = QPushButton("新建")
        apply_modern_button(add_script, "sky")
        after_run_close_script_switch = Switch(True, False,"完成后关闭","完成后保留",self.after_run_close_script)
        head_tools_box.addWidget(add_script)
        head_tools_box.addWidget(after_run_close_script_switch)
        right_vbox.addLayout(head_tools_box)

        connect_adb_box = QHBoxLayout()
        right_vbox.addLayout(connect_adb_box)
        input_label = QLabel("输入设备地址")
        connect_adb_box.addWidget(input_label)
        self.input_address = QLineEdit("127.0.0.1:7555")
        connect_adb_box.addWidget(self.input_address)
        connect_adb_button = QPushButton("连接")
        restart_adb_button = QPushButton("重启ADB")
        apply_modern_button(connect_adb_button, "blue")
        apply_modern_button(restart_adb_button, "amber")
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
        apply_modern_button(clear_cmd_out, "slate")
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
        apply_modern_button(save_default_device_btn, "emerald")
        apply_modern_button(connect_all_default_device_btn, "cyan")

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
        right_vbox.addLayout(cmd_and_device_box)
        about_box = QHBoxLayout()
        right_vbox.addLayout(about_box)
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


    def _write_script_sort_order(self, names: list):
        with open(os.path.join("scripts", "sort.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(names))

    def _current_script_list_order(self):
        order = []
        for i in range(self.script_list.count()):
            it = self.script_list.item(i)
            if it is not None:
                order.append(it.text())
        return order

    def _move_row_keep_widget(self, from_row: int, to_row: int) -> bool:
        """用 model.moveRow 重排行，内嵌 itemWidget 会随行移动，避免 takeItem 与控件脱钩导致崩溃。"""
        if from_row == to_row:
            return True
        n = self.script_list.count()
        if from_row < 0 or from_row >= n or to_row < 0 or to_row >= n:
            return False
        m = self.script_list.model()
        parent = QModelIndex()
        if from_row < to_row:
            dest = to_row + 1
        else:
            dest = to_row
        return bool(m.moveRow(parent, from_row, parent, dest))

    def script_move_up(self, script_name: str):
        n = self.script_list.count()
        r = None
        for i in range(n):
            it = self.script_list.item(i)
            if it is not None and it.text() == script_name:
                r = i
                break
        if r is None or r <= 0:
            return
        order = self._current_script_list_order()
        if len(order) != n or r >= len(order):
            self.update_script_list()
            return
        order[r - 1], order[r] = order[r], order[r - 1]
        self._write_script_sort_order(order)
        if not self._move_row_keep_widget(r, r - 1):
            self._full_rebuild_script_list(self.get_scripts(), quiet=True)
            return
        self._script_snapshot = tuple(order)
        self._apply_script_row_move_buttons(n)

    def script_move_down(self, script_name: str):
        n = self.script_list.count()
        r = None
        for i in range(n):
            it = self.script_list.item(i)
            if it is not None and it.text() == script_name:
                r = i
                break
        if r is None or r >= n - 1:
            return
        order = self._current_script_list_order()
        if len(order) != n or r >= len(order):
            self.update_script_list()
            return
        order[r], order[r + 1] = order[r + 1], order[r]
        self._write_script_sort_order(order)
        if not self._move_row_keep_widget(r, r + 1):
            self._full_rebuild_script_list(self.get_scripts(), quiet=True)
            return
        self._script_snapshot = tuple(order)
        self._apply_script_row_move_buttons(n)

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

    def get_scripts(self):
        scripts = os.listdir("scripts") or []
        scripts = list(filter(lambda x:x!="sort.txt",scripts))
        if not os.path.exists("scripts/sort.txt"):
            with open("scripts/sort.txt","w+",encoding="utf-8") as f:
                f.write("\n".join(scripts))
        
        with open("scripts/sort.txt","r",encoding="utf-8") as f:
            sort = f.read().replace(" ","").replace("\t","").replace("\r","").split("\n")
        sort = list(filter(lambda x:x!="",sort))
        
        last_scripts_list = []
        for s in sort:
            if s in scripts:
                last_scripts_list.append(s)
                scripts.remove(s)
        last_scripts_list += scripts
        with open("scripts/sort.txt","w+",encoding="utf-8") as f:
            f.write("\n".join(last_scripts_list))
        return last_scripts_list

    def _apply_script_row_move_buttons(self, row_count: int):
        for i in range(self.script_list.count()):
            it = self.script_list.item(i)
            if it is None:
                continue
            item = self._script_items.get(it.text())
            if item is None:
                continue
            item.up_btn.setEnabled(i > 0)
            item.down_btn.setEnabled(i < row_count - 1)

    def _remove_script_row(self, name: str):
        item = self._script_items.pop(name, None)
        if item is None:
            return
        r = self.script_list.row(item)
        if r < 0:
            return
        w = self.script_list.itemWidget(item)
        if w is not None:
            self.script_list.removeItemWidget(item)
        self.script_list.takeItem(r)

    def _insert_new_script_row(self, name: str, index: int, row_count: int):
        item = ScriptListWidgetItem(
            self,
            name,
            self.default_devices,
            self.get_after_run_close_script,
            row_index=index,
            row_count=row_count,
        )
        item.update_script_list = self.update_script_list
        self._script_items[name] = item
        self.script_list.insertItem(index, item)
        self.script_list.setItemWidget(item, item.widget)

    def _reconcile_rows_to_order(self, names: list) -> bool:
        """把已有行挪到与 names 一致（takeItem 前先卸下 widget）。"""
        for want_pos, want_name in enumerate(names):
            while True:
                it = self.script_list.item(want_pos)
                if it is not None and it.text() == want_name:
                    break
                j = want_pos + 1
                while j < self.script_list.count():
                    jt = self.script_list.item(j)
                    if jt is not None and jt.text() == want_name:
                        break
                    j += 1
                if j >= self.script_list.count():
                    return False
                if not self._move_row_keep_widget(j, want_pos):
                    return False
        return True

    def _incremental_sync_to_names(self, names: list) -> bool:
        """新有旧无则插入，旧有新无则删除，顺序不对则挪行。成功返回 True。"""
        new_keys = set(names)
        for name in list(self._script_items.keys()):
            if name not in new_keys:
                self._remove_script_row(name)
        to_add = [nm for nm in names if nm not in self._script_items]
        n = len(names)
        if to_add:
            if self.script_list.count() == 0:
                for i, name in enumerate(to_add):
                    self._insert_new_script_row(name, i, n)
            else:
                for name in sorted(to_add, key=lambda x: -names.index(x)):
                    idx = names.index(name)
                    self._insert_new_script_row(name, idx, n)
        if set(self._script_items.keys()) != new_keys:
            return False
        if self.script_list.count() != n:
            return False
        cur = []
        for i in range(self.script_list.count()):
            it = self.script_list.item(i)
            if it is None:
                return False
            cur.append(it.text())
        if cur == names:
            return True
        return self._reconcile_rows_to_order(names)

    def _full_rebuild_script_list(self, names: list, *, quiet: bool = False):
        """仅作兜底：清空后按序重建（无进度条，避免主线程长时间弹窗）。"""
        _ = quiet
        self.script_list.clear()
        self._script_items.clear()
        if not names:
            self._script_snapshot = tuple()
            return
        for i, name in enumerate(names):
            item = ScriptListWidgetItem(
                self,
                name,
                self.default_devices,
                self.get_after_run_close_script,
                row_index=i,
                row_count=len(names),
            )
            item.update_script_list = self.update_script_list
            self._script_items[name] = item
            self.script_list.addItem(item)
            self.script_list.setItemWidget(item, item.widget)
        self._script_snapshot = tuple(names)

    def _sync_script_list_ui(self, names: list):
        if not names:
            self.script_list.clear()
            self._script_items.clear()
            self._script_snapshot = tuple()
            return

        new_t = tuple(names)
        n = len(names)
        if (
            self._script_snapshot == new_t
            and self.script_list.count() == n
            and set(self._script_items.keys()) == set(names)
        ):
            self._apply_script_row_move_buttons(n)
            return

        if not self._incremental_sync_to_names(names):
            self._full_rebuild_script_list(names, quiet=True)

        self._script_snapshot = tuple(names)
        self._apply_script_row_move_buttons(len(names))

    def update_script_list(self):
        if not hasattr(self, "script_list"):
            return
        if not hasattr(self, "_script_items"):
            self._script_items = {}
            self._script_snapshot = None
        names = self.get_scripts()
        self._sync_script_list_ui(names)
