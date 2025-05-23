from PySide6.QtWidgets import (
    QListWidget,
)
from PySide6.QtCore import Signal
from src.utils import Bean
from src.widgets.page import Page


class ChooseDevice(Page):
    on_closed = Signal(str)
    def __init__(self):
        super().__init__()
        self.resize(800, 600)
        self.setWindowTitle("选择设备")
        self.device_list = QListWidget()
        self.device_list.setStyleSheet(
            "QListWidget::item { padding: 5px;height:40px; }"
        )
        self.device_list.itemDoubleClicked.connect(self.on_click_device_list)
        for device in Bean.adb_devices:
            self.device_list.addItem(device)
        self.setCentralWidget(self.device_list)

    def on_click_device_list(self, item):
        self.on_closed.emit(item.text())
        self.close()
