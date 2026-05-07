"""脚本 DSL 编辑器：语法高亮、行号、命令与图片名补全（深色主题与圆角补全列表）。"""

from __future__ import annotations

import os
import re
from typing import Callable

from PySide6.QtCore import QEvent, QModelIndex, QRect, QSize, Qt, QRegularExpression, QStringListModel, QTimer
from PySide6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QTextBlock,
    QTextCharFormat,
    QTextCursor,
    QTextFormat,
    QSyntaxHighlighter,
)
from PySide6.QtWidgets import (
    QCompleter,
    QPlainTextEdit,
    QSizePolicy,
    QTextEdit,
    QWidget,
)

# 与 vm.py 中指令对齐
SCRIPT_COMMANDS = (
    "BACK",
    "BREAK",
    "CALC",
    "CLICK",
    "CONT",
    "END",
    "END_FOR",
    "END_IF",
    "FIND_IMAGE",
    "FOR",
    "GO",
    "HAS_IMAGE",
    "HOME",
    "IF",
    "ELSE_IF",
    "ELSE",
    "IMPORT",
    "INFO",
    "LOG",
    "ERROR",
    "WARN",
    "RES",
    "PYTHON_RUN",
    "RANDOM",
    "SET",
    "START",
    "SWIP",
    "TAG",
    "WAIT",
    "WAIT_IMAGE",
)

SCRIPT_SUB_KEYWORDS = frozenset(
    {
        "THEN",
        "TIME_OUT",
        "PASS",
        "RANGE",
        "x",
        "y",
        "+",
        "-",
        "*",
        "/",
        "==",
        "!=",
        ">",
        ">=",
        "<",
        "<=",
    }
)


class _ScriptSyntaxHighlighter(QSyntaxHighlighter):
    def __init__(self, doc):
        super().__init__(doc)
        self._fmts = {
            "keyword": self._fmt("#569cd6"),
            "subkw": self._fmt("#c586c0"),
            "number": self._fmt("#b5cea8"),
            "string": self._fmt("#ce9178"),
            "comment": self._fmt("#6a9955", italic=True),
            "operator": self._fmt("#d4d4d4"),
        }
        self._re_comment = QRegularExpression(r"#.*$")
        self._re_string = QRegularExpression(r'"[^"]*"|\'[^\']*\'')

    @staticmethod
    def _fmt(color: str, *, italic: bool = False) -> QTextCharFormat:
        f = QTextCharFormat()
        f.setForeground(QColor(color))
        if italic:
            f.setFontItalic(True)
        return f

    def highlightBlock(self, text: str):
        it = self._re_comment.globalMatch(text)
        while it.hasNext():
            m = it.next()
            self.setFormat(m.capturedStart(), m.capturedLength(), self._fmts["comment"])

        code = text.split("#", 1)[0]

        it = self._re_string.globalMatch(code)
        while it.hasNext():
            m = it.next()
            self.setFormat(m.capturedStart(), m.capturedLength(), self._fmts["string"])

        parts = code.split()
        offset = 0
        for i, tok in enumerate(parts):
            pos = code.find(tok, offset)
            if pos < 0:
                break
            fmt = None
            if i == 0 and tok.upper() in SCRIPT_COMMANDS:
                fmt = self._fmts["keyword"]
            elif tok.upper() in SCRIPT_SUB_KEYWORDS:
                fmt = self._fmts["subkw"]
            elif re.fullmatch(r"-?\d+\.?\d*", tok):
                fmt = self._fmts["number"]
            elif tok in ("==", "!=", ">", ">=", "<", "<=", "|"):
                fmt = self._fmts["operator"]
            if fmt:
                self.setFormat(pos, len(tok), fmt)
            offset = pos + len(tok)


class _LineNumberArea(QWidget):
    def __init__(self, editor: "ModernScriptEditor"):
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self):
        return QSize(self._editor._line_number_area_width(), 0)

    def paintEvent(self, event):
        self._editor._line_number_area_paint_event(event)


