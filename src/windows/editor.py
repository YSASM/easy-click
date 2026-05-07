import os
import secrets
import string
import traceback
from io import BytesIO
from pathlib import Path

from PySide6.QtWidgets import (
    QListWidget,
    QWidget,
    QVBoxLayout,
    QPushButton,
    QHBoxLayout,
    QLineEdit,
    QLabel,
    QGridLayout,
    QMessageBox,
    QApplication,
    QProgressDialog,
    QScrollArea,
    QTextEdit,
    QTextBrowser,
)
from PySide6.QtCore import QTimer, Signal, QRect, Qt, QSize, QObject, QThread
from PySide6.QtGui import QPainter, QPen, qRgb, QPixmap, QImageReader

from src.utils import Bean
from src.utils.adb import Adb
from src.utils.uiautomator2Manger import Uiautomator2
from src.widgets.image import Image as ImageView
from src.widgets.listItem import ListItem
from src.widgets.modern_button import apply_modern_button
from src.widgets.script_editor import ModernScriptEditor
from src.widgets.page import Page
from src.windows.scriptRunner import ScriptRunner
from PIL import Image as PILImage

RED = qRgb(255, 0, 0)


def _pil_image_from_png_bytes(data: bytes):
    return PILImage.open(BytesIO(data)).convert("RGBA")


_RANDOM_IMAGE_NAME_CHARS = string.ascii_lowercase + string.digits


def _unique_new_image_png_name(images_dir: str) -> str:
    """生成 6 位随机小写字母与数字组成的文件名，不与目录内已有 png 冲突。"""
    try:
        names = os.listdir(images_dir)
    except OSError:
        names = []
    taken_lower = {n.lower() for n in names}
    for _ in range(2048):
        base = "".join(secrets.choice(_RANDOM_IMAGE_NAME_CHARS) for _ in range(6))
        candidate = f"{base}.png"
        if candidate.lower() not in taken_lower:
            return candidate
    raise RuntimeError("无法生成唯一截图文件名")


def _load_fast_thumbnail(path: str, max_side: int = 100) -> QPixmap:
    """
    读取低质量缩略图：优先用 QImageReader 直接按目标尺寸解码，避免加载大图导致卡顿。
    """
    reader = QImageReader(path)
    try:
        sz = reader.size()
        if not sz.isEmpty():
            w, h = sz.width(), sz.height()
            if w > 0 and h > 0:
                if w >= h:
                    tw, th = max_side, max(1, int(max_side * h / w))
                else:
                    th, tw = max_side, max(1, int(max_side * w / h))
                reader.setScaledSize(QSize(tw, th))
    except Exception:
        pass
    img = reader.read()
    if img.isNull():
        pm = QPixmap(path)
        if not pm.isNull():
            return pm.scaled(
                max_side,
                max_side,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation,
            )
        return QPixmap()
    return QPixmap.fromImage(img)


class _ScreenshotWorker(QObject):
    finished = Signal(bytes)
    failed = Signal(str)

    def __init__(self, address: str):
        super().__init__()
        self.address = address

    def run(self):
        try:
            u2 = Uiautomator2(self.address)
            u2.connect()
            pil = u2.screenshot_pillow()
            buf = BytesIO()
            pil.save(buf, format="PNG")
            self.finished.emit(buf.getvalue())
        except Exception as e:
            self.failed.emit(str(e) or traceback.format_exc())


class _ScriptFileLoadWorker(QObject):
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, path: str):
        super().__init__()
        self._path = path

    def run(self):
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                self.finished.emit(f.read())
        except Exception as e:
            self.failed.emit(str(e))


