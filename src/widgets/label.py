from PySide6.QtWidgets import QLabel
from PySide6.QtCore import Signal
from PySide6.QtGui import QMouseEvent


class Label(QLabel):
    clicked = Signal(QMouseEvent)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)

    def mousePressEvent(self, event:QMouseEvent):
        self.clicked.emit(event)
        return super().mousePressEvent(event)
