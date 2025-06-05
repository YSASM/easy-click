from threading import Thread
import uuid
from PySide6.QtWidgets import QMainWindow
from PySide6.QtCore import Signal


class Page(QMainWindow):
    closed = Signal(QMainWindow)
    open_page_signal = Signal(QMainWindow)
    add_vm_task_signal = Signal(Thread)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.id = uuid.uuid4()

    def open_page(self, page):
        self.open_page_signal.emit(page)

    def closeEvent(self, event):
        self.closed.emit(self)
        return super().closeEvent(event)

    def add_vm_task(self, th):
        self.add_vm_task_signal.emit(th)
