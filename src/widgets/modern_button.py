"""Flat, high-contrast button styles for toolbars and lists."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton

_THEMES: dict[str, tuple[str, str, str]] = {
    "teal": ("#0d9488", "#0f766e", "#115e59"),
    "violet": ("#7c3aed", "#6d28d9", "#5b21b6"),
    "blue": ("#2563eb", "#1d4ed8", "#1e40af"),
    "rose": ("#e11d48", "#be123c", "#9f1239"),
    "slate": ("#475569", "#334155", "#1e293b"),
    "amber": ("#d97706", "#b45309", "#92400e"),
    "emerald": ("#059669", "#047857", "#065f46"),
    "sky": ("#0284c7", "#0369a1", "#075985"),
    "indigo": ("#4f46e5", "#4338ca", "#3730a3"),
    "cyan": ("#0891b2", "#0e7490", "#155e75"),
}


def apply_modern_button(btn: QPushButton, variant: str = "slate") -> None:
    bg, hover, pressed = _THEMES.get(variant, _THEMES["slate"])
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setStyleSheet(
        f"""
QPushButton {{
    min-height: 19px;
    padding: 3px 10px;
    border: none;
    border-radius: 6px;
    font-size: 12px;
    font-weight: 600;
    color: #ffffff;
    background-color: {bg};
}}
QPushButton:hover {{ background-color: {hover}; }}
QPushButton:pressed {{ background-color: {pressed}; }}
QPushButton:disabled {{ background-color: #94a3b8; color: #e2e8f0; }}
"""
    )
