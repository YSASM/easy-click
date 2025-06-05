import json
import os
import random
import re
from threading import Thread
import time
from PySide6.QtWidgets import (
    QMainWindow,
    QTextEdit,
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QTextCharFormat, QTextCursor
from src.utils.vm import Vm
from src.widgets.page import Page


class ScriptRunner(Page):
    update_cmd_out_signal = Signal()
    def __init__(self, address, name, *args, **kwargs):
        self.dir = f"scripts/{name}"
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
        self.update_cmd_out_signal.connect(self.update_cmd_out)
        
    def start(self):
        self.th = Vm(self, self.dir, self.address, self.script)
        self.add_vm_task(self.th)
        

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
        if self.cmd_out_list.__len__() > 50:
            self.cmd_out_list = self.cmd_out_list[-50:]
        self.cmd_out.setText("\n".join(self.cmd_out_list))
        bar = self.cmd_out.verticalScrollBar()
        bar.setValue(bar.maximum())
        self.set_cmd_out_color()

    def closeEvent(self, event):
        self.th.kill()
        return super().closeEvent(event)


