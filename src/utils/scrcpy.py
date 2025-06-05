import cv2
import numpy as np
import subprocess


class Scrcpy:
    port = 1000

    def __init__(self):
        self.stoped = False

    def listen(self, address, callback):
        self.stoped = False
        # 启动 scrcpy 服务器
        scrpy_process = subprocess.Popen(
            [
                "lib/scrcpy/scrcpy.exe",
                "--tcpip=1234",
                "--no-control",
            ]
        )
        self.port += 1

        # 通过 OpenCV 捕获视频流
        cap = cv2.VideoCapture(f"tcp://127.0.0.1:1234")  # scrcpy 默认端口

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            # 在此处理帧数据
            cv2.imshow("Android Screen", frame)
            callback(frame)
            if self.stoped:
                break
        scrpy_process.terminate()
        cap.release()
        cv2.destroyAllWindows()

    def stop_listen(self):
        self.stoped = True
