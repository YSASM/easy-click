import uuid
from PySide6.QtWidgets import QListWidgetItem

from src.widgets.page import Page


class ListItem(QListWidgetItem):
    def __init__(self, page: Page, text, *args, **kwargs):
        super().__init__(text, *args, **kwargs)
        self.setText(text)
        self.page = page
        self.id = uuid.uuid4()