class Drawing(QWidget):
    def __init__(self, parent=None):
        super(Drawing, self).__init__(parent)
        self.resize(600, 400)
        self.setWindowTitle("拖拽绘制矩形")
        self.rect = None

    # 重写绘制函数
    def paintEvent(self, event):
        # 初始化绘图工具
        qp = QPainter()
        # 开始在窗口绘制
        qp.begin(self)
        # 自定义画点方法
        if self.rect:
            self.drawRect(qp)
        # 结束在窗口的绘制
        qp.end()

    def drawRect(self, qp: QPainter):
        # 创建红色，宽度为4像素的画笔
        pen = QPen()
        pen.setColor(RED)
        pen.setWidth(4)
        qp.setPen(pen)
        qp.drawRect(*self.rect)

    # 重写三个时间处理
    def mousePressEvent(self, event):
        self.rect = (event.x(), event.y(), 0, 0)

    def mouseReleaseEvent(self, event):
        if self.rect is None:
            return
        x0, y0, w, h = self.rect
        x1, y1 = x0 + w, y0 + h
        left, top = min(x0, x1), min(y0, y1)
        rw, rh = abs(w), abs(h)
        self.rect = (left, top, rw, rh)
        self.update()

    def mouseMoveEvent(self, event):
        if self.rect is None:
            return
        start_x, start_y = self.rect[0:2]
        self.rect = (start_x, start_y, event.x() - start_x, event.y() - start_y)
        self.update()


class GetXYWindow(Page):
    getted = Signal(list)

    def __init__(self, dir, address):
        super().__init__()
        self.dir = dir
        self.address = address
        self.setWindowTitle("取点")
        self.resize(420, 100)
        self._thread = None
        self._build_loading_ui()
        self._start_screenshot_thread()

    def _build_loading_ui(self):
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        lo = QVBoxLayout(central_widget)
        lo.addWidget(QLabel("正在连接设备并截取屏幕…"))

    def _start_screenshot_thread(self):
        self._thread = QThread(self)
        self._screenshot_worker = _ScreenshotWorker(self.address)
        self._screenshot_worker.moveToThread(self._thread)
        self._thread.started.connect(self._screenshot_worker.run)
        self._screenshot_worker.finished.connect(self._on_screenshot_ready)
        self._screenshot_worker.failed.connect(self._on_screenshot_failed)
        self._screenshot_worker.finished.connect(self._thread.quit)
        self._screenshot_worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._screenshot_worker.deleteLater)
        self._thread.start()

    def _on_screenshot_failed(self, msg: str):
        QMessageBox.warning(self, "取点失败", msg)
        self.close()

    def _on_screenshot_ready(self, png_bytes: bytes):
        pil = _pil_image_from_png_bytes(png_bytes)
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        v_box = QGridLayout(central_widget)
        self.show_image = ImageView(pil)
        v_box.addWidget(self.show_image, 0, 0)
        self.show_image.clicked.connect(self.on_click)
        w, h = self.show_image.image.width(), self.show_image.image.height()
        self.resize(min(w + 48, 1400), min(h + 80, 900))
        self._page_center_on_screen()

    def on_click(self, event):
        xy = [event.x(), event.y()]
        self.getted.emit(xy)
        self.close()

    def closeEvent(self, event):
        t = getattr(self, "_thread", None)
        if t is not None:
            try:
                if t.isRunning():
                    t.quit()
                    t.wait(2000)
            except RuntimeError:
                pass
        return super().closeEvent(event)


