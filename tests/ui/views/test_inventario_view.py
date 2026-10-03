"""Tests for InventarioView, _ProductoDialog and _MovimientosDialog.

Coverage target: >=70% of inventario_view.py
Strategy: mock SessionManager and the dialogs to stay off the real DB.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QMessageBox,
    QPushButton,
)
from pytest_mock import MockerFixture

from opticamanager.ui.views.inventario_view import (
    InventarioView,
    _MovimientosDialog,
    _ProductoDialog,
    _copiar_imagen,
)

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


# ── Helpers ──────────────────────────────────────────────────────────────


def _make_product(
    product_id: int = 1,
    name: str = "Lente Bifocal",
    barcode: str | None = "1234567890123",
    category_id: int | None = 1,
    cost_price_usd: Decimal = Decimal("10.00"),
    sale_price_usd: Decimal = Decimal("25.00"),
    stock_quantity: int = 50,
    min_stock: int = 5,
    active: bool = True,
    description: str | None = "Lente de prueba",
    image_path: str | None = None,
) -> MagicMock:
    p = MagicMock()
    p.id = product_id
    p.name = name
    p.barcode = barcode
    p.category_id = category_id
    p.cost_price_usd = cost_price_usd
    p.sale_price_usd = sale_price_usd
    p.stock_quantity = stock_quantity
    p.min_stock = min_stock
    p.active = active
    p.description = description
    p.image_path = image_path
    return p


def _make_category(cat_id: int = 1, name: str = "Lentes") -> MagicMock:
    c = MagicMock()
    c.id = cat_id
    c.name = name
    return c


def _make_inventory_log(
    log_id: int = 1,
    product_id: int = 1,
    quantity: int = 10,
    unit_cost: Decimal | None = Decimal("10.00"),
    reason: str = "Compra",
    user_id: int = 1,
) -> MagicMock:
    log = MagicMock()
    log.id = log_id
    log.product_id = product_id
    log.quantity = quantity
    log.unit_cost = unit_cost
    log.reason = reason
    log.user_id = user_id
    log.created_at = datetime(2026, 9, 20, 10, 30)
    return log


def _make_user(user_id: int = 1, name: str = "Admin") -> MagicMock:
    u = MagicMock()
    u.id = user_id
    u.name = name
    return u


def _fake_session(mocker: MockerFixture, get_side_effect=None):
    """Create a fake session that returns controlled query results."""
    fake = MagicMock()
    manager = mocker.patch("opticamanager.ui.views.inventario_view.SessionManager")
    manager.return_value.__enter__.return_value = fake
    manager.return_value.__exit__.return_value = False
    if get_side_effect is not None:
        fake.get.side_effect = get_side_effect
    return fake, manager


def _add_row_to_view(view: InventarioView, product=None) -> None:
    """Manually add a product row to the view's table for selection testing."""
    if product is None:
        product = _make_product()
    view._tabla.add_row(
        [
            str(product.id),
            product.barcode or "",
            product.name,
            "Lentes",
            f"$ {product.sale_price_usd:,.2f}",
            str(product.stock_quantity),
            str(product.min_stock),
            "Activo" if product.active else "Inactivo",
        ]
    )


def _select_first_row(view: InventarioView) -> None:
    """Select the first row in the table."""
    view._tabla.view().selectRow(0)


def _suppress_message_boxes(mocker: MockerFixture) -> list:
    """Suppress QMessageBox.warning and QMessageBox.information calls."""
    warned = []
    mocker.patch.object(
        QMessageBox, "warning", side_effect=lambda *_a, **_k: warned.append("warn")
    )
    mocker.patch.object(
        QMessageBox,
        "information",
        side_effect=lambda *_a, **_k: warned.append("info"),
    )
    return warned


# ── _copiar_imagen Tests ────────────────────────────────────────────────


