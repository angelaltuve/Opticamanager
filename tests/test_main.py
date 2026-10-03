"""Tests for the CLI entrypoint (__main__.py) with heavy modules mocked."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from pytest_mock import MockerFixture
from sqlmodel import select

from opticamanager import __main__ as main_module
from opticamanager.db import SessionManager
from opticamanager.models.sale_status import SaleStatus


class TestLoadStyles:
    def test_estilos_breeze_y_custom_aplicados(
        self, qapp, mocker: MockerFixture, tmp_path: Path
    ) -> None:
        """Breeze readable via Qt resources + custom QSS from disk."""
        style_file = tmp_path / "styles.qss"
        style_file.write_text("QPushButton { color: red; }", encoding="utf-8")
        mocker.patch.object(main_module, "STYLES_PATH", style_file)
        mocker.patch.object(
            main_module.QFile,
            "open",
            return_value=True,
        )
        mocker.patch.object(
            main_module.QFile,
            "readAll",
            return_value=b"breeze-qss-body",
        )

        app = MagicMock()
        main_module._load_styles(app)

        app.setStyleSheet.assert_called_once_with(
            "breeze-qss-body" + "QPushButton { color: red; }"
        )

    def test_estilos_solo_custom_si_breeze_no_abre(
        self, qapp, mocker: MockerFixture, tmp_path: Path
    ) -> None:
        """Breeze unavailable -> only custom QSS is applied."""
        style_file = tmp_path / "styles.qss"
        style_file.write_text("body{}", encoding="utf-8")
        mocker.patch.object(main_module, "STYLES_PATH", style_file)
        mocker.patch.object(main_module.QFile, "open", return_value=False)

        app = MagicMock()
        main_module._load_styles(app)

        app.setStyleSheet.assert_called_once_with("body{}")

    def test_estilos_vacios_si_no_hay_qss(self, qapp, mocker: MockerFixture) -> None:
        """Neither styles source available -> empty stylesheet."""
        mocker.patch.object(
            main_module,
            "STYLES_PATH",
            Path("/no/existe/styles.qss"),
        )
        mocker.patch.object(main_module.QFile, "open", return_value=False)

        app = MagicMock()
        main_module._load_styles(app)

        app.setStyleSheet.assert_called_once_with("")


class TestEnsureDefaultData:
    def test_crea_los_cuatro_estados_de_venta(self) -> None:
        main_module._ensure_default_data()

        with SessionManager() as session:
            statuses = session.exec(select(SaleStatus)).all()
            by_id = {s.id: s.name for s in statuses}

        assert by_id == {
            1: "Completada",
            2: "Pendiente",
            3: "Cancelada",
            4: "Rembolsada",
        }

    def test_es_idempotente(self) -> None:
        main_module._ensure_default_data()
        main_module._ensure_default_data()

        with SessionManager() as session:
            count = len(session.exec(select(SaleStatus)).all())

        assert count == 4


class TestMain:
    def _patch_main_world(
        self, mocker: MockerFixture, admin_exists: bool = True
    ) -> SimpleNamespace:
        """Replace everything main() touches except the branch logic."""
        fake_app = MagicMock()
        fake_app.exec.return_value = 0
        fake_qapp = mocker.patch("opticamanager.__main__.QApplication")
        fake_qapp.return_value = fake_app
        mocker.patch("opticamanager.__main__._load_styles")
        mocker.patch("opticamanager.__main__.create_db_and_tables")
        mocker.patch("opticamanager.__main__._ensure_default_data")
        fake_exit = mocker.patch("opticamanager.__main__.sys.exit")
        fake_login = mocker.patch("opticamanager.__main__.LoginWindow")
        fake_register = mocker.patch("opticamanager.__main__.RegisterWindow")
        mocker.patch.object(
            main_module.UserSession, "admin_exists", return_value=admin_exists
        )

        return SimpleNamespace(
            app=fake_app,
            exit=fake_exit,
            login=fake_login,
            register=fake_register,
        )

    def test_main_muestra_login_cuando_existe_admin(
        self, mocker: MockerFixture
    ) -> None:
        world = self._patch_main_world(mocker, admin_exists=True)

        main_module.main()

        world.login.assert_called_once()
        world.register.assert_not_called()
        world.login.return_value.show.assert_called_once()
        world.exit.assert_called_once_with(world.app.exec())

    def test_main_muestra_registro_cuando_no_hay_admin(
        self, mocker: MockerFixture
    ) -> None:
        world = self._patch_main_world(mocker, admin_exists=False)

        main_module.main()

        world.register.assert_called_once()
        world.login.assert_not_called()
        world.register.return_value.show.assert_called_once()
        world.exit.assert_called_once_with(world.app.exec())
