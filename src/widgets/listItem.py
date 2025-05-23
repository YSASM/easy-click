import uuid
from PySide6.QtWidgets import QMainWindow, QListWidgetItem
from PySide6.QtCore import Signal

from src.widgets.page import Page


class ListItem(QListWidgetItem):
    open_page_signal = Signal(QMainWindow)

    def __init__(self, page: Page, text, *args, **kwargs):
        super().__init__(text, *args, **kwargs)
        self.setText(text)
        self.page = page
        self.id = uuid.uuid4()
