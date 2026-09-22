"""Desktop theme: a quiet dark instrument console. Same palette as the project documentation.

Fonts come from the operating system (its UI font and its fixed-width font), so the
application looks native on Windows, Linux and macOS and never asks Qt for a family that is
not installed.
"""
from PyQt6 import QtGui

C = {
    "ground": "#0B1116", "surface": "#111A21", "raised": "#18242D", "sunken": "#070C10",
    "ink": "#E3ECF1", "ink2": "#BCCCD5", "muted": "#8DA1AD", "faint": "#61737E",
    "line": "#22323D", "line2": "#1A2831",
    "accent": "#52C4DE", "signal": "#E08D4C", "good": "#5CBE93", "bad": "#E0603F",
}


def mono(size: float = 10.0, bold: bool = False) -> QtGui.QFont:
    """The system fixed-width font at a point size (Consolas, Menlo, DejaVu Sans Mono...)."""
    f = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.SystemFont.FixedFont)
    f.setPointSizeF(size)
    f.setBold(bold)
    return f


def ui_font(size: float = 10.0) -> QtGui.QFont:
    f = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.SystemFont.GeneralFont)
    f.setPointSizeF(size)
    return f


STYLESHEET = f"""
QMainWindow, QWidget {{ background: {C['ground']}; color: {C['ink']}; }}
QToolTip {{ background: {C['raised']}; color: {C['ink']}; border: 1px solid {C['line']}; padding: 6px; }}

/* toolbar */
QToolBar {{ background: {C['surface']}; border: none; border-bottom: 1px solid {C['line']}; spacing: 4px; padding: 6px 8px; }}
QToolBar::separator {{ width: 1px; background: {C['line']}; margin: 5px 8px; }}
QToolBar QLabel {{ background: transparent; color: {C['muted']}; padding: 0 2px 0 4px; }}
QToolBar QToolButton {{ background: transparent; border: 1px solid transparent; border-radius: 4px; padding: 5px 10px; color: {C['ink2']}; }}
QToolBar QToolButton:hover {{ background: {C['raised']}; border-color: {C['line']}; color: {C['ink']}; }}
QToolBar QToolButton:disabled {{ color: {C['faint']}; }}
QToolButton#primary {{ background: {C['accent']}; border-color: {C['accent']}; color: {C['ground']}; font-weight: 600; padding: 5px 16px; }}
QToolButton#primary:hover {{ background: #6fd0e6; border-color: #6fd0e6; color: {C['ground']}; }}
QToolButton#primary:disabled {{ background: {C['raised']}; border-color: {C['line']}; color: {C['faint']}; }}
QToolButton#danger:enabled {{ color: {C['signal']}; border-color: #4a3322; }}
QToolButton#danger:enabled:hover {{ background: #2a1d12; }}

/* inputs */
QSpinBox, QDoubleSpinBox, QLineEdit, QComboBox {{ background: {C['surface']}; border: 1px solid {C['line']}; border-radius: 4px; padding: 3px 6px; color: {C['ink']}; min-height: 20px; selection-background-color: {C['raised']}; }}
QSpinBox:focus, QDoubleSpinBox:focus, QLineEdit:focus, QComboBox:focus {{ border-color: {C['accent']}; }}
QSpinBox:disabled, QDoubleSpinBox:disabled, QLineEdit:disabled, QComboBox:disabled {{ color: {C['faint']}; background: {C['ground']}; }}
QComboBox QAbstractItemView {{ background: {C['surface']}; color: {C['ink']}; border: 1px solid {C['line']}; selection-background-color: {C['raised']}; outline: none; }}
QCheckBox {{ color: {C['ink2']}; spacing: 8px; }}
QCheckBox::indicator {{ width: 14px; height: 14px; border: 1px solid {C['line']}; border-radius: 3px; background: {C['surface']}; }}
QCheckBox::indicator:checked {{ background: {C['accent']}; border-color: {C['accent']}; }}
QCheckBox::indicator:disabled {{ background: {C['ground']}; }}

/* side panel */
QScrollArea, QScrollArea > QWidget > QWidget {{ background: {C['ground']}; border: none; }}
QLabel[class="section"] {{ color: {C['ink']}; font-weight: 600; padding: 4px 0 6px 0; border-bottom: 1px solid {C['line']}; }}
QLabel[class="hint"] {{ color: {C['faint']}; padding: 2px 0 4px 0; }}
QLabel[class="fieldlabel"] {{ color: {C['muted']}; }}
QLabel[class="fieldlabel"]:disabled {{ color: {C['faint']}; }}

/* tiles and views */
QFrame[class="tile"] {{ background: {C['surface']}; border: 1px solid {C['line']}; border-radius: 6px; }}
QLabel[class="tiletitle"] {{ color: {C['muted']}; background: transparent; }}
QLabel[class="tilevalue"] {{ background: transparent; }}
QLabel[class="tileunit"] {{ color: {C['faint']}; background: transparent; }}
QLabel[class="view"] {{ background: {C['sunken']}; border: 1px solid {C['line']}; border-radius: 6px; color: {C['faint']}; }}
QPlainTextEdit[class="tele"] {{ background: {C['surface']}; border: 1px solid {C['line']}; border-radius: 6px; color: {C['ink2']}; padding: 10px; }}

/* status bar */
QStatusBar {{ background: {C['surface']}; border-top: 1px solid {C['line']}; color: {C['muted']}; }}
QStatusBar QLabel {{ background: transparent; color: {C['muted']}; padding: 0 6px; }}
QProgressBar {{ background: {C['ground']}; border: 1px solid {C['line']}; border-radius: 3px; max-height: 8px; }}
QProgressBar::chunk {{ background: {C['accent']}; border-radius: 2px; }}
QMessageBox {{ background: {C['surface']}; }}
QMessageBox QLabel {{ color: {C['ink']}; }}
QMessageBox QPushButton, QDialog QPushButton {{ background: {C['raised']}; border: 1px solid {C['line']}; border-radius: 4px; padding: 5px 14px; color: {C['ink']}; }}
QMessageBox QPushButton:hover, QDialog QPushButton:hover {{ border-color: {C['accent']}; }}

/* scroll bars: thin, no arrow buttons */
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 8px; margin: 0; }}
QScrollBar::handle {{ background: {C['line']}; border-radius: 4px; min-height: 30px; min-width: 30px; }}
QScrollBar::handle:hover {{ background: {C['faint']}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; border: none; background: none; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}
"""
