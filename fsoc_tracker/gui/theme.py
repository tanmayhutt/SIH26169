"""Dark instrument-console theme. Same palette as the project documentation."""

C = {
    "ground": "#0A1117", "surface": "#111C24", "raised": "#16242D", "ink": "#E3ECF1", "ink2": "#BCCCD5",
    "muted": "#8DA1AD", "faint": "#6A7F8B", "line": "#22323D", "accent": "#52C4DE", "signal": "#E08D4C", "good": "#5CBE93",
}

STYLESHEET = f"""
QMainWindow, QWidget {{ background: {C['ground']}; color: {C['ink']}; font-family: -apple-system, 'Segoe UI', 'Helvetica Neue', Arial; font-size: 12px; }}
QToolBar {{ background: {C['surface']}; border-bottom: 1px solid {C['line']}; spacing: 6px; padding: 4px; }}
QToolBar QToolButton {{ background: {C['raised']}; border: 1px solid {C['line']}; border-radius: 3px; padding: 5px 10px; color: {C['ink']}; }}
QToolBar QToolButton:hover {{ border-color: {C['accent']}; color: {C['accent']}; }}
QToolBar QToolButton:disabled {{ color: {C['faint']}; }}
QScrollArea {{ background: {C['ground']}; border: none; }}
QLabel[class="section"] {{ color: {C['accent']}; font-family: Menlo, Consolas, monospace; font-size: 10px; letter-spacing: 1px; padding-bottom: 3px; border-bottom: 1px solid {C['line']}; }}
QLabel[class="fieldlabel"] {{ color: {C['muted']}; }}
QLabel[class="view"] {{ background: {C['surface']}; border: 1px solid {C['line']}; border-radius: 3px; }}
QSpinBox, QDoubleSpinBox, QLineEdit, QComboBox {{ background: {C['surface']}; border: 1px solid {C['line']}; border-radius: 3px; padding: 2px 5px; color: {C['ink']}; min-height: 20px; }}
QSpinBox:focus, QDoubleSpinBox:focus, QLineEdit:focus, QComboBox:focus {{ border-color: {C['accent']}; }}
QComboBox QAbstractItemView {{ background: {C['surface']}; color: {C['ink']}; selection-background-color: {C['raised']}; }}
QCheckBox {{ color: {C['ink']}; }}
QCheckBox::indicator {{ width: 14px; height: 14px; border: 1px solid {C['line']}; border-radius: 2px; background: {C['surface']}; }}
QCheckBox::indicator:checked {{ background: {C['accent']}; border-color: {C['accent']}; }}
QPlainTextEdit[class="tele"] {{ background: {C['surface']}; border: 1px solid {C['line']}; border-radius: 3px; color: {C['ink2']}; font-family: Menlo, Consolas, monospace; font-size: 11px; padding: 8px; }}
QStatusBar {{ background: {C['surface']}; border-top: 1px solid {C['line']}; color: {C['muted']}; }}
QProgressBar {{ background: {C['surface']}; border: 1px solid {C['line']}; border-radius: 3px; height: 8px; }}
QProgressBar::chunk {{ background: {C['accent']}; }}
QMessageBox {{ background: {C['surface']}; }}
QScrollBar:vertical {{ background: {C['ground']}; width: 10px; }}
QScrollBar::handle:vertical {{ background: {C['line']}; border-radius: 4px; min-height: 30px; }}
"""

STYLESHEET += f"""
QLabel[class="hint"] {{ color: {C['faint']}; font-size: 11px; padding-bottom: 2px; }}
QFrame[class="tile"] {{ background: {C['surface']}; border: 1px solid {C['line']}; border-radius: 4px; }}
QLabel[class="tiletitle"] {{ color: {C['muted']}; font-family: Menlo, Consolas, monospace; font-size: 9px; letter-spacing: 1px; }}
QLabel[class="tilevalue"] {{ color: {C['ink']}; font-size: 20px; font-weight: 600; }}
QLabel[class="tileunit"] {{ color: {C['faint']}; font-size: 10px; }}
QToolTip {{ background: {C['raised']}; color: {C['ink']}; border: 1px solid {C['line']}; padding: 6px; font-size: 11px; }}
"""