class ModernScriptEditor(QPlainTextEdit):
    """深色主题、行号、DSL 高亮、命令与动态图片名补全。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._image_provider: Callable[[], list[str]] | None = None
        self._setup_ui()
        _ScriptSyntaxHighlighter(self.document())
        self._setup_completer()

        self._line_number_area = _LineNumberArea(self)
        self.blockCountChanged.connect(self._update_line_number_area_width)
        self.updateRequest.connect(self._update_line_number_area)
        self.cursorPositionChanged.connect(self._highlight_current_line)
        self.textChanged.connect(self._schedule_completion)

        self._complete_timer = QTimer(self)
        self._complete_timer.setSingleShot(True)
        self._complete_timer.setInterval(50)
        self._complete_timer.timeout.connect(self._maybe_auto_complete)
        self._completion_arrow_used = False
        self._completion_popup_prefix: str | None = None

        self._update_line_number_area_width()
        self._highlight_current_line()

    def _setup_ui(self):
        font = QFont()
        for fam in ("Cascadia Code", "JetBrains Mono", "Consolas", "Courier New"):
            font.setFamily(fam)
            if font.exactMatch():
                break
        font.setFixedPitch(True)
        font.setPointSize(11)
        self.setFont(font)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * 4)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.viewport().setCursor(Qt.CursorShape.IBeamCursor)
        self.setStyleSheet(
            """
            QPlainTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #3c3c3c;
                border-radius: 10px;
                padding: 8px 12px 8px 8px;
                selection-background-color: #264f78;
                selection-color: #ffffff;
            }
            """
        )

    def set_image_completion_provider(self, fn: Callable[[], list[str]] | None):
        """返回当前脚本目录 images 下文件名列表（如 xxx.png）；补全词库会同时加入无后缀名 xxx。"""
        self._image_provider = fn

    def _all_completion_strings(self) -> list[str]:
        base = list(SCRIPT_COMMANDS) + list(SCRIPT_SUB_KEYWORDS)
        if self._image_provider:
            try:
                names = list(self._image_provider())
                base.extend(names)
                for s in names:
                    stem, ext = os.path.splitext(s)
                    if ext.lower() == ".png" and stem:
                        base.append(stem)
            except Exception:
                pass
        seen: set[str] = set()
        out: list[str] = []
        for s in base:
            if s not in seen:
                seen.add(s)
                out.append(s)
        return out

    def _setup_completer(self):
        self._completion_model = QStringListModel()
        # 父对象必须是编辑器本身：挂在 viewport 上时部分环境下会吞掉按键，导致无法输入
        self._completer = QCompleter(self._completion_model, self)
        self._completer.setWidget(self)
        self._completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self._completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._completer.setFilterMode(Qt.MatchFlag.MatchStartsWith)
        self._completer.setMaxVisibleItems(14)
        popup = self._completer.popup()
        popup.setStyleSheet(
            """
            QListView {
                background-color: #252526;
                color: #d4d4d4;
                border: 1px solid #454545;
                border-radius: 10px;
                padding: 6px;
                outline: none;
                font-size: 12px;
            }
            QListView::item {
                padding: 6px 12px;
                border-radius: 6px;
                min-height: 24px;
            }
            QListView::item:selected {
                background-color: #094771;
                color: #ffffff;
            }
            QListView::item:hover {
                background-color: #2a2d2e;
            }
            """
        )
        self._completer.activated[str].connect(self._insert_completion)
        self._refresh_completion_model()
        popup.installEventFilter(self)

    def eventFilter(self, watched, event):
        """列表获得焦点时，方向键/回车不会进 QPlainTextEdit，在此同步「已选」与回车补全。"""
        popup = self._completer.popup()
        if watched is popup and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
                self._completion_arrow_used = True
            elif key in (Qt.Key.Key_Enter, Qt.Key.Key_Return):
                if self._completion_arrow_used and self._accept_popup_completion():
                    return True
        return super().eventFilter(watched, event)

    def _refresh_completion_model(self):
        self._completion_model.setStringList(self._all_completion_strings())

    def refresh_completion(self):
        """图片列表等变更后刷新补全词库。"""
        self._refresh_completion_model()

    def focusInEvent(self, event):
        self._refresh_completion_model()
        super().focusInEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self._line_number_area.setGeometry(
            QRect(cr.left(), cr.top(), self._line_number_area_width(), cr.height())
        )

    def _line_number_area_width(self) -> int:
        digits = max(2, len(str(max(1, self.blockCount()))))
        return 8 + self.fontMetrics().horizontalAdvance("9") * digits

    def _update_line_number_area_width(self, _new_count: int = 0):
        self.setViewportMargins(self._line_number_area_width(), 0, 0, 0)

    def _update_line_number_area(self, rect: QRect, dy: int):
        if dy:
            self._line_number_area.scroll(0, dy)
        else:
            self._line_number_area.update(
                0, rect.y(), self._line_number_area.width(), rect.height()
            )

    def _line_number_area_paint_event(self, event):
        painter = QPainter(self._line_number_area)
        painter.fillRect(event.rect(), QColor("#252526"))
        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = round(
            self.blockBoundingGeometry(block).translated(self.contentOffset()).top()
        )
        bottom = top + round(self.blockBoundingRect(block).height())
        width = self._line_number_area.width()
        painter.setPen(QColor("#858585"))
        painter.setFont(self.font())
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                num = str(block_number + 1)
                painter.drawText(
                    0,
                    top,
                    width - 6,
                    self.fontMetrics().height(),
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                    num,
                )
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            block_number += 1

    def _highlight_current_line(self):
        extra = QTextEdit.ExtraSelection()
        extra.format.setBackground(QColor("#2d2d2d"))
        extra.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
        extra.cursor = self.textCursor()
        extra.cursor.clearSelection()
        self.setExtraSelections([extra])

    def _completion_prefix(self) -> str:
        cur = self.textCursor()
        col = cur.positionInBlock()
        line = cur.block().text()[:col]
        if not line:
            return ""
        i = len(line) - 1
        while i >= 0 and line[i].isspace():
            i -= 1
        if i < 0:
            return ""
        j = i
        while j >= 0 and not line[j].isspace():
            j -= 1
        return line[j + 1 : i + 1]

    def _schedule_completion(self):
        self._complete_timer.start()

    def _completion_popup_rect(self) -> QRect:
        # cursorRect 相对 viewport；QCompleter.setWidget(self) 时 complete(rect) 需相对 self
        cr = self.cursorRect()
        tl = self.viewport().mapTo(self, cr.topLeft())
        cr = QRect(tl, cr.size())
        sb = self._completer.popup().verticalScrollBar().sizeHint().width()
        col = self._completer.popup().sizeHintForColumn(0)
        cr.setWidth(max(320, col + sb + 16))
        return cr

    def _maybe_auto_complete(self):
        prefix = self._completion_prefix()
        popup = self._completer.popup()
        was_visible = popup.isVisible()
        last_prefix = self._completion_popup_prefix

        if len(prefix) < 1:
            popup.hide()
            self._completion_arrow_used = False
            self._completion_popup_prefix = None
            return
        # 同前缀防抖再次进入时勿 setStringList，否则会清空列表选中行，导致回车取不到项
        if not was_visible or last_prefix != prefix:
            self._refresh_completion_model()
        self._completer.setCompletionPrefix(prefix)
        if self._completer.completionCount() == 0:
            self._completer.setFilterMode(Qt.MatchFlag.MatchContains)
            self._completer.setCompletionPrefix(prefix)
        if self._completer.completionCount() == 0:
            self._completer.setFilterMode(Qt.MatchFlag.MatchStartsWith)
            popup.hide()
            self._completion_arrow_used = False
            self._completion_popup_prefix = None
            return
        # 定时器晚于方向键触发时，不能把「已用上下键」清掉：仅在新开弹窗或前缀变化时重置
        if not was_visible or last_prefix != prefix:
            self._completion_arrow_used = False
        self._completion_popup_prefix = prefix
        self._completer.complete(self._completion_popup_rect())
        self._completer.setFilterMode(Qt.MatchFlag.MatchStartsWith)

    @staticmethod
    def _dsl_line_is_comment(text: str) -> bool:
        return bool(text.strip()) and re.match(r"^\s*#", text) is not None

    @staticmethod
    def _dsl_comment_line(text: str) -> str:
        """在缩进后插入 '# '；空行写成 '#'；已为注释的行不重复追加。"""
        if not text.strip():
            return "#"
        if re.match(r"^\s*#", text):
            return text
        m = re.match(r"^(\s*)(.*)$", text)
        if not m:
            return f"# {text}"
        return f"{m.group(1)}# {m.group(2)}"

    @staticmethod
    def _dsl_uncomment_line(text: str) -> str:
        m = re.match(r"^(\s*)#\s?", text)
        if m:
            return m.group(1) + text[m.end() :]
        return text

    def _toggle_block_comment(self) -> None:
        """选中多行或当前行：Ctrl+/ 切换行首（缩进后）'#' 注释。"""
        cur = self.textCursor()
        doc = cur.document()
        anchor, pos = cur.anchor(), cur.position()
        sel_a, sel_b = (anchor, pos) if anchor <= pos else (pos, anchor)

        start_block = doc.findBlock(sel_a)
        end_block = doc.findBlock(sel_b)
        first_bn = start_block.blockNumber()
        last_bn = end_block.blockNumber()

        rows: list[tuple[QTextBlock, str]] = []
        b = start_block
        while b.isValid() and b.blockNumber() <= last_bn:
            rows.append((b, b.text()))
            b = b.next()

        nonempty = [t for _, t in rows if t.strip()]
        should_uncomment = bool(nonempty) and all(
            self._dsl_line_is_comment(t) for t in nonempty
        )

        cur.beginEditBlock()
        try:
            for block, old in reversed(rows):
                new_line = (
                    self._dsl_uncomment_line(old)
                    if should_uncomment
                    else self._dsl_comment_line(old)
                )
                c = QTextCursor(block)
                c.movePosition(QTextCursor.MoveOperation.StartOfBlock)
                c.movePosition(
                    QTextCursor.MoveOperation.EndOfBlock,
                    QTextCursor.MoveMode.KeepAnchor,
                )
                c.removeSelectedText()
                c.insertText(new_line)
        finally:
            cur.endEditBlock()

        b0 = doc.findBlockByNumber(first_bn)
        b1 = doc.findBlockByNumber(last_bn)
        if not b0.isValid() or not b1.isValid():
            return
        out = QTextCursor(doc)
        out.setPosition(b0.position())
        out.setPosition(
            b1.position() + len(b1.text()),
            QTextCursor.MoveMode.KeepAnchor,
        )
        self.setTextCursor(out)

    def insert_line_after_cursor(self, text: str) -> None:
        """在当前光标所在行之后插入一行脚本（不改变光标所在行的内容）。"""
        line = text.strip()
        if not line:
            return
        cur = self.textCursor()
        cur.beginEditBlock()
        cur.movePosition(QTextCursor.MoveOperation.EndOfBlock)
        cur.insertText("\n" + line)
        cur.endEditBlock()
        self.setTextCursor(cur)
        self.setFocus(Qt.FocusReason.OtherFocusReason)

    def _insert_completion(self, text: str):
        cur = self.textCursor()
        prefix = self._completion_prefix()
        if prefix:
            for _ in range(len(prefix)):
                cur.deletePreviousChar()
        cur.insertText(text)

    def _completion_step_row(self, delta: int) -> None:
        cm = self._completer.completionModel()
        root = QModelIndex()
        n = cm.rowCount(root)
        if n <= 0:
            return
        popup = self._completer.popup()
        cur = self._completer.currentRow()
        if cur < 0:
            ix = popup.currentIndex()
            cur = ix.row() if ix.isValid() else 0
        new_row = max(0, min(n - 1, cur + delta))
        self._completer.setCurrentRow(new_row)
        idx = cm.index(new_row, 0, root)
        if idx.isValid():
            popup.setCurrentIndex(idx)

    def _selected_completion_text(self) -> str | None:
        """当前高亮项的展示文本。勿用 currentCompletion()：在 QPlainTextEdit 上常等同第一项。"""
        popup = self._completer.popup()
        cm = self._completer.completionModel()
        root = QModelIndex()
        idx = popup.currentIndex()
        if idx.isValid():
            m = popup.model()
            if m is not None:
                data = m.data(idx, Qt.ItemDataRole.DisplayRole)
                if data is not None:
                    s = str(data).strip()
                    if s:
                        return s
        row = self._completer.currentRow()
        if 0 <= row < cm.rowCount(root):
            data = cm.data(cm.index(row, 0, root), Qt.ItemDataRole.DisplayRole)
            if data is not None:
                s = str(data).strip()
                if s:
                    return s
        return None

    def _accept_popup_completion(self) -> bool:
        """仅在上键/下键选过项后由回车调用：用当前行替换前缀。"""
        popup = self._completer.popup()
        if not popup.isVisible():
            return False
        text = self._selected_completion_text()
        if not text:
            return False
        popup.hide()
        self._completion_arrow_used = False
        self._completion_popup_prefix = None
        self._insert_completion(text)
        return True

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Slash and (
            event.modifiers()
            & (
                Qt.KeyboardModifier.ControlModifier
                | Qt.KeyboardModifier.MetaModifier
            )
        ):
            self._completer.popup().hide()
            self._completion_arrow_used = False
            self._completion_popup_prefix = None
            self._toggle_block_comment()
            event.accept()
            return

        popup = self._completer.popup()
        if popup.isVisible() and event.key() == Qt.Key.Key_Escape:
            popup.hide()
            self._completion_arrow_used = False
            self._completion_popup_prefix = None
            event.accept()
            return
        if popup.isVisible() and event.key() in (
            Qt.Key.Key_Up,
            Qt.Key.Key_Down,
        ):
            self._completion_arrow_used = True
            self._completion_step_row(1 if event.key() == Qt.Key.Key_Down else -1)
            event.accept()
            return
        if popup.isVisible() and event.key() in (
            Qt.Key.Key_Enter,
            Qt.Key.Key_Return,
        ):
            if self._completion_arrow_used and self._accept_popup_completion():
                event.accept()
                return
            popup.hide()
            self._completion_arrow_used = False
            self._completion_popup_prefix = None
            super().keyPressEvent(event)
            return
        super().keyPressEvent(event)
