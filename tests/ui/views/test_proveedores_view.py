"""Tests for ProveedoresView, _SupplierDialog and _PagoDeudaDialog.

Coverage target: >=70% of proveedores_view.py
Strategy: mock SessionManager and the dialogs to stay off the real DB.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QMessageBox,
    QPushButton,
)
from pytest_mock import MockerFixture

from opticamanager.ui.views.proveedores_view import (
    ProveedoresView,
    _PagoDeudaDialog,
    _SupplierDialog,
)

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


# ── Helpers ──────────────────────────────────────────────────────────────


def _make_supplier(
    supplier_id: int = 1,
    company_name: str = "Optical Corp",
    contact_name: str | None = "Juan Pérez",
    phone: str | None = "04141234567",
    email: str | None = "info@optical.com",
    address: str | None = "Calle Principal",
    current_debt: Decimal = Decimal("500.00"),
    active: bool = True,
) -> MagicMock:
    s = MagicMock()
    s.id = supplier_id
    s.company_name = company_name
    s.contact_name = contact_name
    s.phone = phone
    s.email = email
    s.address = address
    s.current_debt = current_debt
    s.active = active
    return s


def _fake_session(mocker: MockerFixture, get_side_effect=None):
    """Create a fake session that returns controlled query results."""
    fake = MagicMock()
    manager = mocker.patch("opticamanager.ui.views.proveedores_view.SessionManager")
    manager.return_value.__enter__.return_value = fake
    manager.return_value.__exit__.return_value = False
    if get_side_effect is not None:
        fake.get.side_effect = get_side_effect
    return fake, manager


def _add_supplier_to_view(view: ProveedoresView, supplier=None) -> None:
    """Manually add a supplier row to the view's table."""
    if supplier is None:
        supplier = _make_supplier()
    view._tabla.add_row(
        [
            str(supplier.id),
            supplier.company_name,
            supplier.contact_name or "—",
            supplier.phone or "—",
            supplier.email or "—",
            f"Bs. {supplier.current_debt:,.2f}",
            "Activo" if supplier.active else "Inactivo",
        ]
    )


def _select_first_row(view: ProveedoresView) -> None:
    """Select the first row in the table."""
    view._tabla.view().selectRow(0)


# ── _SupplierDialog Tests ───────────────────────────────────────────────


