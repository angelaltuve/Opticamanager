import os
import sqlite3
import sys
from collections.abc import Generator
from pathlib import Path
from types import TracebackType

from sqlalchemy import event
from sqlmodel import SQLModel, Session, create_engine

from opticamanager.models import *  # noqa: F401, F403

if getattr(sys, "frozen", False):
    # PyInstaller bundle: DB lives next to the executable
    DB_DIR = Path(sys.executable).parent / "data"
else:
    # Dev mode: relative to source tree
    DB_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data"
DB_PATH = (
    Path(os.environ["OPTICAMANAGER_DB_PATH"])
    if os.environ.get("OPTICAMANAGER_DB_PATH")
    else DB_DIR / "opticamanager.db"
)
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_connection: sqlite3.Connection, _record: object) -> None:
    """Apply the SQLite pragmas to every connection in the pool.

    SQLite pragmas are per connection: issuing them once on a single connection
    leaves the rest of the pool without ``foreign_keys=ON``, and therefore without
    referential integrity checking.
    """
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
    finally:
        cursor.close()


def create_db_and_tables() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    SQLModel.metadata.create_all(engine)


class SessionManager:
    def __init__(self) -> None:
        self.session: Session | None = None

    def __enter__(self) -> Session:
        self.session = Session(engine, expire_on_commit=False)
        return self.session

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        _exc_val: BaseException | None,
        _exc_tb: TracebackType | None,
    ) -> None:
        if self.session is None:
            return
        if exc_type is not None:
            self.session.rollback()
        self.session.close()
        self.session = None


def get_session() -> Generator[Session, None, None]:
    """FastAPI-style dependency: yields a session and always closes it.

    Kept consistent with :class:`SessionManager` (``expire_on_commit=False``)
    so callers do not lose attribute access after an explicit commit.
    Commits remain the caller's responsibility.
    """
    with Session(engine, expire_on_commit=False) as session:
        yield session
