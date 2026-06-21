"""WhoLikedIt? – application entry point."""
from __future__ import annotations
import sys
import os
import logging

# Ensure the project root is in sys.path when run as a script or EXE
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QT_VERSION_STR, PYQT_VERSION_STR
from PyQt6.QtGui import QFont

from database.db_manager import DatabaseManager
from ui.main_window import MainWindow
from utils.config import APP_NAME, APP_VERSION, DATA_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(DATA_DIR / "app.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)


def main() -> None:
    log.info(
        "Starting %s v%s  (Qt %s / PyQt %s)",
        APP_NAME, APP_VERSION, QT_VERSION_STR, PYQT_VERSION_STR,
    )

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName(APP_NAME)

    # Smooth high-DPI rendering
    app.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    # Default font
    font = QFont("Segoe UI", 10)
    app.setFont(font)

    # Initialize database
    db = DatabaseManager()
    db.initialize()

    window = MainWindow(db)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
