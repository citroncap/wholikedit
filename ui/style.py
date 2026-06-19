"""Global dark theme stylesheet."""

GLOBAL_STYLE = """
* { font-family: "Segoe UI", Arial, sans-serif; color: #FFFFFF; }

QMainWindow, QDialog { background-color: #0a0a0a; }
QWidget { background-color: transparent; }
QLabel  { background-color: transparent; }

/* ── Scrollbars ──────────────────────────────── */
QScrollBar:vertical { background:#161616; width:6px; border-radius:3px; }
QScrollBar::handle:vertical { background:#3a3a3a; border-radius:3px; min-height:24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
QScrollBar:horizontal { height:0; }

/* ── QPushButton ─────────────────────────────── */
QPushButton {
    background-color:#1e1e1e; border:1px solid #333;
    border-radius:8px; padding:10px 22px;
    font-size:14px; font-weight:600;
}
QPushButton:hover  { background-color:#2a2a2a; border-color:#FE2C55; }
QPushButton:pressed { background-color:#161616; }
QPushButton:disabled { color:#444; border-color:#222; }

/* Primary */
QPushButton[primary="true"] {
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #FE2C55,stop:1 #FF006E);
    border:none; color:#fff;
}
QPushButton[primary="true"]:hover {
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #FF4470,stop:1 #FF2888);
}
QPushButton[primary="true"]:pressed {
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #CC2244,stop:1 #CC0055);
}

/* Secondary (outline) */
QPushButton[secondary="true"] {
    background:transparent; border:2px solid #25F4EE; color:#25F4EE;
}
QPushButton[secondary="true"]:hover { background:rgba(37,244,238,0.08); }

/* Danger */
QPushButton[danger="true"] {
    background:transparent; border:1px solid #E74C3C; color:#E74C3C;
}
QPushButton[danger="true"]:hover { background:rgba(231,76,60,0.12); }

/* ── QLineEdit ───────────────────────────────── */
QLineEdit {
    background:#1e1e1e; border:1px solid #333; border-radius:8px;
    padding:10px 14px; font-size:14px; color:#FFFFFF;
    selection-background-color:#FE2C55;
}
QLineEdit:focus { border-color:#FE2C55; }

/* ── QSpinBox ────────────────────────────────── */
QSpinBox {
    background:#1e1e1e; border:1px solid #333; border-radius:8px;
    padding:8px 12px; font-size:14px;
}
QSpinBox:focus { border-color:#FE2C55; }
QSpinBox::up-button, QSpinBox::down-button { background:#333; border:none; width:22px; }
QSpinBox::up-button:hover, QSpinBox::down-button:hover { background:#FE2C55; }

/* ── QProgressBar ────────────────────────────── */
QProgressBar {
    background:#1e1e1e; border:none; border-radius:4px;
    height:8px; text-align:center;
}
QProgressBar::chunk {
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #FE2C55,stop:1 #25F4EE);
    border-radius:4px;
}

/* ── QFrame separators ───────────────────────── */
QFrame[frameShape="4"], QFrame[frameShape="5"] { color:#2a2a2a; }

/* ── QCheckBox ───────────────────────────────── */
QCheckBox { spacing:8px; font-size:14px; }
QCheckBox::indicator {
    width:18px; height:18px; border:2px solid #333;
    border-radius:4px; background:#1e1e1e;
}
QCheckBox::indicator:checked { background:#FE2C55; border-color:#FE2C55; }

/* ── QScrollArea ─────────────────────────────── */
QScrollArea { border:none; background:transparent; }
"""