class TestCopiarImagen:
    """Tests for the _copiar_imagen helper function."""

    def test_copia_imagen_y_retorna_ruta_relativa(
        self, mocker: MockerFixture, tmp_path
    ) -> None:
        from opticamanager.ui.views import inventario_view

        mocker.patch.object(inventario_view, "IMAGES_DIR", tmp_path)
        mock_copy = mocker.patch("opticamanager.ui.views.inventario_view.copy2")
        origen = str(tmp_path / "foto.jpg")
        result = _copiar_imagen(origen)
        mock_copy.assert_called_once()
        assert isinstance(result, str)

    def test_crea_directorio_si_no_existe(
        self, mocker: MockerFixture, tmp_path
    ) -> None:
        from opticamanager.ui.views import inventario_view

        new_dir = tmp_path / "new_images"
        mocker.patch.object(inventario_view, "IMAGES_DIR", new_dir)
        mocker.patch("opticamanager.ui.views.inventario_view.copy2")
        _copiar_imagen(str(tmp_path / "foto.jpg"))
        assert new_dir.exists()

    def test_usa_extension_por_defecto_cuando_no_tiene(
        self, mocker: MockerFixture, tmp_path
    ) -> None:
        from opticamanager.ui.views import inventario_view

        mocker.patch.object(inventario_view, "IMAGES_DIR", tmp_path)
        mocker.patch("opticamanager.ui.views.inventario_view.copy2")
        result = _copiar_imagen(str(tmp_path / "foto"))
        assert result.endswith(".jpg") or result.endswith(".png")


# ── _ProductoDialog Tests ───────────────────────────────────────────────


