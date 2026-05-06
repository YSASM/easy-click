# This Python file uses the following encoding: utf-8
import sys
from threading import Thread
from PySide6.QtWidgets import QApplication, QMainWindow

from src.utils.vm import Vm
from src.widgets.page import Page
from .windows import HomeWindow


pages = {}
tasks = []


def add_vm_task(th: Vm):
    tasks.append(th)
    th.start()


def on_page_close(object: Page):
    print(f"关闭{object.id}")
    try:
        if hasattr(pages,str(object.id)):
            delattr(pages,str(object.id))
    except Exception as e:
        print(e)


def open_page(page: Page):
    print(f"开启{page.id}")
    page.closed.connect(on_page_close)
    page.open_page_signal.connect(open_page)
    page.add_vm_task_signal.connect(add_vm_task)
    page.show()
    pages[page.id] = page


def listen():
    while True:
        for index, task in enumerate(tasks):
            task: Vm = task
            if task.end:
                task.join()
                print(task.ident)
                tasks.__delitem__(index)
                break


def start():
    app = QApplication(sys.argv)
    mw = HomeWindow()
    open_page(mw)
    Thread(target=listen, daemon=True).start()
    sys.exit(app.exec())