class TestSupplierDialogCreacion:
    """Tests for _SupplierDialog creation and UI setup."""

    def test_creacion_nuevo_proveedor(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        dlg = _SupplierDialog()
        qtbot.addWidget(dlg)
        assert dlg.windowTitle() == "Nuevo Proveedor"
        assert dlg._company is not None
        assert dlg._phone is not None
        assert dlg._email is not None

    def test_creacion_editar_proveedor(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        supplier = _make_supplier()
        dlg = _SupplierDialog(supplier=supplier)
        qtbot.addWidget(dlg)
        assert dlg.windowTitle() == "Editar Proveedor"
        assert dlg._supplier is supplier


class TestSupplierDialogFillForm:
    """Tests for _SupplierDialog._fill_form."""

    def test_fill_form_completo(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        supplier = _make_supplier()
        dlg = _SupplierDialog(supplier=supplier)
        qtbot.addWidget(dlg)
        assert dlg._company.text() == "Optical Corp"
        assert dlg._contact.text() == "Juan Pérez"
        assert dlg._phone.text() == "04141234567"
        assert dlg._email.text() == "info@optical.com"
        assert dlg._address.text() == "Calle Principal"
        assert "500" in dlg._debt.text()
        assert dlg._active.currentData() is True

    def test_fill_form_campos_vacios(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        supplier = _make_supplier(
            contact_name=None,
            phone=None,
            email=None,
            address=None,
        )
        dlg = _SupplierDialog(supplier=supplier)
        qtbot.addWidget(dlg)
        assert dlg._company.text() == "Optical Corp"
        assert dlg._contact.text() == ""
        assert dlg._phone.text() == ""
        assert dlg._email.text() == ""
        assert dlg._address.text() == ""

    def test_fill_form_proveedor_inactivo(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        supplier = _make_supplier(active=False)
        dlg = _SupplierDialog(supplier=supplier)
        qtbot.addWidget(dlg)
        assert dlg._active.currentData() is False
        assert dlg._active.currentIndex() == 1


class TestSupplierDialogValidacion:
    """Tests for _SupplierDialog._validate_and_accept."""

    def test_empresa_vacia_muestra_warning(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        dlg = _SupplierDialog()
        qtbot.addWidget(dlg)
        warned = []
        mocker.patch.object(
            QMessageBox,
            "warning",
            side_effect=lambda *_a, **_k: warned.append("warn"),
        )
        dlg._company.setText("")
        dlg._phone.setText("04141234567")
        dlg._validate_and_accept()
        assert warned
        assert dlg.result() != QDialog.DialogCode.Accepted

    def test_telefono_vacio_muestra_warning(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        dlg = _SupplierDialog()
        qtbot.addWidget(dlg)
        warned = []
        mocker.patch.object(
            QMessageBox,
            "warning",
            side_effect=lambda *_a, **_k: warned.append("warn"),
        )
        dlg._company.setText("Optical Corp")
        dlg._phone.setText("")
        dlg._validate_and_accept()
        assert warned
        assert dlg.result() != QDialog.DialogCode.Accepted

    def test_validacion_ok_acepta(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        dlg = _SupplierDialog()
        qtbot.addWidget(dlg)
        dlg._company.setText("Optical Corp")
        dlg._phone.setText("04141234567")
        dlg._validate_and_accept()
        assert dlg.result() == QDialog.DialogCode.Accepted


class TestSupplierDialogGetData:
    """Tests for _SupplierDialog.get_data."""

    def test_get_data_completo(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        dlg = _SupplierDialog()
        qtbot.addWidget(dlg)
        dlg._company.setText("Optical Corp")
        dlg._contact.setText("Juan Pérez")
        dlg._phone.setText("04141234567")
        dlg._email.setText("info@optical.com")
        dlg._address.setText("Calle Principal")
        dlg._debt.setText("150.00")
        dlg._active.setCurrentIndex(0)
        data = dlg.get_data()
        assert data["company_name"] == "Optical Corp"
        assert data["contact_name"] == "Juan Pérez"
        assert data["phone"] == "04141234567"
        assert data["email"] == "info@optical.com"
        assert data["address"] == "Calle Principal"
        assert data["current_debt"] == Decimal("150.00")
        assert data["active"] is True

    def test_get_data_campos_opcionales_vacios(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        dlg = _SupplierDialog()
        qtbot.addWidget(dlg)
        dlg._company.setText("Optical Corp")
        dlg._phone.setText("04141234567")
        dlg._contact.setText("")
        dlg._email.setText("")
        dlg._address.setText("")
        data = dlg.get_data()
        assert data["contact_name"] is None
        assert data["email"] is None
        assert data["address"] is None


# ── _PagoDeudaDialog Tests ──────────────────────────────────────────────


class TestPagoDeudaDialogCreacion:
    """Tests for _PagoDeudaDialog creation and UI setup."""

    def test_creacion_basica(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        supplier = _make_supplier(current_debt=Decimal("500.00"))
        dlg = _PagoDeudaDialog(parent=None, supplier=supplier)
        qtbot.addWidget(dlg)
        assert "Pagar deuda" in dlg.windowTitle()
        assert "Optical Corp" in dlg.windowTitle()

    def test_monto_default_igual_deuda(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        supplier = _make_supplier(current_debt=Decimal("500.00"))
        dlg = _PagoDeudaDialog(parent=None, supplier=supplier)
        qtbot.addWidget(dlg)
        assert dlg._monto.text() == "500.00"


class TestPagoDeudaDialogActualizarRestante:
    """Tests for _PagoDeudaDialog._actualizar_restante."""

    def test_restante_se_actualiza(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        supplier = _make_supplier(current_debt=Decimal("500.00"))
        dlg = _PagoDeudaDialog(parent=None, supplier=supplier)
        qtbot.addWidget(dlg)
        dlg._monto.setText("200.00")
        dlg._actualizar_restante()
        assert "300" in dlg._restante.text()

    def test_restante_cero_cuando_pago_total(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        supplier = _make_supplier(current_debt=Decimal("500.00"))
        dlg = _PagoDeudaDialog(parent=None, supplier=supplier)
        qtbot.addWidget(dlg)
        dlg._monto.setText("500.00")
        dlg._actualizar_restante()
        assert "0.00" in dlg._restante.text()

    def test_restante_no_negativo(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        supplier = _make_supplier(current_debt=Decimal("100.00"))
        dlg = _PagoDeudaDialog(parent=None, supplier=supplier)
        qtbot.addWidget(dlg)
        dlg._monto.setText("200.00")
        dlg._actualizar_restante()
        assert "0.00" in dlg._restante.text()

    def test_monto_invalido_restante_mantiene_deuda(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        supplier = _make_supplier(current_debt=Decimal("500.00"))
        dlg = _PagoDeudaDialog(parent=None, supplier=supplier)
        qtbot.addWidget(dlg)
        mocker.patch.object(dlg._monto, "text", return_value="abc")
        dlg._actualizar_restante()
        # Invalid input → ``monto`` = 0 → ``restante`` = 500
        assert "500" in dlg._restante.text()


class TestPagoDeudaDialogValidacion:
    """Tests for _PagoDeudaDialog._validate_and_accept."""

    def test_monto_cero_muestra_warning(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        supplier = _make_supplier(current_debt=Decimal("500.00"))
        dlg = _PagoDeudaDialog(parent=None, supplier=supplier)
        qtbot.addWidget(dlg)
        warned = []
        mocker.patch.object(
            QMessageBox,
            "warning",
            side_effect=lambda *_a, **_k: warned.append("warn"),
        )
        mocker.patch.object(dlg._monto, "text", return_value="0")
        dlg._validate_and_accept()
        assert warned
        assert dlg.result() != QDialog.DialogCode.Accepted

    def test_monto_mayor_que_deuda_muestra_warning(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        supplier = _make_supplier(current_debt=Decimal("100.00"))
        dlg = _PagoDeudaDialog(parent=None, supplier=supplier)
        qtbot.addWidget(dlg)
        warned = []
        mocker.patch.object(
            QMessageBox,
            "warning",
            side_effect=lambda *_a, **_k: warned.append("warn"),
        )
        mocker.patch.object(dlg._monto, "text", return_value="200.00")
        dlg._validate_and_accept()
        assert warned
        assert dlg.result() != QDialog.DialogCode.Accepted

    def test_monto_invalido_muestra_warning(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        supplier = _make_supplier(current_debt=Decimal("500.00"))
        dlg = _PagoDeudaDialog(parent=None, supplier=supplier)
        qtbot.addWidget(dlg)
        warned = []
        mocker.patch.object(
            QMessageBox,
            "warning",
            side_effect=lambda *_a, **_k: warned.append("warn"),
        )
        mocker.patch.object(dlg._monto, "text", return_value="abc")
        dlg._validate_and_accept()
        # Invalid Decimal → monto = 0 → "monto debe ser mayor a cero"
        assert warned
        assert dlg.result() != QDialog.DialogCode.Accepted

    def test_validacion_ok_acepta(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        supplier = _make_supplier(current_debt=Decimal("500.00"))
        dlg = _PagoDeudaDialog(parent=None, supplier=supplier)
        qtbot.addWidget(dlg)
        dlg._monto.setText("300.00")
        dlg._validate_and_accept()
        assert dlg.result() == QDialog.DialogCode.Accepted

    def test_monto_igual_deuda_acepta(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        supplier = _make_supplier(current_debt=Decimal("500.00"))
        dlg = _PagoDeudaDialog(parent=None, supplier=supplier)
        qtbot.addWidget(dlg)
        dlg._monto.setText("500.00")
        dlg._validate_and_accept()
        assert dlg.result() == QDialog.DialogCode.Accepted


class TestPagoDeudaDialogMontoPago:
    """Tests for _PagoDeudaDialog.monto_pago."""

    def test_monto_pago_retorna_valor(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        supplier = _make_supplier(current_debt=Decimal("500.00"))
        dlg = _PagoDeudaDialog(parent=None, supplier=supplier)
        qtbot.addWidget(dlg)
        dlg._monto.setText("250.00")
        assert dlg.monto_pago() == Decimal("250.00")

    def test_monto_pago_vacio_retorna_cero(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        supplier = _make_supplier(current_debt=Decimal("500.00"))
        dlg = _PagoDeudaDialog(parent=None, supplier=supplier)
        qtbot.addWidget(dlg)
        dlg._monto.setText("")
        assert dlg.monto_pago() == Decimal("0")


# ── ProveedoresView Tests ───────────────────────────────────────────────


class TestProveedoresViewCreacion:
    """Smoke tests for ProveedoresView creation."""

    def test_creacion_basica(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        view = ProveedoresView()
        qtbot.addWidget(view)
        assert isinstance(view, ProveedoresView)

    def test_titulo_visible(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        view = ProveedoresView()
        qtbot.addWidget(view)
        from PyQt6.QtWidgets import QLabel

        titles = view.findChildren(QLabel, "title-h2")
        assert len(titles) >= 1
        assert "Proveedores" in titles[0].text()

    def test_botones_toolbar(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        view = ProveedoresView()
        qtbot.addWidget(view)
        buttons = view.findChildren(QPushButton)
        texts = [b.text() for b in buttons]
        assert any("Nuevo Proveedor" in t for t in texts)
        assert any("Editar" in t for t in texts)
        assert any("Eliminar" in t for t in texts)
        assert any("Pagar Deuda" in t for t in texts)


class TestProveedoresViewLoadData:
    """Tests for _load_data."""

    def test_load_data_vacio(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        view = ProveedoresView()
        qtbot.addWidget(view)
        assert view._tabla.row_count() == 0

    def test_load_data_con_proveedores(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        fake, _ = _fake_session(mocker)
        s1 = _make_supplier(1, "Optical Corp")
        s2 = _make_supplier(2, "Lens World")
        fake.exec.return_value.all.return_value = [s1, s2]
        view = ProveedoresView()
        qtbot.addWidget(view)
        assert view._tabla.row_count() == 2

    def test_load_data_proveedor_sin_contacto(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        fake, _ = _fake_session(mocker)
        s = _make_supplier(contact_name=None, phone=None, email=None)
        fake.exec.return_value.all.return_value = [s]
        view = ProveedoresView()
        qtbot.addWidget(view)
        assert view._tabla.row_count() == 1

    def test_load_data_proveedor_inactivo(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        fake, _ = _fake_session(mocker)
        s = _make_supplier(active=False)
        fake.exec.return_value.all.return_value = [s]
        view = ProveedoresView()
        qtbot.addWidget(view)
        assert view._tabla.row_count() == 1


class TestProveedoresViewNuevoProveedor:
    """Tests for _nuevo_proveedor flow."""

    def test_dialogo_cancelado_no_crea(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        view = ProveedoresView()
        qtbot.addWidget(view)
        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = QDialog.DialogCode.Rejected
        mocker.patch(
            "opticamanager.ui.views.proveedores_view._SupplierDialog",
            return_value=mock_dlg,
        )
        view._nuevo_proveedor()
        fake.add.assert_not_called()

    def test_dialogo_aceptado_crea_proveedor(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        view = ProveedoresView()
        qtbot.addWidget(view)
        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = QDialog.DialogCode.Accepted
        mock_dlg.get_data.return_value = {
            "company_name": "Nuevo Proveedor",
            "contact_name": "Ana",
            "phone": "04141234567",
            "email": "ana@test.com",
            "address": "Calle 1",
            "current_debt": Decimal("0"),
            "active": True,
        }
        mocker.patch(
            "opticamanager.ui.views.proveedores_view._SupplierDialog",
            return_value=mock_dlg,
        )
        view._nuevo_proveedor()
        fake.add.assert_called_once()
        fake.commit.assert_called()

    def test_error_al_crear_muestra_error(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        fake.add.side_effect = Exception("DB error")
        view = ProveedoresView()
        qtbot.addWidget(view)
        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = QDialog.DialogCode.Accepted
        mock_dlg.get_data.return_value = {
            "company_name": "Nuevo",
            "contact_name": None,
            "phone": "04141234567",
            "email": None,
            "address": None,
            "current_debt": Decimal("0"),
            "active": True,
        }
        mocker.patch(
            "opticamanager.ui.views.proveedores_view._SupplierDialog",
            return_value=mock_dlg,
        )
        mock_error = mocker.patch(
            "opticamanager.ui.views.proveedores_view.dialogo_error",
        )
        view._nuevo_proveedor()
        mock_error.assert_called_once()


class TestProveedoresViewEditarProveedor:
    """Tests for _editar_proveedor flow."""

    def test_sin_seleccion_no_hace_nada(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        view = ProveedoresView()
        qtbot.addWidget(view)
        msgs = []
        mocker.patch.object(
            QMessageBox,
            "information",
            side_effect=lambda *_a, **_k: msgs.append("info"),
        )
        view._editar_proveedor()
        assert msgs

    def test_proveedor_no_encontrado(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        view = ProveedoresView()
        qtbot.addWidget(view)
        _add_supplier_to_view(view)
        _select_first_row(view)
        fake.get.return_value = None
        view._editar_proveedor()
        # Should return without crash

    def test_dialogo_cancelado_no_edita(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        view = ProveedoresView()
        qtbot.addWidget(view)
        _add_supplier_to_view(view)
        _select_first_row(view)
        supplier = _make_supplier()
        fake.get.return_value = supplier
        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = QDialog.DialogCode.Rejected
        mocker.patch(
            "opticamanager.ui.views.proveedores_view._SupplierDialog",
            return_value=mock_dlg,
        )
        view._editar_proveedor()
        fake.add.assert_not_called()

    def test_dialogo_aceptado_edita_proveedor(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        view = ProveedoresView()
        qtbot.addWidget(view)
        _add_supplier_to_view(view)
        _select_first_row(view)
        supplier = _make_supplier()
        fake.get.return_value = supplier
        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = QDialog.DialogCode.Accepted
        mock_dlg.get_data.return_value = {
            "company_name": "Editado Corp",
            "contact_name": "Ana",
            "phone": "04141234567",
            "email": "editado@test.com",
            "address": "Nueva Dirección",
            "current_debt": Decimal("100.00"),
            "active": True,
        }
        mocker.patch(
            "opticamanager.ui.views.proveedores_view._SupplierDialog",
            return_value=mock_dlg,
        )
        view._editar_proveedor()
        fake.add.assert_called()
        fake.commit.assert_called()


class TestProveedoresViewEliminarProveedor:
    """Tests for _eliminar_proveedor flow."""

    def test_sin_seleccion_no_hace_nada(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        view = ProveedoresView()
        qtbot.addWidget(view)
        msgs = []
        mocker.patch.object(
            QMessageBox,
            "information",
            side_effect=lambda *_a, **_k: msgs.append("info"),
        )
        view._eliminar_proveedor()
        assert msgs

    def test_cancelar_eliminacion(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        view = ProveedoresView()
        qtbot.addWidget(view)
        _add_supplier_to_view(view)
        _select_first_row(view)
        mocker.patch(
            "opticamanager.ui.views.proveedores_view.dialogo_confirmacion",
            return_value=False,
        )
        view._eliminar_proveedor()
        fake.delete.assert_not_called()

    def test_confirmar_eliminacion_exitosa(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        view = ProveedoresView()
        qtbot.addWidget(view)
        _add_supplier_to_view(view)
        _select_first_row(view)
        mocker.patch(
            "opticamanager.ui.views.proveedores_view.dialogo_confirmacion",
            return_value=True,
        )
        supplier = _make_supplier()
        fake.get.return_value = supplier
        view._eliminar_proveedor()
        fake.delete.assert_called_once_with(supplier)
        fake.commit.assert_called()

    def test_proveedor_no_encontrado_no_crash(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        view = ProveedoresView()
        qtbot.addWidget(view)
        _add_supplier_to_view(view)
        _select_first_row(view)
        mocker.patch(
            "opticamanager.ui.views.proveedores_view.dialogo_confirmacion",
            return_value=True,
        )
        fake.get.return_value = None
        view._eliminar_proveedor()
        # Should not crash

    def test_error_al_eliminar_muestra_error(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        view = ProveedoresView()
        qtbot.addWidget(view)
        _add_supplier_to_view(view)
        _select_first_row(view)
        mocker.patch(
            "opticamanager.ui.views.proveedores_view.dialogo_confirmacion",
            return_value=True,
        )
        supplier = _make_supplier()
        fake.get.return_value = supplier
        fake.delete.side_effect = Exception("FK constraint")
        mock_error = mocker.patch(
            "opticamanager.ui.views.proveedores_view.dialogo_error",
        )
        view._eliminar_proveedor()
        mock_error.assert_called_once()


class TestProveedoresViewPagarDeuda:
    """Tests for _pagar_deuda flow."""

    def test_sin_seleccion_no_hace_nada(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        view = ProveedoresView()
        qtbot.addWidget(view)
        msgs = []
        mocker.patch.object(
            QMessageBox,
            "information",
            side_effect=lambda *_a, **_k: msgs.append("info"),
        )
        view._pagar_deuda()
        assert msgs

    def test_proveedor_no_encontrado(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        view = ProveedoresView()
        qtbot.addWidget(view)
        _add_supplier_to_view(view)
        _select_first_row(view)
        fake.get.return_value = None
        view._pagar_deuda()
        # Should return without crash

    def test_proveedor_sin_deuda_muestra_info(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        view = ProveedoresView()
        qtbot.addWidget(view)
        _add_supplier_to_view(view)
        _select_first_row(view)
        supplier = _make_supplier(current_debt=Decimal("0"))
        fake.get.return_value = supplier
        msgs = []
        mocker.patch.object(
            QMessageBox,
            "information",
            side_effect=lambda *_a, **_k: msgs.append("info"),
        )
        view._pagar_deuda()
        assert msgs

    def test_dialogo_cancelado_no_paga(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        view = ProveedoresView()
        qtbot.addWidget(view)
        _add_supplier_to_view(view)
        _select_first_row(view)
        supplier = _make_supplier(current_debt=Decimal("500.00"))
        fake.get.return_value = supplier
        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = QDialog.DialogCode.Rejected
        mocker.patch(
            "opticamanager.ui.views.proveedores_view._PagoDeudaDialog",
            return_value=mock_dlg,
        )
        view._pagar_deuda()
        fake.commit.assert_not_called()

    def test_pago_exitoso(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        view = ProveedoresView()
        qtbot.addWidget(view)
        _add_supplier_to_view(view)
        _select_first_row(view)
        supplier = _make_supplier(current_debt=Decimal("500.00"))
        fake.get.return_value = supplier
        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = QDialog.DialogCode.Accepted
        mock_dlg.monto_pago.return_value = Decimal("200.00")
        mocker.patch(
            "opticamanager.ui.views.proveedores_view._PagoDeudaDialog",
            return_value=mock_dlg,
        )
        msgs = []
        mocker.patch.object(
            QMessageBox,
            "information",
            side_effect=lambda *_a, **_k: msgs.append("info"),
        )
        view._pagar_deuda()
        assert supplier.current_debt == Decimal("300.00")
        fake.add.assert_called()
        fake.commit.assert_called()
        assert msgs

    def test_pago_total_deuda_cero(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        view = ProveedoresView()
        qtbot.addWidget(view)
        _add_supplier_to_view(view)
        _select_first_row(view)
        supplier = _make_supplier(current_debt=Decimal("100.00"))
        fake.get.return_value = supplier
        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = QDialog.DialogCode.Accepted
        mock_dlg.monto_pago.return_value = Decimal("100.00")
        mocker.patch(
            "opticamanager.ui.views.proveedores_view._PagoDeudaDialog",
            return_value=mock_dlg,
        )
        msgs = []
        mocker.patch.object(
            QMessageBox,
            "information",
            side_effect=lambda *_a, **_k: msgs.append("info"),
        )
        view._pagar_deuda()
        assert supplier.current_debt == Decimal("0.00")
        fake.commit.assert_called()


class TestProveedoresViewSelectedRow:
    """Tests for _selected_row and _selected_supplier_id."""

    def test_selected_row_sin_seleccion(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        view = ProveedoresView()
        qtbot.addWidget(view)
        msgs = []
        mocker.patch.object(
            QMessageBox,
            "information",
            side_effect=lambda *_a, **_k: msgs.append("info"),
        )
        result = view._selected_row()
        assert result is None
        assert msgs

    def test_selected_row_con_seleccion(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        view = ProveedoresView()
        qtbot.addWidget(view)
        _add_supplier_to_view(view)
        _select_first_row(view)
        result = view._selected_row()
        assert result == 0

    def test_selected_supplier_id_sin_seleccion(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        view = ProveedoresView()
        qtbot.addWidget(view)
        msgs = []
        mocker.patch.object(
            QMessageBox,
            "information",
            side_effect=lambda *_a, **_k: msgs.append("info"),
        )
        result = view._selected_supplier_id()
        assert result is None

    def test_selected_supplier_id_con_seleccion(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        view = ProveedoresView()
        qtbot.addWidget(view)
        _add_supplier_to_view(view, _make_supplier(supplier_id=42))
        _select_first_row(view)
        result = view._selected_supplier_id()
        assert result == 42


class TestProveedoresViewStaticHelpers:
    """Tests for static helper methods."""

    def test_get_selected_id(self) -> None:
        model = MagicMock()
        item = MagicMock()
        item.text.return_value = "42"
        model.item.return_value = item
        assert ProveedoresView._get_selected_id(model, 0) == 42

    def test_get_selected_id_item_none(self) -> None:
        model = MagicMock()
        model.item.return_value = None
        assert ProveedoresView._get_selected_id(model, 0) == 0

    def test_get_selected_name(self) -> None:
        model = MagicMock()
        item = MagicMock()
        item.text.return_value = "Optical Corp"
        model.item.return_value = item
        assert ProveedoresView._get_selected_name(model, 0) == "Optical Corp"

    def test_get_selected_name_item_none(self) -> None:
        model = MagicMock()
        model.item.return_value = None
        assert ProveedoresView._get_selected_name(model, 0) == ""


class TestProveedoresViewBotonesConexion:
    """Tests that toolbar buttons are wired to the correct slots.

    Patch at CLASS level BEFORE instantiation so signal-slot picks up the mock.
    """

    def test_boton_editar_conecta(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        mock_editar = mocker.patch.object(ProveedoresView, "_editar_proveedor")
        view = ProveedoresView()
        qtbot.addWidget(view)
        mock_editar.reset_mock()
        qtbot.mouseClick(view._btn_editar, Qt.MouseButton.LeftButton)
        mock_editar.assert_called_once()

    def test_boton_eliminar_conecta(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        mock_eliminar = mocker.patch.object(ProveedoresView, "_eliminar_proveedor")
        view = ProveedoresView()
        qtbot.addWidget(view)
        mock_eliminar.reset_mock()
        qtbot.mouseClick(view._btn_eliminar, Qt.MouseButton.LeftButton)
        mock_eliminar.assert_called_once()

    def test_boton_nuevo_existe(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        view = ProveedoresView()
        qtbot.addWidget(view)
        for btn in view.findChildren(QPushButton):
            if "Nuevo Proveedor" in btn.text():
                assert btn is not None
                return
        raise AssertionError("Botón 'Nuevo Proveedor' no encontrado")

    def test_boton_pagar_deuda_existe(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        view = ProveedoresView()
        qtbot.addWidget(view)
        for btn in view.findChildren(QPushButton):
            if "Pagar Deuda" in btn.text():
                assert btn is not None
                return
        raise AssertionError("Botón 'Pagar Deuda' no encontrado")
