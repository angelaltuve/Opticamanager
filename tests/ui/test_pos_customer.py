"""Tests of POS customer search helpers and the selected-customer card.

These target pure functions plus _SaleTab display state (no DB, no session),
so they run headless with a module-scoped QApplication.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Iterator

import pytest
from PyQt6.QtCore import QModelIndex, Qt
from PyQt6.QtWidgets import QApplication
from pytest_mock import MockerFixture

from opticamanager.models import Customer
from opticamanager.ui.views.pos_view import (
    _CREATE_SENTINEL,
    _PLACEHOLDER_BUSCAR,
    _etiqueta_busqueda_cliente,
    _filtrar_clientes,
    _normalizar_texto,
    _parse_documento_busqueda,
    POSView,
    _SaleTab,
)


@pytest.fixture(scope="module")
def qapp() -> Iterator[object]:
    """Module-scoped QApplication so widgets can be created without qtbot."""
    app = QApplication.instance() or QApplication([])
    yield app


def _cliente(id_document: str, name: str, phone: str | None = None) -> Customer:
    return Customer(id_document=id_document, name=name, phone=phone)


class TestNormalizarTexto:
    def test_quita_acentos_y_minusculas(self) -> None:
        assert _normalizar_texto("José Ángel") == "jose angel"

    def test_transforma_diacriticos_y_casefold(self) -> None:
        assert _normalizar_texto("MARÍA Ñ") == "maria n"

    def test_vacio(self) -> None:
        assert _normalizar_texto("") == ""


class TestFiltrarClientes:
    def test_query_vacia_devuelve_vacio(self) -> None:
        c = _cliente("V-1", "Ana")
        assert _filtrar_clientes([c], "") == []

    def test_coincide_por_nombre_parcial(self) -> None:
        c = _cliente("V-1", "María Pérez")
        assert _filtrar_clientes([c], "perez") == [c]

    def test_coincide_por_cedula(self) -> None:
        c = _cliente("V-12345678", "Ana")
        assert _filtrar_clientes([c], "V-12") == [c]

    def test_coincide_por_telefono(self) -> None:
        c = _cliente("V-1", "Ana", phone="0414-1234567")
        assert _filtrar_clientes([c], "0414") == [c]

    def test_insensible_a_acentos(self) -> None:
        c = _cliente("V-1", "María José")
        assert _filtrar_clientes([c], "maria") == [c]

    def test_prioriza_prefijo_de_nombre(self) -> None:
        ana_rodriguez = _cliente("V-9", "Rodríguez Ana")
        ana_gomez = _cliente("V-8", "Ana Gómez")
        result = _filtrar_clientes([ana_rodriguez, ana_gomez], "ana")
        assert result == [ana_gomez, ana_rodriguez]

    def test_respeta_limite(self) -> None:
        clientes = [_cliente(f"V-{i}", f"Cliente {i}") for i in range(12)]
        assert len(_filtrar_clientes(clientes, "cliente")) == 8

    def test_limite_personalizado(self) -> None:
        clientes = [_cliente(f"V-{i}", f"Cliente {i}") for i in range(12)]
        assert len(_filtrar_clientes(clientes, "cliente", limite=3)) == 3

    def test_sin_coincidencias(self) -> None:
        c = _cliente("V-1", "Ana")
        assert _filtrar_clientes([c], "zzz") == []


class TestEtiquetaBusqueda:
    def test_incluye_documento(self) -> None:
        assert _etiqueta_busqueda_cliente(_cliente("V-123", "Ana")) == ("Ana  (V-123)")

    def test_incluye_telefono_cuando_existe(self) -> None:
        etiqueta = _etiqueta_busqueda_cliente(
            _cliente("V-123", "Ana", phone="0414-123")
        )
        assert "Ana  (V-123)" in etiqueta
        assert "0414-123" in etiqueta


class TestParseDocumentoBusqueda:
    def test_solo_numeros(self) -> None:
        assert _parse_documento_busqueda("12345678") == "12345678"

    def test_prefijo_y_guion(self) -> None:
        assert _parse_documento_busqueda("v-12345678") == "V-12345678"

    def test_prefijo_sin_guion(self) -> None:
        assert _parse_documento_busqueda("V12345678") == "V-12345678"

    def test_otros_prefijos(self) -> None:
        assert _parse_documento_busqueda("j-87654321") == "J-87654321"

    def test_nombre_no_es_documento(self) -> None:
        assert _parse_documento_busqueda("Juan Pérez") is None

    def test_vacio(self) -> None:
        assert _parse_documento_busqueda("") is None


class TestSaleTabCustomerCard:
    def test_tarjeta_oculta_sin_cliente(self, qapp) -> None:
        tab = _SaleTab()
        assert tab.customer_card.isHidden() is True
        assert tab.btn_pick_rx.isHidden() is True
        assert tab.btn_rx_history.isHidden() is True
        assert tab.customer_edit.placeholderText() != ""

    def test_tarjeta_visible_con_cliente(self, qapp) -> None:
        tab = _SaleTab()
        tab.session.customer = _cliente("V-123", "Ana", phone="0414-1234567")
        tab.set_customer_display()
        assert tab.customer_card.isHidden() is False
        assert tab.lbl_customer_name.text() == "Ana"
        assert "V-123" in tab.lbl_customer_meta.text()
        assert "0414-1234567" in tab.lbl_customer_meta.text()
        assert tab.btn_pick_rx.isHidden() is False
        assert tab.btn_rx_history.isHidden() is False

    def test_quitar_cliente_oculta_tarjeta(self, qapp) -> None:
        tab = _SaleTab()
        tab.session.customer = _cliente("V-1", "Luis", phone="0414-1234567")
        tab.set_customer_display()
        tab.session.customer = None
        tab.set_customer_display()
        assert tab.customer_card.isHidden() is True
        assert tab.btn_pick_rx.isHidden() is True
        assert tab.btn_rx_history.isHidden() is True

    def test_placeholder_buscar_definido(self, qapp) -> None:
        tab = _SaleTab()
        assert tab.customer_edit.placeholderText() == _PLACEHOLDER_BUSCAR
        assert _PLACEHOLDER_BUSCAR != ""
        assert _CREATE_SENTINEL == -1


class TestPOSViewCustomerPopup:
    """The suggestion popup preselects the first row so Enter activates it."""

    def _make_view(self, mocker: MockerFixture) -> tuple[POSView, _SaleTab]:
        mocker.patch(
            "opticamanager.ui.views.pos_view.get_iva_rate",
            return_value=Decimal("0.16"),
        )
        mocker.patch(
            "opticamanager.ui.views.pos_view.get_iva_rate_pct", return_value=16
        )
        mocker.patch(
            "opticamanager.ui.views.pos_view.convert_to_usd", return_value=None
        )
        view = POSView()
        view._configure_customer_completer()
        tab = next(iter(view._cart_tabs.values()))
        return view, tab

    def test_con_coincidencias_preselecciona_la_mejor(self, qapp, mocker) -> None:
        view, tab = self._make_view(mocker)
        ana = _cliente("V-1", "Ana Gómez")
        ana.id = 1
        luisa = _cliente("V-2", "Ana Luisa")
        luisa.id = 2
        view._customer_index = [luisa, ana]  # "ana" ranks "Ana Gómez" first
        view._customer_by_id = {1: ana, 2: luisa}

        view._update_customer_suggestions(tab, "ana")

        popup = view._customer_completer.popup()
        assert popup.currentIndex().row() == 0
        assert "Ana Gómez" in popup.model().index(0, 0).data()

    def test_sin_coincidencias_preselecciona_crear(self, qapp, mocker) -> None:
        view, tab = self._make_view(mocker)
        view._customer_index = []

        view._update_customer_suggestions(tab, "cliente nuevo")

        popup = view._customer_completer.popup()
        assert popup.currentIndex().row() == 0
        assert (
            popup.model().index(0, 0).data(Qt.ItemDataRole.UserRole) == _CREATE_SENTINEL
        )

    def test_completer_activacion_usa_overload_de_indice(self, qapp, mocker) -> None:
        """The `activated` signal connects to the QModelIndex overload, not str."""
        view, tab = self._make_view(mocker)
        ana = _cliente("V-1", "Ana Gómez")
        ana.id = 1
        view._customer_index = [ana]
        view._customer_by_id = {1: ana}
        view._update_customer_suggestions(tab, "Ana")

        # The str overload stays unconnected: emitting it sets no customer and
        # raises none of the `str.data()` AttributeError.
        view._customer_completer.activated[str].emit("Ana Gómez")
        assert tab.session.customer is None

        # The QModelIndex overload is connected and applies the customer.
        idx = view._customer_model.index(0, 0)
        view._customer_completer.activated[QModelIndex].emit(idx)
        assert tab.session.customer is not None
        assert tab.session.customer.id == 1

    def test_quitar_cliente_ignora_bool_de_clicked(self, qapp, mocker) -> None:
        """QPushButton.clicked emits a bool; the lambda must not shadow `tab`."""
        view, tab = self._make_view(mocker)
        ana = _cliente("V-1", "Ana Gómez")
        tab.session.customer = ana

        tab.btn_quit_customer.clicked.emit(True)
        tab.btn_quit_customer.clicked.emit(False)

        assert tab.session.customer is None