class CutImageWindow(Page):
    def __init__(self, dir, address, replace_filename=None):
        super().__init__()
        self.dir = dir
        self.address = address
        self.replace_filename = replace_filename
        self.update_image_list = lambda: None
        self._thread = None
        title = "重新截图" if replace_filename else "截图"
        self.setWindowTitle(title)
        self.resize(420, 100)
        self._build_loading_ui()
        self._start_screenshot_thread()

    def _build_loading_ui(self):
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        lo = QVBoxLayout(central_widget)
        lo.addWidget(QLabel("正在连接设备并截取屏幕，请稍候…"))

    def _start_screenshot_thread(self):
        self._thread = QThread(self)
        self._screenshot_worker = _ScreenshotWorker(self.address)
        self._screenshot_worker.moveToThread(self._thread)
        self._thread.started.connect(self._screenshot_worker.run)
        self._screenshot_worker.finished.connect(self._on_screenshot_ready)
        self._screenshot_worker.failed.connect(self._on_screenshot_failed)
        self._screenshot_worker.finished.connect(self._thread.quit)
        self._screenshot_worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._screenshot_worker.deleteLater)
        self._thread.start()

    def _on_screenshot_failed(self, msg: str):
        QMessageBox.warning(self, "截图失败", msg)
        self.close()

    def _on_screenshot_ready(self, png_bytes: bytes):
        pil = _pil_image_from_png_bytes(png_bytes)
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        v_box = QGridLayout(central_widget)
        self.show_image = ImageView(pil)
        self.cut_box = Drawing()
        self.cut_box.setFixedSize(self.show_image.pixmap().size())
        v_box.addWidget(self.show_image, 0, 0)
        v_box.addWidget(self.cut_box, 0, 0)
        self.cut_box.raise_()
        ok = QPushButton("确定保存选区")
        apply_modern_button(ok, "emerald")
        v_box.addWidget(ok)
        ok.clicked.connect(self.on_click_ok)
        hint = QLabel("拖拽框选要保存的区域")
        v_box.addWidget(hint)
        w, h = self.show_image.image.width(), self.show_image.image.height()
        self.resize(min(w + 48, 1400), min(h + 140, 900))
        self._page_center_on_screen()

    def on_click_ok(self):
        if self.cut_box.rect is None:
            QMessageBox.warning(self, "提示", "请先拖拽框选截图区域")
            return
        x, y, w, h = self.cut_box.rect
        if w <= 0 or h <= 0:
            QMessageBox.warning(self, "提示", "框选区域无效，请重新拖拽")
            return
        pm = self.show_image.image
        rect = QRect(int(x), int(y), int(w), int(h))
        if (
            rect.x() < 0
            or rect.y() < 0
            or rect.x() + rect.width() > pm.width()
            or rect.y() + rect.height() > pm.height()
        ):
            QMessageBox.warning(self, "提示", "截取区域超出屏幕范围")
            return

        cropped_pixmap = pm.copy(rect)
        images_dir = os.path.join(self.dir, "images")
        os.makedirs(images_dir, exist_ok=True)
        if self.replace_filename:
            save_path = os.path.join(images_dir, self.replace_filename)
        else:
            save_path = os.path.join(images_dir, _unique_new_image_png_name(images_dir))
        cropped_pixmap.save(save_path)
        self.update_image_list()
        self.close()

    def closeEvent(self, event):
        t = getattr(self, "_thread", None)
        if t is not None:
            try:
                if t.isRunning():
                    t.quit()
                    t.wait(2000)
            except RuntimeError:
                pass
        return super().closeEvent(event)


