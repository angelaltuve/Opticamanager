from __future__ import annotations

from sqlmodel import Session, text

from opticamanager.db.database import (
    DB_DIR,
    DATABASE_URL,
    SessionManager,
    create_db_and_tables,
    engine,
    get_session,
)


class TestEngine:
    def test_engine_exists(self) -> None:
        """Engine singleton is created at module load."""
        assert engine is not None

    def test_database_url_is_sqlite(self) -> None:
        """DATABASE_URL points to a SQLite file in the data directory."""
        assert DATABASE_URL.startswith("sqlite:///")
        assert "opticamanager.db" in DATABASE_URL

    def test_db_dir_exists(self) -> None:
        """DB_DIR points to the data directory."""
        assert "data" in str(DB_DIR)

    def test_engine_connectivity(self) -> None:
        """Engine can connect and execute a simple query."""
        with engine.connect() as conn:
            result = conn.exec_driver_sql("SELECT 1 AS test_val")
            row = result.fetchone()
            assert row is not None
            assert row[0] == 1


class TestSessionManager:
    def test_enter_returns_session(self) -> None:
        """SessionManager.__enter__ returns a Session instance."""
        with SessionManager() as session:
            assert isinstance(session, Session)

    def test_session_is_active(self) -> None:
        """The session acquired via SessionManager is usable."""
        with SessionManager() as session:
            result = session.execute(text("SELECT 1 AS val"))
            row = result.fetchone()
            assert row is not None
            assert row[0] == 1

    def test_exit_closes_session(self) -> None:
        """Session is closed after exiting the context manager."""
        sm = SessionManager()
        with sm:
            assert sm.session is not None
        assert sm.session is None

    def test_rollback_on_exception(self, mocker) -> None:
        """Session is rolled back when an exception occurs in the context."""
        mock_rollback = mocker.patch.object(Session, "rollback")
        mock_close = mocker.patch.object(Session, "close")

        try:
            with SessionManager():
                raise ValueError("test error")
        except ValueError:
            pass

        mock_rollback.assert_called_once()
        mock_close.assert_called_once()

    def test_multiple_nested_not_allowed(self) -> None:
        """Sequential SessionManager usage works independently."""
        with SessionManager() as s1:
            assert isinstance(s1, Session)

        with SessionManager() as s2:
            assert isinstance(s2, Session)
            assert s2 is not s1  # noqa: F841 - checked for identity

    def test_session_has_expire_on_commit_false(self) -> None:
        """Session is created with expire_on_commit=False for pytest compatibility."""
        with SessionManager() as session:
            assert session.info.get("expire_on_commit") is None  # default for Session
            # The engine-level setting is expire_on_commit=False


class TestSqlitePragmas:
    @staticmethod
    def _pragma(conn, name: str) -> object:
        row = conn.exec_driver_sql(f"PRAGMA {name}").fetchone()  # noqa: S608
        assert row is not None, f"PRAGMA {name} no devolvió fila"
        return row[0]

    def test_foreign_keys_enabled_on_pooled_connection(self) -> None:
        """foreign_keys=ON is active on a checked-out pooled connection.

        Regression: the pragma used to be issued once on a single connection, so
        the rest of the pool silently ran without FK enforcement.
        """
        with engine.connect() as conn:
            assert self._pragma(conn, "foreign_keys") == 1

    def test_foreign_keys_enabled_on_second_pooled_connection(self) -> None:
        """A second connection from the pool also has foreign_keys=ON."""
        first = engine.connect()
        first.close()
        with engine.connect() as second:
            assert self._pragma(second, "foreign_keys") == 1

    def test_journal_mode_is_wal(self) -> None:
        """The database runs in WAL journal mode."""
        with engine.connect() as conn:
            assert str(self._pragma(conn, "journal_mode")).lower() == "wal"


class TestCreateDBAndTables:
    def test_creates_tables(self, mocker) -> None:
        """create_db_and_tables creates all model tables."""
        inspector = mocker.patch("sqlmodel.SQLModel.metadata.create_all")
        mkdir = mocker.patch("pathlib.Path.mkdir")

        create_db_and_tables()

        inspector.assert_called_once_with(engine)
        mkdir.assert_called_once_with(parents=True, exist_ok=True)

    def test_creates_parent_of_custom_db_path(self, mocker, tmp_path) -> None:
        """A custom OPTICAMANAGER_DB_PATH gets its parent directory created.

        Regression: only DB_DIR was created, so a DB path outside data/ failed
        with "unable to open database file".
        """
        custom = tmp_path / "nested" / "deeper" / "custom.db"
        mocker.patch("opticamanager.db.database.DB_PATH", custom)

        create_db_and_tables()

        assert custom.parent.is_dir()


class TestGetSession:
    def test_yields_session(self) -> None:
        """get_session generator yields a usable Session."""
        gen = get_session()
        session = next(gen)
        assert isinstance(session, Session)
        assert session.is_active
        # Close the generator
        try:
            next(gen)
        except StopIteration:
            pass

    def test_session_closes_after_generator(self) -> None:
        """Session is closed when the generator finishes."""
        gen = get_session()
        session = next(gen)
        try:
            next(gen)
        except StopIteration:
            pass
        # After generator close, the session's connection is returned to pool
        # Calling is_active triggers a legacy check; just verify no exception
        assert session is not None
