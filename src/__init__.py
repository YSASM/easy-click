# This Python file uses the following encoding: utf-8
import sys
from threading import Thread
from PySide6.QtWidgets import QApplication,QMainWindow
from .windows import HomeWindow

def start():
    app = QApplication(sys.argv)
    # ...
    mw = HomeWindow()
    mw.show()
    def listen():
        while True:
            del_list = []
            for task in mw.get_tasks():
                task:Thread = task
                if task.is_alive():
                    task.join()
                    print(f"任务结束{task.ident}")
                    del_list.append(task)
            for task in del_list:
                mw.remove_task(task)

    th = Thread(target=listen)
    th.setDaemon(True)
    th.start()
    sys.exit(app.exec())

