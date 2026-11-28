"""High-contrast light theme for projector (beamer) use on a white wall.

Design requirements from the owner: light colorized look, strong contrast,
3 px colored border strokes around each card, large readable controls.
"""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

ACCENTS = {
    "blue": "#0057C2",
    "green": "#007A3D",
    "red": "#C21807",
    "orange": "#C25E00",
    "purple": "#6A28B8",
    "teal": "#007582",
    "magenta": "#B0127C",
    "slate": "#33415C",
}

APP_STYLESHEET = """
QMainWindow, QTabWidget::pane, QWidget#Root {
    background: #F4F3EE;
}
QWidget {
    color: #15181D;
    font-size: 15px;
}
QLabel#HeaderTitle {
    font-size: 30px;
    font-weight: 800;
}
QLabel#CardTitle {
    font-size: 19px;
    font-weight: 700;
}
QLabel#BigValue {
    font-size: 34px;
    font-weight: 800;
}
QPushButton {
    background: #FFFFFF;
    border: 2px solid #6B7280;
    border-radius: 8px;
    padding: 9px 14px;
    font-weight: 600;
    min-height: 26px;
}
QPushButton:hover { border-color: #15181D; }
QPushButton:pressed { background: #E4E7EC; }
QPushButton:disabled { color: #9AA1AB; border-color: #C9CED6; background: #F1F2F4; }
QPushButton:checked {
    background: #0057C2;
    border-color: #003C86;
    color: #FFFFFF;
}
QPushButton#PowerOn {
    background: #007A3D; border-color: #00592C; color: white; font-size: 17px;
}
QPushButton#Standby {
    background: #C21807; border-color: #8E1205; color: white; font-size: 17px;
}
QPushButton#Danger {
    background: #C21807; border-color: #8E1205; color: white; font-weight: 800;
}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    background: #FFFFFF;
    border: 2px solid #6B7280;
    border-radius: 6px;
    padding: 6px 8px;
}
QSlider::groove:horizontal {
    height: 10px; border-radius: 5px; background: #C9CED6;
}
QSlider::handle:horizontal {
    width: 26px; margin: -9px 0; border-radius: 13px;
    background: #0057C2; border: 2px solid #003C86;
}
QSlider::groove:vertical {
    width: 10px; border-radius: 5px; background: #C9CED6;
}
QSlider::handle:vertical {
    height: 26px; margin: 0 -9px; border-radius: 13px;
    background: #6A28B8; border: 2px solid #4A1C80;
}
QTabBar::tab {
    background: #E4E7EC;
    border: 2px solid #6B7280;
    border-bottom: none;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    padding: 10px 22px;
    font-size: 16px;
    font-weight: 700;
    margin-right: 4px;
}
QTabBar::tab:selected {
    background: #FFFFFF;
    border-color: #15181D;
}
QPlainTextEdit {
    background: #FFFFFF;
    border: 2px solid #6B7280;
    border-radius: 6px;
    font-family: Consolas, monospace;
    font-size: 13px;
}
"""


class Card(QFrame):
    """A titled white panel with a 3 px accent-colored border."""

    def __init__(self, title: str, accent: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        color = ACCENTS.get(accent, accent)
        self.setObjectName("Card")
        self.setStyleSheet(
            f"QFrame#Card {{ background: #FFFFFF; border: 3px solid {color};"
            f" border-radius: 14px; }}"
        )
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(16, 12, 16, 14)
        self._layout.setSpacing(10)
        title_label = QLabel(title)
        title_label.setObjectName("CardTitle")
        title_label.setStyleSheet(f"color: {color}; border: none;")
        self._layout.addWidget(title_label)

    def body(self) -> QVBoxLayout:
        return self._layout
