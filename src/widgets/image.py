from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QLabel
from PySide6.QtCore import QSize, QThread, Signal, Qt
from PIL import Image as PILImage
from PySide6.QtGui import QMouseEvent

class Image(QLabel):
    clicked = Signal(QMouseEvent)

    def __init__(self, image, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            self._original_size = QSize()
            self._current_thread = None

            self.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.setStyleSheet("background: #f0f0f0;")

            # PIL.Image.Image（含 open/convert 结果）不一定是 ImageFile 子类，勿仅用 ImageFile 判断
            if isinstance(image, PILImage.Image):
                self.image = self.image_to_qimage(image)
            else:
                self.image = QPixmap(image)
            self.setPixmap(self.image)

        except Exception as e:
            print(e)

    def setSize(self, width, height):
        qs = QSize(width, height)
        scaled = self.pixmap().scaled(
            qs,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.setPixmap(scaled)

    def image_to_qimage(self, image: PILImage.Image):
        image = image.convert("RGBA")
        q_image = QImage(image.tobytes("raw","RGBA"), image.size[0], image.size[1], QImage.Format.Format_ARGB32)
        return QPixmap.fromImage(q_image.rgbSwapped())
    

    def mousePressEvent(self, event:QMouseEvent):
        self.clicked.emit(event)
        return super().mousePressEvent(event)
