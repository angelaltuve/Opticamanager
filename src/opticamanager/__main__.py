import sys
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QFile, QIODevice
from PyQt6.QtWidgets import QApplication

from sqlalchemy import text

from opticamanager.core.logging_config import get_logger, setup_logging
from opticamanager.core.session import UserSession
from opticamanager.db import SessionManager, create_db_and_tables
from opticamanager.resources import breeze_resources  # noqa: F401 (registers Qt resources)
from opticamanager.ui.login_window import LoginWindow
from opticamanager.ui.register_window import RegisterWindow

log = get_logger(__name__)

setup_logging()

STYLES_PATH = Path(__file__).resolve().parent / "resources" / "styles.qss"


def _load_styles(app: QApplication) -> None:
    """Load Breeze theme as base, then apply app-specific overrides."""
    # 1. Load Breeze QSS from Qt resources
    breeze_file = QFile(":/light/stylesheet.qss")
    if breeze_file.open(QIODevice.OpenModeFlag.ReadOnly | QIODevice.OpenModeFlag.Text):
        breeze_qss = str(breeze_file.readAll(), encoding="utf-8")
        breeze_file.close()
    else:
        breeze_qss = ""

    # 2. Load app-specific overrides
    custom_qss = STYLES_PATH.read_text(encoding="utf-8") if STYLES_PATH.exists() else ""

    app.setStyleSheet(breeze_qss + custom_qss)


def _ensure_default_data() -> None:
    """Ensure essential seed data exists (sale statuses, etc.)."""
    with SessionManager() as session:
        statuses = [
            (1, "Completada"),
            (2, "Pendiente"),
            (3, "Cancelada"),
            (4, "Rembolsada"),
        ]
        for sid, name in statuses:
            session.execute(
                text(
                    "INSERT OR IGNORE INTO sale_statuses (id, name, created_at, updated_at) "
                    "VALUES (:id, :name, :now, :now)"
                ),
                {"id": sid, "name": name, "now": datetime.now()},
            )
        session.commit()
        log.info("default_data: ensured %d sale statuses", len(statuses))


def main() -> None:
    app = QApplication(sys.argv)
    _load_styles(app)

    # Create DB and tables if they don't exist
    create_db_and_tables()
    _ensure_default_data()

    # Show RegisterWindow if no admin exists, otherwise LoginWindow
    if UserSession.admin_exists():
        window: LoginWindow | RegisterWindow = LoginWindow()
    else:
        window = RegisterWindow()

    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
