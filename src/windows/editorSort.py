# 创建一个主窗口类，继承自 QMainWindow
from src.widgets.page import Page
from PySide6.QtWidgets import (
    QWidget,
    QPushButton,
    QVBoxLayout,
    QTextEdit,
)
from PySide6.QtCore import Signal

class EditorSortWindow(Page):
    ok = Signal(str)

    def __init__(self):
        super().__init__()  # 调用父类 QMainWindow 的初始化方法
        self.resize(200, 500)  # 设置窗口大小
        self.setWindowTitle("排序")  # 设置窗口标题
        with open("scripts/sort.txt","r",encoding="utf-8") as f:
            sort = f.read()
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        h_box = QVBoxLayout()
        central_widget.setLayout(h_box)
        self.sort = QTextEdit()
        self.sort.setText(sort)
        h_box.addWidget(self.sort)
        ok = QPushButton("确定")
        h_box.addWidget(ok)
        ok.clicked.connect(self.on_click_ok)

    def on_click_ok(self):
        sort = self.sort.toPlainText()
        self.ok.emit(sort)
        self.close()