class TestProductoDialogCreacion:
    """Tests for _ProductoDialog creation and UI setup."""

    def test_creacion_nuevo_producto(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        dlg = _ProductoDialog()
        qtbot.addWidget(dlg)
        assert dlg.windowTitle() == "Nuevo Producto"
        assert dlg._nombre is not None
        assert dlg._cost_price is not None
        assert dlg._sale_price is not None

    def test_creacion_editar_producto(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        product = _make_product()
        dlg = _ProductoDialog(producto=product)
        qtbot.addWidget(dlg)
        assert dlg.windowTitle() == "Editar Producto"
        assert dlg._producto is product

    def test_load_categories_pobla_combo(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        fake, _ = _fake_session(mocker)
        cat1 = _make_category(1, "Lentes")
        cat2 = _make_category(2, "Monturas")
        fake.exec.return_value.all.return_value = [cat1, cat2]
        dlg = _ProductoDialog()
        qtbot.addWidget(dlg)
        assert dlg._categoria.count() == 2
        assert dlg._categoria.itemText(0) == "Lentes"
        assert dlg._categoria.itemText(1) == "Monturas"

    def test_load_categories_vacio(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        dlg = _ProductoDialog()
        qtbot.addWidget(dlg)
        assert dlg._categoria.count() == 0


class TestProductoDialogValidacion:
    """Tests for _ProductoDialog._validate_and_accept."""

    def test_nombre_vacio_muestra_warning(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        dlg = _ProductoDialog()
        qtbot.addWidget(dlg)
        warned = []
        mocker.patch.object(
            QMessageBox,
            "warning",
            side_effect=lambda *_a, **_k: warned.append("warn"),
        )
        dlg._nombre.setText("")
        dlg._cost_price.setText("10.00")
        dlg._sale_price.setText("20.00")
        dlg._validate_and_accept()
        assert warned
        assert dlg.result() != QDialog.DialogCode.Accepted

    def test_costo_vacio_muestra_warning(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        dlg = _ProductoDialog()
        qtbot.addWidget(dlg)
        warned = []
        mocker.patch.object(
            QMessageBox,
            "warning",
            side_effect=lambda *_a, **_k: warned.append("warn"),
        )
        dlg._nombre.setText("Producto")
        dlg._cost_price.setText("")
        dlg._sale_price.setText("20.00")
        dlg._validate_and_accept()
        assert warned
        assert dlg.result() != QDialog.DialogCode.Accepted

    def test_precio_venta_vacio_muestra_warning(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        dlg = _ProductoDialog()
        qtbot.addWidget(dlg)
        warned = []
        mocker.patch.object(
            QMessageBox,
            "warning",
            side_effect=lambda *_a, **_k: warned.append("warn"),
        )
        dlg._nombre.setText("Producto")
        dlg._cost_price.setText("10.00")
        dlg._sale_price.setText("")
        dlg._validate_and_accept()
        assert warned
        assert dlg.result() != QDialog.DialogCode.Accepted

    def test_validacion_ok_acepta(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        dlg = _ProductoDialog()
        qtbot.addWidget(dlg)
        dlg._nombre.setText("Producto")
        dlg._cost_price.setText("10.00")
        dlg._sale_price.setText("20.00")
        dlg._validate_and_accept()
        assert dlg.result() == QDialog.DialogCode.Accepted


class TestProductoDialogGetData:
    """Tests for _ProductoDialog.get_data."""

    def test_get_data_basico(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        dlg = _ProductoDialog()
        qtbot.addWidget(dlg)
        dlg._nombre.setText("Lente Bifocal")
        dlg._barcode.setText("1234567890123")
        dlg._cost_price.setText("10.00")
        dlg._sale_price.setText("25.00")
        dlg._stock.setText("50")
        dlg._min_stock.setText("5")
        dlg._description.setPlainText("Descripción de prueba")
        data = dlg.get_data()
        assert data["name"] == "Lente Bifocal"
        assert data["barcode"] == "1234567890123"
        assert data["cost_price_usd"] == Decimal("10.00")
        assert data["sale_price_usd"] == Decimal("25.00")
        assert data["stock_quantity"] == 50
        assert data["min_stock"] == 5
        assert data["description"] == "Descripción de prueba"
        assert "image_path" not in data

    def test_get_data_barcode_vacio_es_none(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        dlg = _ProductoDialog()
        qtbot.addWidget(dlg)
        dlg._nombre.setText("Producto")
        dlg._barcode.setText("")
        dlg._cost_price.setText("10.00")
        dlg._sale_price.setText("20.00")
        data = dlg.get_data()
        assert data["barcode"] is None

    def test_get_data_description_vacia_es_none(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        dlg = _ProductoDialog()
        qtbot.addWidget(dlg)
        dlg._nombre.setText("Producto")
        dlg._cost_price.setText("10.00")
        dlg._sale_price.setText("20.00")
        dlg._description.setPlainText("")
        data = dlg.get_data()
        assert data["description"] is None

    def test_get_data_con_imagen(
        self, qtbot: QtBot, mocker: MockerFixture, tmp_path
    ) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        dlg = _ProductoDialog()
        qtbot.addWidget(dlg)
        dlg._nombre.setText("Producto")
        dlg._cost_price.setText("10.00")
        dlg._sale_price.setText("20.00")
        dlg._imagen_origen = str(tmp_path / "foto.jpg")
        mock_copy = mocker.patch(
            "opticamanager.ui.views.inventario_view._copiar_imagen",
            return_value="images/test.jpg",
        )
        data = dlg.get_data()
        assert data["image_path"] == "images/test.jpg"
        mock_copy.assert_called_once_with(str(tmp_path / "foto.jpg"))

    def test_get_data_stock_vacio_es_cero(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        dlg = _ProductoDialog()
        qtbot.addWidget(dlg)
        dlg._nombre.setText("Producto")
        dlg._cost_price.setText("10.00")
        dlg._sale_price.setText("20.00")
        dlg._stock.setText("")
        dlg._min_stock.setText("")
        data = dlg.get_data()
        assert data["stock_quantity"] == 0
        assert data["min_stock"] == 0


class TestProductoDialogFillForm:
    """Tests for _ProductoDialog._fill_form."""

    def test_fill_form_con_producto_completo(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        fake, _ = _fake_session(mocker)
        cat = _make_category(1, "Lentes")
        fake.exec.return_value.all.return_value = [cat]
        product = _make_product(
            barcode="1234567890123",
            description="Una descripción",
            image_path=None,
        )
        dlg = _ProductoDialog(producto=product)
        qtbot.addWidget(dlg)
        assert dlg._nombre.text() == "Lente Bifocal"
        assert dlg._barcode.text() == "1234567890123"
        assert dlg._cost_price.text() == "10.00"
        assert dlg._sale_price.text() == "25.00"
        assert dlg._stock.text() == "50"
        assert dlg._min_stock.text() == "5"
        assert "Una descripción" in dlg._description.toPlainText()

    def test_fill_form_sin_barcode_ni_descripcion(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        product = _make_product(barcode=None, description=None)
        dlg = _ProductoDialog(producto=product)
        qtbot.addWidget(dlg)
        assert dlg._barcode.text() == ""
        assert dlg._description.toPlainText() == ""

    def test_fill_form_con_imagen_existente(
        self, qtbot: QtBot, mocker: MockerFixture, tmp_path
    ) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        # _fill_form does: IMAGES_DIR.parent / p.image_path
        img_dir = tmp_path / "images"
        img_dir.mkdir()
        img_file = tmp_path / "test.jpg"
        img_file.write_bytes(b"\xff\xd8\xff")  # Minimal JPEG
        from opticamanager.ui.views import inventario_view

        mocker.patch.object(inventario_view, "IMAGES_DIR", img_dir)
        product = _make_product(image_path="test.jpg")
        dlg = _ProductoDialog(producto=product)
        qtbot.addWidget(dlg)
        # _fill_form ran without crashing and filled the name correctly
        assert dlg._nombre.text() == "Lente Bifocal"
        # Image path branch was entered (file exists at IMAGES_DIR.parent / "test.jpg")
        assert dlg._imagen_origen is None  # _fill_form doesn't set _imagen_origen

    def test_fill_form_con_categoria_correcta(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        fake, _ = _fake_session(mocker)
        cat1 = _make_category(1, "Lentes")
        cat2 = _make_category(2, "Monturas")
        fake.exec.return_value.all.return_value = [cat1, cat2]
        product = _make_product(category_id=2)
        dlg = _ProductoDialog(producto=product)
        qtbot.addWidget(dlg)
        assert dlg._categoria.currentData() == 2
        assert dlg._categoria.currentText() == "Monturas"


class TestProductoDialogImagen:
    """Tests for image selection and clearing."""

    def test_limpiar_imagen(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        dlg = _ProductoDialog()
        qtbot.addWidget(dlg)
        dlg._imagen_origen = "/fake/path.jpg"
        dlg._btn_limpiar.setVisible(True)
        dlg._limpiar_imagen()
        assert dlg._imagen_origen is None
        assert not dlg._btn_limpiar.isVisible()

    def test_seleccionar_imagen_cancelado(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        dlg = _ProductoDialog()
        qtbot.addWidget(dlg)
        mocker.patch(
            "opticamanager.ui.views.inventario_view.QFileDialog.getOpenFileName",
            return_value=("", ""),
        )
        dlg._seleccionar_imagen()
        assert dlg._imagen_origen is None

    def test_seleccionar_imagen_exitosa(
        self, qtbot: QtBot, mocker: MockerFixture, tmp_path
    ) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        dlg = _ProductoDialog()
        qtbot.addWidget(dlg)
        img_path = str(tmp_path / "foto.jpg")
        mocker.patch(
            "opticamanager.ui.views.inventario_view.QFileDialog.getOpenFileName",
            return_value=(img_path, "Images"),
        )
        # QPixmap.isNull will be True for a non-image file, but we test the path is set
        dlg._seleccionar_imagen()
        assert dlg._imagen_origen == img_path


class TestProductoDialogCrearCategoriaInline:
    """Tests for inline category creation."""

    def test_crear_categoria_cancelado(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        dlg = _ProductoDialog()
        qtbot.addWidget(dlg)
        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = QDialog.DialogCode.Rejected
        mocker.patch(
            "opticamanager.ui.views.categorias_view._CategoryDialog",
            return_value=mock_dlg,
        )
        initial_count = dlg._categoria.count()
        dlg._crear_categoria_inline()
        assert dlg._categoria.count() == initial_count

    def test_crear_categoria_exitosa(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        dlg = _ProductoDialog()
        qtbot.addWidget(dlg)
        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = QDialog.DialogCode.Accepted
        mock_dlg.get_data.return_value = {"name": "Nueva Cat"}
        mocker.patch(
            "opticamanager.ui.views.categorias_view._CategoryDialog",
            return_value=mock_dlg,
        )
        new_cat = MagicMock()
        new_cat.name = "Nueva Cat"
        new_cat.id = 99
        mocker.patch(
            "opticamanager.ui.views.inventario_view.create_category",
            return_value=new_cat,
        )
        dlg._crear_categoria_inline()
        assert dlg._categoria.count() == 1
        assert dlg._categoria.itemText(0) == "Nueva Cat"

    def test_crear_categoria_error(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        dlg = _ProductoDialog()
        qtbot.addWidget(dlg)
        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = QDialog.DialogCode.Accepted
        mock_dlg.get_data.return_value = {"name": "Cat Error"}
        mocker.patch(
            "opticamanager.ui.views.categorias_view._CategoryDialog",
            return_value=mock_dlg,
        )
        mocker.patch(
            "opticamanager.ui.views.inventario_view.create_category",
            side_effect=Exception("DB error"),
        )
        mocker.patch(
            "opticamanager.ui.views.inventario_view.dialogo_error",
        )
        dlg._crear_categoria_inline()
        # Should not crash, dialogo_error should be called


# ── _MovimientosDialog Tests ────────────────────────────────────────────


class TestMovimientosDialogCreacion:
    """Tests for _MovimientosDialog creation and data loading.

    Note: __init__ calls _load_productos() then _load_data(). QComboBox signals
    can fire _load_data() during _load_productos(). We use return_value (not
    side_effect) for safe init, then call _load_data() manually.
    """

    def test_creacion_basica(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        dlg = _MovimientosDialog()
        qtbot.addWidget(dlg)
        assert dlg.windowTitle() == "Historial de Movimientos"

    def test_creacion_con_prefiltro(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        dlg = _MovimientosDialog(product_id=1)
        qtbot.addWidget(dlg)
        assert dlg._prefiltro_id == 1

    def test_load_productos_pobla_filtro(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        fake, _ = _fake_session(mocker)
        prod1 = _make_product(1, "Lente 1")
        prod2 = _make_product(2, "Lente 2")

        # exec() is called with different statements for products vs logs.
        # Use side_effect on exec() itself to distinguish.
        def exec_side_effect(stmt):
            result = MagicMock()
            # column_descriptions is a property (not callable)
            descs = stmt.column_descriptions
            entity = descs[0].get("entity") if descs else None
            if entity and entity.__name__ == "InventoryLog":
                result.all.return_value = []
            else:
                result.all.return_value = [prod1, prod2]
            return result

        fake.exec.side_effect = exec_side_effect
        dlg = _MovimientosDialog()
        qtbot.addWidget(dlg)
        # "Todos los productos" + 2 products
        assert dlg._filtro.count() == 3
        assert dlg._filtro.itemText(0) == "Todos los productos"
        assert dlg._filtro.itemText(1) == "[1] Lente 1"
        assert dlg._filtro.itemText(2) == "[2] Lente 2"

    def test_load_data_vacio(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        dlg = _MovimientosDialog()
        qtbot.addWidget(dlg)
        assert dlg._tabla.row_count() == 0

    def test_load_data_con_movimientos(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        fake, _ = _fake_session(mocker)
        prod = _make_product()
        user = _make_user()
        log = _make_inventory_log(quantity=10, reason="Compra")
        fake.exec.return_value.all.return_value = []
        dlg = _MovimientosDialog()
        qtbot.addWidget(dlg)
        # Manually call _load_data with controlled data
        fake.exec.return_value.all.return_value = [log]
        fake.get.side_effect = lambda model, ident: {1: prod}.get(ident, user)
        dlg._load_data()
        assert dlg._tabla.row_count() == 1

    def test_load_data_con_movimiento_negativo(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        fake, _ = _fake_session(mocker)
        prod = _make_product()
        user = _make_user()
        log = _make_inventory_log(quantity=-5, reason="Venta")
        fake.exec.return_value.all.return_value = []
        dlg = _MovimientosDialog()
        qtbot.addWidget(dlg)
        fake.exec.return_value.all.return_value = [log]
        fake.get.side_effect = lambda model, ident: {1: prod}.get(ident, user)
        dlg._load_data()
        assert dlg._tabla.row_count() == 1

    @pytest.mark.parametrize("qty", ["abc", None])
    def test_load_data_con_quantity_no_numerica(
        self, qtbot: QtBot, mocker: MockerFixture, qty
    ) -> None:
        """A corrupt quantity (str or None) counts as not positive, with no crash."""
        fake, _ = _fake_session(mocker)
        prod = _make_product()
        user = _make_user()
        log = _make_inventory_log(quantity=qty, reason="Venta")
        fake.exec.return_value.all.return_value = []
        dlg = _MovimientosDialog()
        qtbot.addWidget(dlg)
        fake.exec.return_value.all.return_value = [log]
        fake.get.side_effect = lambda model, ident: {1: prod}.get(ident, user)
        dlg._load_data()
        assert dlg._tabla.row_count() == 1
        # No "+" sign and no TypeError
        item = dlg._tabla.model().item(0, 3)
        assert item is not None
        assert item.text() == str(qty)

    def test_load_data_con_producto_none(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        fake, _ = _fake_session(mocker)
        log = _make_inventory_log()
        fake.exec.return_value.all.return_value = []
        dlg = _MovimientosDialog()
        qtbot.addWidget(dlg)
        fake.exec.return_value.all.return_value = [log]
        fake.get.return_value = None
        dlg._load_data()
        assert dlg._tabla.row_count() == 1

    def test_close_button(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        dlg = _MovimientosDialog()
        qtbot.addWidget(dlg)
        btn_cerrar = dlg.findChild(QPushButton, "")
        for btn in dlg.findChildren(QPushButton):
            if "Cerrar" in btn.text():
                btn_cerrar = btn
                break
        assert btn_cerrar is not None
        qtbot.mouseClick(btn_cerrar, Qt.MouseButton.LeftButton)
        assert dlg.result() == QDialog.DialogCode.Accepted


# ── InventarioView Tests ────────────────────────────────────────────────


class TestInventarioViewCreacion:
    """Smoke tests for InventarioView creation."""

    def test_creacion_basica(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        view = InventarioView()
        qtbot.addWidget(view)
        assert isinstance(view, InventarioView)

    def test_titulo_visible(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        view = InventarioView()
        qtbot.addWidget(view)
        from PyQt6.QtWidgets import QLabel

        titles = view.findChildren(QLabel, "title-h2")
        assert len(titles) >= 1
        assert "Inventario" in titles[0].text()

    def test_botones_toolbar(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        view = InventarioView()
        qtbot.addWidget(view)
        buttons = view.findChildren(QPushButton)
        texts = [b.text() for b in buttons]
        assert any("Nuevo Producto" in t for t in texts)
        assert any("Editar" in t for t in texts)
        assert any("Eliminar" in t for t in texts)
        assert any("Movimientos" in t for t in texts)


class TestInventarioViewLoadData:
    """Tests for _load_data."""

    def test_load_data_vacio(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        view = InventarioView()
        qtbot.addWidget(view)
        assert view._tabla.row_count() == 0
        # Alert label text is empty when no low stock products
        assert view._alerta_label.text() == ""

    def test_load_data_con_productos(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        fake, _ = _fake_session(mocker)
        prod1 = _make_product(1, "Lente 1", category_id=1)
        prod2 = _make_product(2, "Lente 2", category_id=1)
        cat = _make_category(1, "Lentes")
        # First exec: list products, then get for each category
        fake.exec.return_value.all.return_value = [prod1, prod2]
        fake.get.return_value = cat
        view = InventarioView()
        qtbot.addWidget(view)
        assert view._tabla.row_count() == 2

    def test_load_data_stock_bajo_muestra_alerta(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        fake, _ = _fake_session(mocker)
        prod = _make_product(stock_quantity=2, min_stock=10)
        fake.exec.return_value.all.return_value = [prod]
        fake.get.return_value = None
        view = InventarioView()
        qtbot.addWidget(view)
        assert "1 producto" in view._alerta_label.text()
        assert view._alerta_label.text() != ""

    def test_load_data_sin_categoria(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        fake, _ = _fake_session(mocker)
        prod = _make_product(category_id=None)
        fake.exec.return_value.all.return_value = [prod]
        view = InventarioView()
        qtbot.addWidget(view)
        assert view._tabla.row_count() == 1

    def test_load_data_multiple_stock_bajo(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        fake, _ = _fake_session(mocker)
        prod1 = _make_product(1, stock_quantity=1, min_stock=10)
        prod2 = _make_product(2, stock_quantity=2, min_stock=5)
        fake.exec.return_value.all.return_value = [prod1, prod2]
        fake.get.return_value = None
        view = InventarioView()
        qtbot.addWidget(view)
        assert "2 producto" in view._alerta_label.text()

    def test_load_data_producto_inactivo(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        fake, _ = _fake_session(mocker)
        prod = _make_product(active=False)
        fake.exec.return_value.all.return_value = [prod]
        fake.get.return_value = None
        view = InventarioView()
        qtbot.addWidget(view)
        assert view._tabla.row_count() == 1


class TestInventarioViewNuevoProducto:
    """Tests for _nuevo_producto flow."""

    def test_dialogo_cancelado_no_crea_producto(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        view = InventarioView()
        qtbot.addWidget(view)
        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = QDialog.DialogCode.Rejected
        mocker.patch(
            "opticamanager.ui.views.inventario_view._ProductoDialog",
            return_value=mock_dlg,
        )
        view._nuevo_producto()
        # No commit should happen
        fake.add.assert_not_called()

    def test_dialogo_aceptado_crea_producto(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        view = InventarioView()
        qtbot.addWidget(view)
        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = QDialog.DialogCode.Accepted
        mock_dlg.get_data.return_value = {
            "name": "Nuevo Lente",
            "barcode": "123",
            "category_id": 1,
            "cost_price_usd": Decimal("10.00"),
            "sale_price_usd": Decimal("25.00"),
            "stock_quantity": 50,
            "min_stock": 5,
            "description": None,
        }
        mocker.patch(
            "opticamanager.ui.views.inventario_view._ProductoDialog",
            return_value=mock_dlg,
        )
        view._nuevo_producto()
        fake.add.assert_called_once()
        fake.commit.assert_called()

    def test_error_al_crear_muestra_error(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        fake.add.side_effect = Exception("DB error")
        view = InventarioView()
        qtbot.addWidget(view)
        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = QDialog.DialogCode.Accepted
        mock_dlg.get_data.return_value = {
            "name": "Nuevo Lente",
            "barcode": None,
            "category_id": None,
            "cost_price_usd": Decimal("10.00"),
            "sale_price_usd": Decimal("25.00"),
            "stock_quantity": 0,
            "min_stock": 0,
            "description": None,
        }
        mocker.patch(
            "opticamanager.ui.views.inventario_view._ProductoDialog",
            return_value=mock_dlg,
        )
        mock_error = mocker.patch(
            "opticamanager.ui.views.inventario_view.dialogo_error",
        )
        view._nuevo_producto()
        mock_error.assert_called_once()


class TestInventarioViewEditarProducto:
    """Tests for _editar_producto flow."""

    def test_sin_seleccion_muestra_info(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        view = InventarioView()
        qtbot.addWidget(view)
        msgs = []
        mocker.patch.object(
            QMessageBox,
            "information",
            side_effect=lambda *_a, **_k: msgs.append("info"),
        )
        view._editar_producto()
        assert msgs

    def test_producto_no_encontrado(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        view = InventarioView()
        qtbot.addWidget(view)
        _add_row_to_view(view)
        _select_first_row(view)
        fake.get.return_value = None
        view._editar_producto()
        # Should return without crash

    def test_dialogo_cancelado_no_edita(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        view = InventarioView()
        qtbot.addWidget(view)
        _add_row_to_view(view)
        _select_first_row(view)
        product = _make_product()
        fake.get.return_value = product
        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = QDialog.DialogCode.Rejected
        mocker.patch(
            "opticamanager.ui.views.inventario_view._ProductoDialog",
            return_value=mock_dlg,
        )
        view._editar_producto()
        fake.add.assert_not_called()

    def test_dialogo_aceptado_edita_producto(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        view = InventarioView()
        qtbot.addWidget(view)
        _add_row_to_view(view)
        _select_first_row(view)
        product = _make_product()
        fake.get.return_value = product
        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = QDialog.DialogCode.Accepted
        mock_dlg.get_data.return_value = {
            "name": "Lente Editado",
            "barcode": "123",
            "category_id": 1,
            "cost_price_usd": Decimal("15.00"),
            "sale_price_usd": Decimal("30.00"),
            "stock_quantity": 100,
            "min_stock": 10,
            "description": "Editado",
        }
        mocker.patch(
            "opticamanager.ui.views.inventario_view._ProductoDialog",
            return_value=mock_dlg,
        )
        view._editar_producto()
        fake.add.assert_called()
        fake.commit.assert_called()


class TestInventarioViewEliminarProducto:
    """Tests for _eliminar_producto flow."""

    def test_sin_seleccion_muestra_info(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        view = InventarioView()
        qtbot.addWidget(view)
        msgs = []
        mocker.patch.object(
            QMessageBox,
            "information",
            side_effect=lambda *_a, **_k: msgs.append("info"),
        )
        view._eliminar_producto()
        assert msgs

    def test_cancelar_eliminacion(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        view = InventarioView()
        qtbot.addWidget(view)
        _add_row_to_view(view)
        _select_first_row(view)
        mocker.patch(
            "opticamanager.ui.views.inventario_view.dialogo_confirmacion",
            return_value=False,
        )
        view._eliminar_producto()
        fake.delete.assert_not_called()

    def test_confirmar_eliminacion_exitosa(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        view = InventarioView()
        qtbot.addWidget(view)
        _add_row_to_view(view)
        _select_first_row(view)
        mocker.patch(
            "opticamanager.ui.views.inventario_view.dialogo_confirmacion",
            return_value=True,
        )
        product = _make_product()
        fake.get.return_value = product
        view._eliminar_producto()
        fake.delete.assert_called_once_with(product)
        fake.commit.assert_called()

    def test_producto_no_encontrado_no_crash(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        view = InventarioView()
        qtbot.addWidget(view)
        _add_row_to_view(view)
        _select_first_row(view)
        mocker.patch(
            "opticamanager.ui.views.inventario_view.dialogo_confirmacion",
            return_value=True,
        )
        fake.get.return_value = None
        view._eliminar_producto()
        # Should not crash, product not found → no delete

    def test_error_al_eliminar_muestra_error(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        view = InventarioView()
        qtbot.addWidget(view)
        _add_row_to_view(view)
        _select_first_row(view)
        mocker.patch(
            "opticamanager.ui.views.inventario_view.dialogo_confirmacion",
            return_value=True,
        )
        product = _make_product()
        fake.get.return_value = product
        fake.delete.side_effect = Exception("FK constraint")
        mock_error = mocker.patch(
            "opticamanager.ui.views.inventario_view.dialogo_error",
        )
        view._eliminar_producto()
        mock_error.assert_called_once()


class TestInventarioViewVerMovimientos:
    """Tests for _ver_movimientos flow."""

    def test_sin_seleccion_abre_dialogo_general(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        view = InventarioView()
        qtbot.addWidget(view)
        mock_dlg = MagicMock()
        mocker.patch(
            "opticamanager.ui.views.inventario_view._MovimientosDialog",
            return_value=mock_dlg,
        )
        view._ver_movimientos()
        mock_dlg.exec.assert_called_once()

    def test_con_seleccion_abre_dialogo_filtrado(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        view = InventarioView()
        qtbot.addWidget(view)
        _add_row_to_view(view)
        _select_first_row(view)
        mock_dlg = MagicMock()
        mocker.patch(
            "opticamanager.ui.views.inventario_view._MovimientosDialog",
            return_value=mock_dlg,
        )
        view._ver_movimientos()
        mock_dlg.exec.assert_called_once()


class TestInventarioViewStaticHelpers:
    """Tests for static helper methods."""

    def test_producto_id_modelo(self) -> None:
        model = MagicMock()
        item = MagicMock()
        item.text.return_value = "42"
        model.item.return_value = item
        assert InventarioView._producto_id_modelo(model, 0) == 42

    def test_producto_id_modelo_item_none(self) -> None:
        model = MagicMock()
        model.item.return_value = None
        assert InventarioView._producto_id_modelo(model, 0) == 0

    def test_producto_name_modelo(self) -> None:
        model = MagicMock()
        item = MagicMock()
        item.text.return_value = "Lente Bifocal"
        model.item.return_value = item
        assert InventarioView._producto_name_modelo(model, 0) == "Lente Bifocal"

    def test_producto_name_modelo_item_none(self) -> None:
        model = MagicMock()
        model.item.return_value = None
        assert InventarioView._producto_name_modelo(model, 0) == ""


class TestInventarioViewBotonesConexion:
    """Tests for button click connections.

    Patch at CLASS level BEFORE instantiation so signal-slot picks up mock.
    """

    def test_boton_editar_conecta(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        mock_editar = mocker.patch.object(InventarioView, "_editar_producto")
        view = InventarioView()
        qtbot.addWidget(view)
        mock_editar.reset_mock()
        qtbot.mouseClick(view._btn_editar, Qt.MouseButton.LeftButton)
        mock_editar.assert_called_once()

    def test_boton_eliminar_conecta(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        mock_eliminar = mocker.patch.object(InventarioView, "_eliminar_producto")
        view = InventarioView()
        qtbot.addWidget(view)
        mock_eliminar.reset_mock()
        qtbot.mouseClick(view._btn_eliminar, Qt.MouseButton.LeftButton)
        mock_eliminar.assert_called_once()

    def test_boton_nuevo_existe(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        view = InventarioView()
        qtbot.addWidget(view)
        for btn in view.findChildren(QPushButton):
            if "Nuevo Producto" in btn.text():
                assert btn is not None
                return
        raise AssertionError("Botón 'Nuevo Producto' no encontrado")

    def test_boton_movimientos_existe(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        fake, _ = _fake_session(mocker)
        fake.exec.return_value.all.return_value = []
        view = InventarioView()
        qtbot.addWidget(view)
        for btn in view.findChildren(QPushButton):
            if "Movimientos" in btn.text():
                assert btn is not None
                return
        raise AssertionError("Botón 'Movimientos' no encontrado")
