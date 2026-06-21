"""WhoLikedIt? – application entry point."""
from __future__ import annotations
import sys
import os
import logging

# Ensure the project root is in sys.path when run as a script or EXE
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Must be before QApplication — allows WebEngine to autoplay without user gesture
if "--autoplay-policy" not in " ".join(sys.argv):
    sys.argv += ["--autoplay-policy=no-user-gesture-required"]

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

    # Configure WebEngine profile before any view is created
    try:
        from PyQt6.QtWebEngineCore import QWebEngineProfile
        profile = QWebEngineProfile.defaultProfile()
        # Mobile Chrome UA → TikTok renders its vertical mobile layout (fits 360 px)
        profile.setHttpUserAgent(
            "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36"
        )
        # Persist cookies so TikTok session survives between rounds
        profile.setPersistentStoragePath(str(DATA_DIR / "webengine"))
        profile.setCachePath(str(DATA_DIR / "webengine_cache"))
        profile.setPersistentCookiesPolicy(
            QWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies
        )
    except Exception:
        pass

    # Initialize database
    db = DatabaseManager()
    db.initialize()

    window = MainWindow(db)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
