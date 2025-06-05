import os
from src import start
import sys
import traceback
def my_excepthook(exctype, value, tb):
    with open("error.log", "a") as log_file:
        log_file.write("An error occurred: {}\n".format(exctype))
        traceback.print_exception(exctype, value, tb, file=log_file)
    sys.__excepthook__(exctype, value, tb)  # 调用默认的异常钩子以保持程序的正常退出


sys.excepthook = my_excepthook
if __name__ == '__main__':
    start()