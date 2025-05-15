from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QLabel
from PySide6.QtCore import QSize, QThread, Signal, Qt

class ImageLoaderThread(QThread):
    """异步图片加载线程"""
    loaded = Signal(QImage)  # 加载成功信号
    failed = Signal()        # 加载失败信号

    def __init__(self, path):
        super().__init__()
        self.image_path = path

    def run(self):
        """线程执行内容"""
        try:
            image = QImage(self.image_path)
            if image.isNull():
                raise ValueError("Invalid image file")
            self.loaded.emit(image)
        except Exception as e:
            print(f"加载错误: {e}")
            self.failed.emit()

class Image(QLabel):
    def __init__(self, path=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._original_size = QSize()
        self._current_thread = None
        
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background: #f0f0f0;")
        
        if path:
            self.load_image(path)

    def setSize(self, width, height):
        """设置显示尺寸并保持比例"""
        qs = QSize(width, height)
        if not self.pixmap().isNull():
            scaled = self.pixmap().scaled(
                qs, 
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.setPixmap(scaled)
        self.setFixedSize(qs)

    def getSize(self):
        """获取原始图片尺寸"""
        return (self._original_size.width(), 
                self._original_size.height())

    def load_image(self, path):
        """同步加载图片"""
        self._load_image_impl(path)

    def load_image_async(self, path):
        """异步加载图片"""
        # 清理正在运行的线程
        if self._current_thread and self._current_thread.isRunning():
            self._current_thread.terminate()
        
        # 显示加载状态
        self.setText("加载中...")
        
        # 创建并启动线程
        self._current_thread = ImageLoaderThread(path)
        self._current_thread.loaded.connect(self._on_image_loaded)
        self._current_thread.failed.connect(self._on_load_failed)
        self._current_thread.finished.connect(self._on_thread_finished)
        self._current_thread.start()

    def _load_image_impl(self, image):
        """通用图片加载逻辑"""
        if isinstance(image, str):
            self.image = QImage(image)
        elif isinstance(image, QImage):
            self.image = image
            
        if self.image.isNull():
            self.setText("无效图片文件")
            return
            
        self._original_size = self.image.size()
        self.setPixmap(QPixmap.fromImage(self.image))

    def _on_image_loaded(self, image):
        """异步加载成功处理"""
        self._load_image_impl(image)
        self.setSize(self.width(), self.height())  # 触发尺寸更新

    def _on_load_failed(self):
        """异步加载失败处理"""
        self.setText("图片加载失败")
        self.setStyleSheet("color: red;")

    def _on_thread_finished(self):
        """线程结束清理"""
        self._current_thread.deleteLater()
        self._current_thread = None

    def resizeEvent(self, event):
        """窗口尺寸变化时保持比例"""
        if not self.pixmap().isNull():
            scaled = self.pixmap().scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.setPixmap(scaled)
        super().resizeEvent(event)