class ImagePreviewWindow(Page):
    """大图预览：按窗口可视区域保持宽高比缩放（宽或高贴边）。"""

    def __init__(self, image_path: str):
        super().__init__()
        self._image_path = image_path
        base = os.path.basename(image_path)
        self.setWindowTitle(f"预览 - {base}")
        self.resize(880, 720)
        self._full_pm = QPixmap(image_path)
        cw = QWidget(self)
        self.setCentralWidget(cw)
        self._root_layout = QVBoxLayout(cw)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._label = QLabel()
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if self._full_pm.isNull():
            self._label.setText("无法加载图片")
        self._scroll.setWidget(self._label)
        self._root_layout.addWidget(self._scroll, 1)
        self._close_btn = QPushButton("关闭")
        apply_modern_button(self._close_btn, "slate")
        self._close_btn.clicked.connect(self.close)
        self._root_layout.addWidget(self._close_btn)

    def showEvent(self, event):
        super().showEvent(event)
        self._refit_pixmap()
        QTimer.singleShot(0, self._refit_pixmap)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._refit_pixmap()

    def _refit_pixmap(self):
        if self._full_pm.isNull():
            return
        vp = self._scroll.viewport().size()
        pad = 8
        aw = max(vp.width() - pad * 2, 1)
        ah = max(vp.height() - pad * 2, 1)
        if aw < 8 or ah < 8:
            return
        scaled = self._full_pm.scaled(
            aw,
            ah,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._label.setPixmap(scaled)
        self._label.setMinimumSize(scaled.size())


class ScriptEditoImagesWidgetItem(ListItem):
    def __init__(self, page: Page, text, dir, *args, **kwargs):
        super().__init__(page, text, *args, **kwargs)
        self.widget = QWidget()
        self.layout = QHBoxLayout(self.widget)
        self.layout.setContentsMargins(0, 0, 0, 0)
        # 缩略图：低质量快速加载（避免加载原图导致列表卡顿）
        image = QLabel()
        image.setFixedSize(QSize(100, 100))
        image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        image.setStyleSheet(
            "QLabel { background: #f1f5f9; border: 1px solid #e2e8f0; border-radius: 8px; }"
        )
        pm = _load_fast_thumbnail(os.path.join(dir, "images", text), 100)
        if not pm.isNull():
            image.setPixmap(
                pm.scaled(
                    96,
                    96,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.FastTransformation,
                )
            )
        self.name = QLabel(text)
        self.name.setFixedSize(QSize(80, 20))
        self.preview_button = QPushButton("预览")
        self.change_name_button = QPushButton("修改名称")
        self.click_button = QPushButton("点击图片")
        self.add_button = QPushButton("寻找图片")
        self.re_cut_image_button = QPushButton("重新截图")
        self.delete_button = QPushButton("删除图片")
        apply_modern_button(self.preview_button, "indigo")
        apply_modern_button(self.change_name_button, "slate")
        apply_modern_button(self.add_button, "blue")
        apply_modern_button(self.click_button, "teal")
        apply_modern_button(self.re_cut_image_button, "amber")
        apply_modern_button(self.delete_button, "rose")
        self.layout.addWidget(image)
        self.layout.addWidget(self.preview_button)
        self.layout.addWidget(self.name)
        self.layout.addWidget(self.change_name_button)
        self.layout.addWidget(self.add_button)
        self.layout.addWidget(self.click_button)
        self.layout.addWidget(self.re_cut_image_button)
        self.layout.addWidget(self.delete_button)


# 创建一个主窗口类，继承自 QMainWindow
class ChangeNameWindow(Page):
    change = Signal(str)

    def __init__(self,name):
        super().__init__()  # 调用父类 QMainWindow 的初始化方法
        self.resize(200, 100)  # 设置窗口大小
        self.setWindowTitle("修改名称")  # 设置窗口标题
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        h_box = QHBoxLayout()
        central_widget.setLayout(h_box)
        self.name = QLineEdit(name)
        h_box.addWidget(self.name)
        ok = QPushButton("确定")
        apply_modern_button(ok, "blue")
        h_box.addWidget(ok)
        ok.clicked.connect(self.on_click_ok)

    def on_click_ok(self):
        name = self.name.text()
        self.change.emit(name)
        self.close()


def _project_readme_path() -> Path:
    return Path(__file__).resolve().parents[2] / "README.md"


class TutorialWindow(Page):
    """展示项目 README.md，供编辑页「教程」按钮打开。"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("脚本教程")
        self.resize(760, 680)
        central = QWidget(self)
        self.setCentralWidget(central)
        lo = QVBoxLayout(central)
        body = QTextBrowser(self)
        body.setOpenExternalLinks(True)
        body.setPlaceholderText("正在加载…")
        try:
            text = _project_readme_path().read_text(encoding="utf-8")
        except OSError:
            text = (
                "未找到 README.md。\n\n"
                "请确认程序从项目根目录运行，且存在文件：\n"
                f"{_project_readme_path()}"
            )
        # Qt 的 Markdown 渲染能力取决于版本：优先 setMarkdown，失败则退回纯文本
        try:
            body.setMarkdown(text)
        except Exception:
            body.setPlainText(text)
        body.setStyleSheet(
            """
            QTextBrowser {
                background-color: #fafafa;
                color: #1e293b;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                padding: 12px 14px;
                font-size: 13px;
                font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif;
                line-height: 1.55;
            }
            """
        )
        lo.addWidget(body)
        row = QHBoxLayout()
        row.addStretch()
        close_btn = QPushButton("关闭")
        apply_modern_button(close_btn, "slate")
        close_btn.clicked.connect(self.close)
        row.addWidget(close_btn)
        lo.addLayout(row)


class ScriptEditorWindow(Page):
    def __init__(self, dir):
        super().__init__()
        self.resize(1200, 600)
        self.name = dir.replace("/", "\\").split("\\")[-1]
        self.setWindowTitle(f"编辑-{self.name}")
        self.dir = dir
        self.file = os.path.join(self.dir, "index.txt")
        self.content = ""
        self._script_thread = None
        self._script_worker = None
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.timeout.connect(self._persist_script_file)
        loading = QWidget(self)
        self.setCentralWidget(loading)
        loading_lo = QVBoxLayout(loading)
        loading_lo.addWidget(QLabel("正在加载脚本…"))
        self._start_script_load()

    def _start_script_load(self):
        self._script_thread = QThread(self)
        self._script_worker = _ScriptFileLoadWorker(self.file)
        self._script_worker.moveToThread(self._script_thread)
        self._script_thread.started.connect(self._script_worker.run)
        self._script_worker.finished.connect(self._on_script_file_loaded)
        self._script_worker.failed.connect(self._on_script_file_load_failed)
        self._script_worker.finished.connect(self._script_thread.quit)
        self._script_worker.failed.connect(self._script_thread.quit)
        self._script_thread.finished.connect(self._script_worker.deleteLater)
        self._script_thread.start()

    def _on_script_file_loaded(self, content: str):
        self.content = content
        self.init()

    def _on_script_file_load_failed(self, msg: str):
        QMessageBox.critical(self, "加载脚本失败", msg)
        self.close()

    def closeEvent(self, event):
        if getattr(self, "editor", None) is not None:
            try:
                self._autosave_timer.stop()
                self._persist_script_file()
            except Exception:
                pass
        t = getattr(self, "_script_thread", None)
        if t is not None:
            try:
                if t.isRunning():
                    t.quit()
                    t.wait(2000)
            except RuntimeError:
                pass
        return super().closeEvent(event)

    def _script_image_names_for_completion(self):
        images_dir = os.path.join(self.dir, "images")
        try:
            if not os.path.isdir(images_dir):
                return []
            return sorted(
                n for n in os.listdir(images_dir) if n.lower().endswith(".png")
            )
        except OSError:
            return []

    def init(self):
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        h_box = QHBoxLayout()
        central_widget.setLayout(h_box)

        # 左边栏
        v_box = QVBoxLayout()
        h_box.addLayout(v_box)
        # TAG XXX | 一个标签
        # GOTO XXX | 跳转到 XXX
        # FIND_IMAGE XXX argname 3 | 找到图片 XXX 超时3秒
        # FIND_TEXT XXX argname 3 | 找到文本 XXX
        # CLICK argname | 点击 argname
        # SEND_TEXT "ssdasda" | 输入 XXX
        # WAIT 3 | 等待 3 秒
        Adb.check_adb()
        adb_label = QLabel("设备")
        self.adb_address = QLineEdit(
            Bean.adb_devices[0] if len(Bean.adb_devices) > 0 else ""
        )
        v_box.addWidget(adb_label)
        v_box.addWidget(self.adb_address)
        click_xy_box = QVBoxLayout()
        v_box.addLayout(click_xy_box)

        click_xy_get_box = QHBoxLayout()
        click_xy_box.addLayout(click_xy_get_box)
        

        click_xy_input_box = QHBoxLayout()
        click_xy_label = QLabel("点击坐标")
        
        click_xy_box.addWidget(click_xy_label)
        click_xy_box.addLayout(click_xy_input_box)
        
        click_xy_x_label = QLabel("x:")
        click_xy_y_label = QLabel("y:")
        self.click_xy_x = QLineEdit()
        self.click_xy_y = QLineEdit()
        click_xy_input_box.addWidget(click_xy_x_label)
        click_xy_input_box.addWidget(self.click_xy_x)
        click_xy_input_box.addWidget(click_xy_y_label)
        click_xy_input_box.addWidget(self.click_xy_y)
        click_xy_get_button = QPushButton("获取坐标")
        click_xy_button = QPushButton("插入")
        apply_modern_button(click_xy_get_button, "blue")
        apply_modern_button(click_xy_button, "teal")
        click_xy_input_box.addWidget(click_xy_get_button)
        click_xy_input_box.addWidget(click_xy_button)
        click_xy_button.clicked.connect(self.on_click_click_xy)
        click_xy_get_button.clicked.connect(self.on_click_click_xy_get)
        add_image_box = QHBoxLayout()
        v_box.addLayout(add_image_box)
        add_image_label = QLabel("点击图片")
        add_image_box.addWidget(add_image_label)
        add_image_button = QPushButton("截图")
        apply_modern_button(add_image_button, "sky")
        add_image_box.addWidget(add_image_button)
        self.image_list = QListWidget()
        self.image_list.setStyleSheet(
            """
            QListWidget { 
                height: 200px; 
            }
            QListWidget::item {
                padding: 4px 6px;
                min-height: 28px;
            }
            """
        )
        v_box.addWidget(self.image_list)
        self.update_image_list()

        run_button = QPushButton("运行")
        tutorial_button = QPushButton("教程")
        apply_modern_button(run_button, "violet")
        apply_modern_button(tutorial_button, "sky")
        tools_buttons = QHBoxLayout()
        v_box.addLayout(tools_buttons)
        tools_buttons.addWidget(run_button)
        tools_buttons.addWidget(tutorial_button)
        run_button.clicked.connect(self.on_click_run)
        tutorial_button.clicked.connect(self.on_click_tutorial)

        # 编辑器（DSL 高亮 + 补全）
        self.editor = ModernScriptEditor(self)
        self.editor.textChanged.connect(self._schedule_editor_autosave)
        self.editor.blockSignals(True)
        self.editor.setPlainText(self.content)
        self.editor.blockSignals(False)
        self.editor.setMinimumSize(QSize(480, 420))
        self.editor.set_image_completion_provider(self._script_image_names_for_completion)
        h_box.addWidget(self.editor, 1)
        add_image_button.clicked.connect(self.on_click_add_image)

    def _persist_script_file(self):
        """将当前编辑器内容写入 index.txt（用于自动保存与关闭前冲刷）。"""
        if getattr(self, "editor", None) is None:
            return
        text = self.editor.toPlainText()
        self.content = text
        try:
            with open(self.file, "w", encoding="utf-8") as f:
                f.write(text)
        except OSError as e:
            Bean.cmd_out_list.append(f"脚本保存失败: {self.file}: {e}")

    def _schedule_editor_autosave(self):
        self._autosave_timer.stop()
        self._autosave_timer.start(300)

    def on_changed_device(self, address):
        try:
            sr = ScriptRunner(address, self.name)
            self.open_page(sr)
            sr.start()
        except Exception as e:
            Bean.cmd_out_list.append(str(e))

    def on_click_run(self):
        self._autosave_timer.stop()
        self._persist_script_file()
        sr = ScriptRunner(self.adb_address.text(), self.name, False)
        self.open_page(sr)
        sr.start()

    def on_click_tutorial(self):
        self.open_page(TutorialWindow())

    def on_click_click_xy(self):
        x = self.click_xy_x.text()
        y = self.click_xy_y.text()
        if x == "" or y == "":
            msg = QMessageBox()
            msg.setText("请输入x,y坐标")
            msg.exec_()
            return
        self.editor.insert_line_after_cursor(f"CLICK {x} {y}")

    def on_click_add_image(self):
        try:
            cut_image_window = CutImageWindow(self.dir, self.adb_address.text())
            cut_image_window.update_image_list = self.update_image_list
            self.open_page(cut_image_window)
        except Exception:
            Bean.cmd_out_list.append(traceback.format_exc())

    def on_getted(self, xy):
        self.click_xy_x.setText(str(xy[0]))
        self.click_xy_y.setText(str(xy[1]))

    def on_click_click_xy_get(self):
        try:
            get_xy_window = GetXYWindow(self.dir, self.adb_address.text())
            get_xy_window.getted.connect(self.on_getted)
            self.open_page(get_xy_window)
        except Exception as e:
            Bean.cmd_out_list.append(traceback.format_exc())

    def on_click_image_list_add_image(self, item):
        def func():
            file_name = item.text()
            name = file_name.replace(".png", "")
            self.editor.insert_line_after_cursor(
                f"FIND_IMAGE {file_name} {name}"
            )

        return func

    def on_click_image_list_delete_image(self, item):
        def func():
            fname = item.text()
            r1 = QMessageBox.question(
                self,
                "删除确认",
                f"确定要删除图片「{fname}」吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if r1 != QMessageBox.StandardButton.Yes:
                return
            r2 = QMessageBox.question(
                self,
                "再次确认",
                "删除后无法恢复，是否继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if r2 != QMessageBox.StandardButton.Yes:
                return
            path = os.path.join(self.dir, "images", fname)
            if os.path.isfile(path):
                os.remove(path)
            self.update_image_list()

        return func

    def on_click_re_cut_image(self, item):
        def func():
            try:
                w = CutImageWindow(
                    self.dir, self.adb_address.text(), replace_filename=item.text()
                )
                w.update_image_list = self.update_image_list
                self.open_page(w)
            except Exception:
                Bean.cmd_out_list.append(traceback.format_exc())

        return func

    def on_click_image_list_click_image(self, item):
        def func():
            file_name = item.text()
            name = file_name.replace(".png", "")
            self.editor.insert_line_after_cursor(f"CLICK {name}")

        return func
    
    def on_change_name(self,old):
        def func(new):
            os.rename(os.path.join(self.dir,"images",old), os.path.join(self.dir,"images",new))
            self.update_image_list()
        return func

    def on_click_change_name(self, item):
        def func():
            cnw = ChangeNameWindow(item.text())
            cnw.change.connect(self.on_change_name(item.text()))
            self.open_page(cnw)
        return func

    def on_click_image_preview(self, item):
        def func():
            path = os.path.join(self.dir, "images", item.text())
            if os.path.isfile(path):
                self.open_page(ImagePreviewWindow(path))

        return func

    def update_image_list(self):
        if not hasattr(self, "image_list"):
            return
        images_dir = os.path.join(self.dir, "images")
        try:
            os.makedirs(images_dir, exist_ok=True)
        except OSError:
            pass
        try:
            self.image_list.clear()
            names = sorted(
                n
                for n in os.listdir(images_dir)
                if n.lower().endswith(".png")
            )
            if not names:
                if hasattr(self, "editor"):
                    self.editor.refresh_completion()
                return
            dlg = QProgressDialog("正在加载图片缩略图…", "取消", 0, len(names), self)
            dlg.setWindowModality(Qt.WindowModal)
            dlg.setMinimumDuration(0)
            dlg.setValue(0)
            for i, name in enumerate(names):
                if dlg.wasCanceled():
                    break
                dlg.setValue(i)
                QApplication.processEvents()
                item = ScriptEditoImagesWidgetItem(self, name, self.dir)
                item.change_name_button.clicked.connect(self.on_click_change_name(item))
                item.preview_button.clicked.connect(self.on_click_image_preview(item))
                item.click_button.clicked.connect(
                    self.on_click_image_list_click_image(item)
                )
                item.add_button.clicked.connect(
                    self.on_click_image_list_add_image(item)
                )
                item.re_cut_image_button.clicked.connect(
                    self.on_click_re_cut_image(item)
                )
                item.delete_button.clicked.connect(
                    self.on_click_image_list_delete_image(item)
                )
                self.image_list.addItem(item)
                self.image_list.setItemWidget(item, item.widget)
            dlg.setValue(len(names))
            if hasattr(self, "editor"):
                self.editor.refresh_completion()
        except Exception:
            Bean.cmd_out_list.append(traceback.format_exc())
