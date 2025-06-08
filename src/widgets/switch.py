from typing import Any
from PySide6.QtCore import QPropertyAnimation, QPoint, Signal
from PySide6.QtWidgets import QPushButton, QLabel


class Switch(QPushButton):
    changed = Signal(Any)

    def __init__(
        self,
        open_value=True,
        close_value=False,
        open_text="OFF",
        close_text="NO",
        default_value=False,
    ):
        super().__init__()

        self.open_value = open_value
        self.close_value = close_value
        self.open_text = open_text
        self.close_text = close_text

        self.setCheckable(True)  # 使按钮可以选中和取消选中
        if default_value:
            self.setChecked(True)
        else:
            self.setChecked(False)
        self.setStyleSheet(
            """
            SwitchButton {
                border: 2px solid #ccc;
                border-radius: 15px;
                background-color: #ccc;
                width: 80px;  /* 增加宽度 */
                height: 30px;
                position: relative;
            }
            SwitchButton:checked {
                background-color: #4CAF50;
            }
        """
        )
        self.setFixedSize(150, 30)

        self._slider = QPushButton(self)  # 用于滑动的按钮
        self._slider.setFixedSize(28, 28)
        self._slider.setStyleSheet(
            """
            QPushButton {
                border-radius: 14px;
                background-color: #999999;
            }
        """
        )
        self._slider.move(2, 2)  # 初始位置

        # 添加状态文本标签
        self._label = QLabel("OFF", self)
        self._label.setStyleSheet(
            """
                    QLabel {
                        color: #999999;
                        font-weight: bold;
                    }
                """
        )
        self._label.setFixedSize(75, 30)
        self._label.move(75, 0)  # 初始位置为中间位置

        # 动画效果
        self.animation = QPropertyAnimation(self._slider, b"pos")
        self.animation.setDuration(200)  # 动画持续时间

        # 点击事件切换开关
        self.clicked.connect(self.toggle)
        self.toggle()

    def toggle(self):
        if self.isChecked():
            self.animation.setEndValue(QPoint(120, 2))  # 开关打开时滑块的位置
            self._label.setText(self.open_text)  # 更新文本为 ON
            self._label.move(20, 0)  # 保持文本在中间位置
            self.changed.emit(self.open_value)
        else:
            self.animation.setEndValue(QPoint(2, 2))  # 开关关闭时滑块的位置
            self._label.setText(self.close_text)  # 更新文本为 OFF
            self._label.move(70, 0)  # 保持文本在中间位置
            self.changed.emit(self.close_value)
        self.animation.start()
