from threading import Thread
import uuid
from PySide6.QtWidgets import QMainWindow, QLabel
from PySide6.QtCore import Signal, QObject, QThread
from PySide6.QtGui import QCursor, QGuiApplication


class Worker(QObject):
    finished = Signal()
    def __init__(self, /, parent = ..., *, objectName = ...):
        super().__init__(parent, objectName=objectName)
        self.target = None
    def run(self):
        try:
            if self.target is not None:
                self.target()
        finally:
            self.finished.emit()  # 通知任务完成

class Page(QMainWindow):
    closed = Signal(QMainWindow)
    open_page_signal = Signal(QMainWindow)
    add_vm_task_signal = Signal(Thread)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.id = uuid.uuid4()
        self._page_centered_once = False

    def showEvent(self, event):
        super().showEvent(event)
        if not self._page_centered_once:
            self._page_centered_once = True
            self._page_center_on_screen()

    def _page_center_on_screen(self):
        """在鼠标所在屏（无则主屏）的工作区内几何居中。"""
        screen = QGuiApplication.screenAt(QCursor.pos())
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        ag = screen.availableGeometry()
        fg = self.frameGeometry()
        fg.moveCenter(ag.center())
        self.move(fg.topLeft())

    def async_run(self, fun):
        thread = QThread()
        worker = Worker()
        worker.target = fun
        worker.moveToThread(thread)  # 将 worker 对象移动到新线程中
        worker.finished.connect(thread.quit)  # 当任务完成时，退出线程
        worker.finished.connect(worker.deleteLater)  # 清理 worker 对象内存
        thread.started.connect(worker.run)  # 开始执行任务
        thread.start()  # 启动线程

    def open_page(self, page):
        self.open_page_signal.emit(page)

    def closeEvent(self, event):
        self.closed.emit(self)
        return super().closeEvent(event)

    def add_vm_task(self, th):
        self.add_vm_task_signal.emit(th)
