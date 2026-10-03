"""Point of Sale: shopping cart and sale flow."""

from __future__ import annotations

import re
import unicodedata

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import TYPE_CHECKING, cast

from PyQt6.QtCore import QModelIndex, Qt, QTimer
from PyQt6.QtGui import QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QCompleter,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTabWidget,
    QToolButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from sqlmodel import select

from opticamanager.core.logging_config import get_logger
from opticamanager.core.session import UserSession
from opticamanager.db import SessionManager
from opticamanager.models import CashSession, Customer, Prescription, Product, Sale
from opticamanager.services import cash_session_service
from opticamanager.services.exchange_rate import (
    convert_to_bs,
    convert_to_usd,
    get_rate_info,
    get_usd_rate,
)
from opticamanager.services.stock_service import registrar_venta
from opticamanager.services.settings_service import get_iva_rate, get_iva_rate_pct
from opticamanager.ui.widgets.dialogs import dialogo_confirmacion, dialogo_error
from opticamanager.ui.widgets.exchange_rate_widget import ExchangeRateWidget
from opticamanager.ui.widgets.receipt_dialog import show_sale_receipt
from opticamanager.ui.widgets.table_widget import TablaPersonalizada
from opticamanager.ui.widgets.validators import (
    validador_cedula,
    validador_telefono,
)
from opticamanager.utils.formatters import (
    format_bs,
    format_usd,
    format_ve,
    format_ve_int,
)

if TYPE_CHECKING:
    from decimal import Decimal

    from opticamanager.ui.views.ventas_view import VentasView

log = get_logger(__name__)


# ──────────────────────────────────────────────
#  Available payment methods
# ──────────────────────────────────────────────

PAGO_MOVIL = "Pago Móvil"
ZELLE = "Zelle"
EFECTIVO_BS = "Efectivo Bs"
EFECTIVO_USD = "Efectivo Dólares"
MIXTO = "Mixto"
ABONO = "Abono"

PAYMENT_METHOD_CHOICES = [PAGO_MOVIL, ZELLE, EFECTIVO_BS, EFECTIVO_USD, MIXTO, ABONO]
# Methods usable as a single row inside a Mixto split
SPLIT_METHOD_CHOICES = [PAGO_MOVIL, ZELLE, EFECTIVO_BS, EFECTIVO_USD]


def _rate() -> Decimal | None:
    """Return the active USD→Bs rate, or None if unavailable."""
    info = get_rate_info()
    if info.rate is None or info.rate <= 0:
        return None
    return info.rate


# ──────────────────────────────────────────────
#  Customer search helpers
# ──────────────────────────────────────────────

_PLACEHOLDER_BUSCAR = "Buscar cliente por nombre, cédula o teléfono…"
_PLACEHOLDER_CAMBIAR = "Escribe para cambiar de cliente…"
_CREATE_SENTINEL = -1
_DOCUMENTO_RE = re.compile(r"^([VEJPG])?-?(\d{5,10})$", re.IGNORECASE)


def _normalizar_texto(value: str) -> str:
    """Casefold and strip diacritics so search is case- and accent-insensitive."""
    normalizado = unicodedata.normalize("NFD", value.casefold())
    return "".join(ch for ch in normalizado if unicodedata.category(ch) != "Mn")


def _filtrar_clientes(
    customers: list[Customer], query: str, limite: int = 8
) -> list[Customer]:
    """Return customers matching ``query`` in name, document or phone.

    Matches are substring-based (not prefix-only) and accent-insensitive.
    Customers whose name/document starts with the query rank first, then by name.
    """
    q = _normalizar_texto(query)
    if not q:
        return []
    coincidencias: list[tuple[int, Customer]] = []
    for c in customers:
        objetivo = _normalizar_texto(f"{c.name} {c.id_document} {c.phone or ''}")
        if q not in objetivo:
            continue
        relevancia = (
            0
            if _normalizar_texto(c.name).startswith(q)
            or _normalizar_texto(c.id_document).startswith(q)
            else 1
        )
        coincidencias.append((relevancia, c))
    coincidencias.sort(key=lambda par: (par[0], _normalizar_texto(par[1].name)))
    return [c for _, c in coincidencias[:limite]]


def _etiqueta_busqueda_cliente(c: Customer) -> str:
    """Render a customer as a searchable popup label."""
    etiqueta = f"{c.name}  ({c.id_document})"
    if c.phone:
        etiqueta += f"  ·  {c.phone}"
    return etiqueta


def _parse_documento_busqueda(text: str) -> str | None:
    """Extract a document id from free text like ``v-12345678`` or ``12345678``."""
    m = _DOCUMENTO_RE.match(text.strip())
    if not m:
        return None
    prefijo, numero = m.groups()
    return f"{prefijo.upper()}-{numero}" if prefijo else numero


# ──────────────────────────────────────────────
#  Customer form dialog
# ──────────────────────────────────────────────


class _CustomerFormDialog(QDialog):
    """Simple form to create a new customer inline."""

    def __init__(
        self, parent: QWidget | None = None, prefill: dict[str, str] | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Nuevo Cliente")
        self.setMinimumWidth(400)
        self._prefill = prefill or {}
        self._setup_ui()
        self._fill_prefill()

    def _setup_ui(self) -> None:
        form = QFormLayout()

        self._doc = QLineEdit()
        self._doc.setMaxLength(20)
        self._doc.setValidator(validador_cedula())
        form.addRow("Cédula:", self._doc)

        self._name = QLineEdit()
        self._name.setMaxLength(150)
        form.addRow("Nombre:", self._name)

        self._phone = QLineEdit()
        self._phone.setMaxLength(20)
        self._phone.setValidator(validador_telefono())
        form.addRow("Teléfono:", self._phone)

        self._email = QLineEdit()
        self._email.setMaxLength(100)
        form.addRow("Email:", self._email)

        buttons = QDialogButtonBox()
        btn_guardar = buttons.addButton(
            "Guardar", QDialogButtonBox.ButtonRole.AcceptRole
        )
        buttons.addButton("Cancelar", QDialogButtonBox.ButtonRole.RejectRole)
        btn_guardar.setProperty("success", True)
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(buttons)
        self.setLayout(layout)

    def _fill_prefill(self) -> None:
        """Pre-fill fields from search text so customers are created faster."""
        if self._prefill.get("id_document"):
            self._doc.setText(self._prefill["id_document"])
        if self._prefill.get("name"):
            self._name.setText(self._prefill["name"])
        if self._prefill.get("phone"):
            self._phone.setText(self._prefill["phone"])
        if self._prefill.get("email"):
            self._email.setText(self._prefill["email"])
        # Focus the field the cashier still needs to type.
        if self._prefill.get("id_document") and not self._prefill.get("name"):
            self._name.setFocus()
        elif self._prefill.get("name"):
            self._doc.setFocus()

    def _validate_and_accept(self) -> None:
        if not self._doc.text().strip():
            QMessageBox.warning(self, "Validación", "La cédula es obligatoria")
            return
        if not self._name.text().strip():
            QMessageBox.warning(self, "Validación", "El nombre es obligatorio")
            return
        self.accept()

    def get_data(self) -> dict:
        return {
            "id_document": self._doc.text().strip(),
            "name": self._name.text().strip(),
            "phone": self._phone.text().strip() or None,
            "email": self._email.text().strip() or None,
        }


def _create_customer_from_dialog(
    parent: QWidget | None, prefill: dict[str, str] | None = None
) -> Customer | None:
    """Open the new-customer dialog, persist, and return the created Customer."""
    dlg = _CustomerFormDialog(parent, prefill)
    if dlg.exec() != QDialog.DialogCode.Accepted:
        return None
    data = dlg.get_data()
    try:
        with SessionManager() as session:
            c = Customer(**data)
            session.add(c)
            session.commit()
            session.refresh(c)
            return c
    except Exception as e:
        dialogo_error(parent, "Error", "No se pudo crear el cliente", str(e))
        return None


# ──────────────────────────────────────────────
#  Prescription history dialog
# ──────────────────────────────────────────────


class _PrescriptionHistoryDialog(QDialog):
    """Show all prescriptions for a customer in a table."""

    def __init__(self, customer: Customer, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._customer = customer
        self._selected_prescription: Prescription | None = None
        self.setWindowTitle(f"Recetas — {customer.name}")
        self.setMinimumSize(700, 450)
        self._setup_ui()
        self._load_data()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout()

        header = QLabel(
            f"<b>Cliente:</b> {self._customer.name} ({self._customer.id_document})"
        )
        header.setObjectName("rx-header")
        layout.addWidget(header)

        self._tabla = TablaPersonalizada()
        self._tabla.set_columns(
            [
                "ID",
                "Fecha",
                "OD Esf",
                "OD Cil",
                "OD Eje",
                "OI Esf",
                "OI Cil",
                "OI Eje",
                "DP",
                "Notas",
            ]
        )
        self._tabla.view().setColumnHidden(0, True)
        self._tabla.view().doubleClicked.connect(self._show_detail)
        layout.addWidget(self._tabla)

        # Row of actions. When opened to PICK a prescription, show "Usar receta".
        btn_row = QHBoxLayout()
        self._btn_use = QPushButton("Usar receta para esta venta")
        self._btn_use.setVisible(False)
        self._btn_use.clicked.connect(self._accept_selection)
        btn_row.addWidget(self._btn_use)

        btn_detail = QPushButton("Ver detalle")
        btn_detail.clicked.connect(self._show_detail)
        btn_row.addWidget(btn_detail)

        btn_print = QPushButton("Imprimir receta")
        btn_print.clicked.connect(self._print_prescription)
        btn_row.addWidget(btn_print)

        btn_row.addStretch()
        btn_close = QPushButton("Cerrar")
        btn_close.clicked.connect(self.reject)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

        self.setLayout(layout)

    def set_pick_mode(self) -> None:
        """Show the 'Usar receta' button so the dialog returns a selection."""
        self._btn_use.setVisible(True)

    def _load_data(self) -> None:
        self._tabla.clear()
        with SessionManager() as session:
            stmt = (
                select(Prescription)
                .where(Prescription.customer_id == self._customer.id)  # type: ignore[reportAttributeAccessIssue]
                .order_by(Prescription.issued_date.desc())  # type: ignore[reportAttributeAccessIssue]
            )
            recetas = session.exec(stmt).all()

        for r in recetas:
            self._tabla.add_row(
                [
                    str(r.id) if r.id else "",
                    r.issued_date.isoformat(),
                    self._fmt_opt(r.od_sphere),
                    self._fmt_opt(r.od_cylinder),
                    str(r.od_axis or ""),
                    self._fmt_opt(r.os_sphere),
                    self._fmt_opt(r.os_cylinder),
                    str(r.os_axis or ""),
                    self._fmt_opt(r.pupillary_distance, unit="mm"),
                    (r.notes[:50] + "…")
                    if r.notes and len(r.notes) > 50
                    else (r.notes or ""),
                ]
            )

    @staticmethod
    def _fmt_opt(value: Decimal | None, unit: str = "") -> str:
        if value is None:
            return ""
        return f"{format_ve(value)}{unit}"

    def _current_row_id(self) -> int:
        row = self._tabla.view().currentIndex().row()
        if row < 0:
            return 0
        proxy = self._tabla.proxy()
        source_idx = proxy.mapToSource(proxy.index(row, 0))
        model = self._tabla.model()
        item = model.item(source_idx.row(), 0)
        return int(item.text()) if item else 0

    def _accept_selection(self) -> None:
        rx_id = self._current_row_id()
        if not rx_id:
            QMessageBox.information(
                self, "Seleccionar", "Seleccione una receta de la tabla"
            )
            return
        with SessionManager() as session:
            self._selected_prescription = session.get(Prescription, rx_id)
        self.accept()

    def _show_detail(self) -> None:
        rx_id = self._current_row_id()
        if not rx_id:
            QMessageBox.information(
                self, "Detalle", "Seleccione una receta de la tabla"
            )
            return

        with SessionManager() as session:
            receta = session.get(Prescription, rx_id)
            if not receta:
                return

        detail = (
            f"<b>Fecha:</b> {receta.issued_date.isoformat()}<br><br>"
            f"<b>Ojo Derecho (OD)</b><br>"
            f"  Esfera: {self._fmt_opt(receta.od_sphere)}<br>"
            f"  Cilindro: {self._fmt_opt(receta.od_cylinder)}<br>"
            f"  Eje: {receta.od_axis or '—'}<br>"
            f"  Adición: {self._fmt_opt(receta.od_addition)}<br><br>"
            f"<b>Ojo Izquierdo (OI)</b><br>"
            f"  Esfera: {self._fmt_opt(receta.os_sphere)}<br>"
            f"  Cilindro: {self._fmt_opt(receta.os_cylinder)}<br>"
            f"  Eje: {receta.os_axis or '—'}<br>"
            f"  Adición: {self._fmt_opt(receta.os_addition)}<br><br>"
            f"<b>DP:</b> {self._fmt_opt(receta.pupillary_distance, 'mm')}<br>"
            f"<b>Notas:</b> {receta.notes or '—'}"
        )
        QMessageBox.information(
            self,
            f"Receta #{rx_id}",
            detail,
        )

    def _print_prescription(self) -> None:
        """Save the selected prescription as PDF."""
        rx_id = self._current_row_id()
        if not rx_id:
            QMessageBox.information(
                self, "Imprimir", "Seleccione una receta de la tabla"
            )
            return

        try:
            from opticamanager.services.pdf_service import suggest_prescription_path

            default_path = suggest_prescription_path(rx_id)
        except Exception as e:
            log.error("Error al preparar la receta PDF: %s", e)
            dialogo_error(self, "Error", "No se pudo preparar la receta PDF", str(e))
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Guardar receta PDF",
            str(default_path),
            "PDF (*.pdf)",
        )
        if not path:
            return
        try:
            from opticamanager.services.pdf_service import generate_prescription

            generate_prescription(rx_id, path)
            QMessageBox.information(
                self,
                "Receta generada",
                f"Receta guardada en:\n{path}",
            )
        except Exception as e:
            log.error("Error al generar receta PDF: %s", e)
            dialogo_error(self, "Error", "No se pudo generar la receta PDF", str(e))

    @property
    def selected_prescription(self) -> Prescription | None:
        return self._selected_prescription


# ──────────────────────────────────────────────
#  Cart item representation
# ──────────────────────────────────────────────


class _CartItem:
    """Internal cart item holding product info and quantity."""

    def __init__(
        self,
        product_id: int,
        name: str,
        unit_price: Decimal,
        unit_price_usd: Decimal,
        quantity: int = 1,
    ) -> None:
        self.product_id = product_id
        self.name = name
        self.unit_price = unit_price  # Bs price at transaction time
        self.unit_price_usd = unit_price_usd  # Original USD price
        self.quantity = quantity

    @property
    def subtotal(self) -> Decimal:
        return (self.unit_price * self.quantity).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )


# ──────────────────────────────────────────────
#  Cart session (one per parallel-sale tab)
# ──────────────────────────────────────────────


class _CartSession:
    """Data for one independent sale (per tab)."""

    def __init__(self) -> None:
        self.cart: list[_CartItem] = []
        self.customer: Customer | None = None
        self.prescription: Prescription | None = None

    def cart_empty(self) -> bool:
        return not self.cart

    def subtotal(self) -> Decimal:
        return (Decimal("0") + sum(ci.subtotal for ci in self.cart)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    def iva(self) -> Decimal:
        return (self.subtotal() * get_iva_rate()).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    def total(self) -> Decimal:
        return (self.subtotal() + self.iva()).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )


# ──────────────────────────────────────────────
#  Payment selection dialog
# ──────────────────────────────────────────────


class _MixtoRow:
    """One payment row inside the Mixto section."""

    def __init__(self, parent: QWidget) -> None:
        self.method_combo: QComboBox = QComboBox()
        self.method_combo.addItems(SPLIT_METHOD_CHOICES)
        self.amount_spin: QDoubleSpinBox = QDoubleSpinBox()
        self.amount_spin.setRange(0, 9_999_999.99)
        self.amount_spin.setDecimals(2)
        self.amount_spin.setPrefix("Bs. ")
        self.delete_btn: QPushButton = QPushButton("✕")


class _PaymentDialog(QDialog):
    """Dialog for selecting payment method with a modern mixed-payment UI."""

    PAYMENT_METHODS = PAYMENT_METHOD_CHOICES

    def __init__(
        self,
        total: Decimal,
        total_usd: Decimal | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._total = total
        self._total_usd = total_usd if total_usd is not None else Decimal("0")
        self._payment_method: str = EFECTIVO_BS
        self._payments: list[dict] = []
        self._amount_received: Decimal | None = None
        self._change: Decimal | None = None
        self._mixed_rows: list[_MixtoRow] = []
        self.setWindowTitle("Método de Pago")
        self.setMinimumWidth(520)
        self._setup_ui()
        self._on_method_changed(self._method_combo.currentText())

    # ── UI ─────────────────────────────────────

    def _setup_ui(self) -> None:
        layout = QVBoxLayout()

        # Total display
        total_text = f"Total a cobrar: <b>{format_bs(self._total)}</b>"
        if self._total_usd:
            total_text += f"  (<b>{format_usd(self._total_usd)}</b>)"
        total_label = QLabel(total_text)
        total_label.setObjectName("payment-total")
        layout.addWidget(total_label)

        # Method combo
        form = QFormLayout()
        self._method_combo = QComboBox()
        self._method_combo.addItems(self.PAYMENT_METHODS)
        self._method_combo.currentTextChanged.connect(self._on_method_changed)
        form.addRow("Método de pago:", self._method_combo)
        layout.addLayout(form)

        # ── Single-method cash widget ("Efectivo Bs" / "Efectivo Dólares") ──
        self._cash_widget = QWidget()
        cash_form = QFormLayout(self._cash_widget)
        cash_form.setContentsMargins(0, 0, 0, 0)

        self._received_spin = QDoubleSpinBox()
        self._received_spin.setRange(0, 9_999_999.99)
        self._received_spin.setDecimals(2)
        self._received_spin.setPrefix("Bs. ")
        self._received_spin.valueChanged.connect(self._on_amount_changed)
        cash_form.addRow("Monto recibido:", self._received_spin)

        self._equiv_label = QLabel("")
        self._equiv_label.setObjectName("payment-equiv")
        self._equiv_label.setVisible(False)
        cash_form.addRow("", self._equiv_label)

        self._change_label = QLabel("Bs. 0,00")
        self._change_label.setObjectName("change-pos")
        cash_form.addRow("Cambio:", self._change_label)

        layout.addWidget(self._cash_widget)

        # ── Mixto widget (rows) ──
        self._mixto_widget = QWidget()
        mixto_layout = QVBoxLayout(self._mixto_widget)
        mixto_layout.setContentsMargins(0, 0, 0, 0)
        mixto_layout.setSpacing(6)

        self._mixto_total_label = QLabel("")
        self._mixto_total_label.setObjectName("payment-total")
        mixto_layout.addWidget(self._mixto_total_label)

        self._mixto_rows_container = QVBoxLayout()
        self._mixto_rows_container.setContentsMargins(0, 0, 0, 0)
        self._mixto_rows_container.setSpacing(4)
        mixto_layout.addLayout(self._mixto_rows_container)

        btn_add_payment = QPushButton("+ Agregar pago")
        btn_add_payment.clicked.connect(self._add_mixed_row)
        mixto_layout.addWidget(btn_add_payment, alignment=Qt.AlignmentFlag.AlignLeft)

        layout.addWidget(self._mixto_widget)

        # ── Simple ("Pago Móvil" / "Zelle") info label ──
        self._simple_label = QLabel("")
        self._simple_label.setWordWrap(True)
        self._simple_label.setObjectName("payment-equiv")
        self._simple_label.setVisible(False)
        layout.addWidget(self._simple_label)

        # ── Abono widget (partial payment) ──
        self._abono_widget = QWidget()
        abono_form = QFormLayout(self._abono_widget)
        abono_form.setContentsMargins(0, 0, 0, 0)

        self._abono_spin = QDoubleSpinBox()
        self._abono_spin.setRange(0.01, 9_999_999.99)
        self._abono_spin.setDecimals(2)
        self._abono_spin.setPrefix("Bs. ")
        self._abono_spin.valueChanged.connect(self._on_abono_changed)
        abono_form.addRow("Monto a abonar:", self._abono_spin)

        self._abono_pendiente_label = QLabel("")
        self._abono_pendiente_label.setObjectName("payment-equiv")
        abono_form.addRow("Saldo pendiente:", self._abono_pendiente_label)

        layout.addWidget(self._abono_widget)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.setLayout(layout)
        self._preselect_default()

    def _preselect_default(self) -> None:
        """Pre-fill the first (non-Mixto) amount with the total."""
        self._received_spin.setValue(float(self._total))

    # ── Method switching ───────────────────────

    def _on_method_changed(self, method: str) -> None:
        self._payment_method = method
        is_mixto = method == MIXTO
        is_cash = method in (EFECTIVO_BS, EFECTIVO_USD)
        is_simple = method in (PAGO_MOVIL, ZELLE)
        is_abono = method == ABONO

        self._cash_widget.setVisible(is_cash)
        self._mixto_widget.setVisible(is_mixto)
        self._simple_label.setVisible(is_simple)
        self._abono_widget.setVisible(is_abono)

        if is_cash:
            if method == EFECTIVO_BS:
                self._received_spin.setPrefix("Bs. ")
                self._received_spin.setValue(float(self._total))
                self._equiv_label.setText("")
                self._equiv_label.setVisible(False)
                self._change_label.setText("Bs. 0,00")
            elif method == EFECTIVO_USD:
                rate = _rate()
                self._received_spin.setPrefix("$ ")
                default_usd = self._total_usd or (self._total / rate if rate else 0)
                self._received_spin.setValue(float(default_usd))
                self._equiv_label.setVisible(True)
                self._equiv_label.setText(
                    f"Equivale a {format_bs(self._bs_of_usd(self._received_spin.value()))}"
                )
                self._change_label.setText("$ 0,00")

        if is_simple:
            self._simple_label.setText(
                f"Se cobrará <b>{format_bs(self._total)}</b> por {method}."
            )

        if is_mixto:
            if not self._mixed_rows:
                self._add_mixed_row()
            self._update_mixto()

        if is_abono:
            self._abono_spin.setMaximum(float(self._total))
            self._abono_spin.setValue(float(self._total))
            self._abono_pendiente_label.setText(format_bs(Decimal("0")))

    def _on_abono_changed(self, value: float) -> None:
        """Update the pending balance display when abono amount changes."""
        abono = Decimal(str(value))
        pendiente = self._total - abono
        if pendiente < Decimal("0"):
            pendiente = Decimal("0")
        self._abono_pendiente_label.setText(format_bs(pendiente))

    @staticmethod
    def _bs_of_usd(usd: float) -> Decimal:
        """Convert a float USD amount to Bs using the active rate (0 if none)."""
        rate = _rate()
        if not rate:
            return Decimal("0")
        return (Decimal(str(usd)) * rate).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    # ── Cash amount changes ────────────────────

    def _on_amount_changed(self, value: float) -> None:
        if self._payment_method == EFECTIVO_BS:
            received = Decimal(str(value))
            change = received - self._total
            if change < Decimal("0"):
                change = Decimal("0")
            self._change_label.setText(format_bs(change))
        elif self._payment_method == EFECTIVO_USD:
            rate = _rate()
            self._equiv_label.setText(
                f"Equivale a {format_bs(self._bs_of_usd(value))}"
                + ("" if rate else "  (tasa no disponible)")
            )
            received_usd = Decimal(str(value))
            change_usd = received_usd - self._total_usd
            if change_usd < Decimal("0"):
                change_usd = Decimal("0")
            self._change_label.setText(format_usd(change_usd))

    # ── Mixto rows ─────────────────────────────

    def _add_mixed_row(self) -> None:
        row = _MixtoRow(self)
        row.amount_spin.valueChanged.connect(lambda _v, r=row: self._update_mixto(r))
        row.method_combo.currentTextChanged.connect(
            lambda _t, r=row: self._update_mixto(r)
        )
        row.delete_btn.clicked.connect(lambda: self._remove_mixed_row(row))

        h = QHBoxLayout()
        h.addWidget(row.method_combo)
        h.addWidget(row.amount_spin, 1)
        h.addWidget(row.delete_btn)
        row._layout = h  # type: ignore[attr-defined]
        self._mixto_rows_container.addLayout(h)
        self._mixed_rows.append(row)
        self._update_mixto()

    def _remove_mixed_row(self, row: _MixtoRow) -> None:
        if len(self._mixed_rows) <= 1:
            return
        if row in self._mixed_rows:
            self._mixed_rows.remove(row)
        layout = getattr(row, "_layout", None)
        if layout is not None:
            while layout.count():
                item = layout.takeAt(0)
                w = item.widget()
                if w is not None:
                    w.deleteLater()
            self._mixto_rows_container.removeItem(layout)
            delattr(row, "_layout")
        self._update_mixto()

    def _sum_mixed_bs(self, exclude: _MixtoRow | None = None) -> Decimal:
        total_bs = Decimal("0")
        for row in self._mixed_rows:
            if row is exclude:
                continue
            if row.method_combo.currentText() == EFECTIVO_USD:
                total_bs += self._bs_of_usd(row.amount_spin.value())
            else:
                total_bs += Decimal(str(row.amount_spin.value()))
        return total_bs.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def _balance_row(self) -> _MixtoRow | None:
        """Return the last non-USD row, the one that absorbs the remaining."""
        for row in reversed(self._mixed_rows):
            if row.method_combo.currentText() != EFECTIVO_USD:
                return row
        return None

    def _update_mixto(self, changed_row: _MixtoRow | None = None) -> None:
        if not self._mixed_rows:
            return
        # Keep the balance row (last non-USD) in sync with the remaining amount,
        # unless the user is editing that row right now (manual value respected).
        balance = self._balance_row()
        if balance is not None and balance is not changed_row:
            restante = self._total - self._sum_mixed_bs(exclude=balance)
            if restante < Decimal("0"):
                restante = Decimal("0")
            balance.amount_spin.blockSignals(True)
            balance.amount_spin.setValue(float(restante))
            balance.amount_spin.blockSignals(False)

        current_sum = self._sum_mixed_bs()
        remaining = self._total - current_sum
        if remaining < Decimal("0"):
            remaining = Decimal("0")
        self._mixto_total_label.setText(
            f"Suma {format_bs(current_sum)} — Falta {format_bs(remaining)} de "
            f"{format_bs(self._total)}"
        )

    # ── Acceptance ─────────────────────────────

    def _validate_and_accept(self) -> None:
        method = self._payment_method

        if method == EFECTIVO_BS:
            received = Decimal(str(self._received_spin.value()))
            if received < self._total:
                QMessageBox.warning(
                    self,
                    "Monto insuficiente",
                    f"El monto recibido ({format_bs(received)}) es menor "
                    f"al total ({format_bs(self._total)})",
                )
                return
            self._amount_received = received
            self._change = received - self._total
            self._payments = [
                {
                    "method": EFECTIVO_BS,
                    "currency": "Bs",
                    "amount": received,
                    "amount_bs": received,
                    "rate_used": None,
                }
            ]

        elif method == EFECTIVO_USD:
            rate = _rate()
            if not rate:
                QMessageBox.warning(
                    self,
                    "Tasa no disponible",
                    "No se pudo obtener la tasa BCV. Use otro método de pago.",
                )
                return
            received_usd = Decimal(str(self._received_spin.value()))
            total_usd = self._total_usd or (self._total / rate).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            if received_usd < total_usd:
                QMessageBox.warning(
                    self,
                    "Monto insuficiente",
                    f"El monto recibido ({format_usd(received_usd)}) es menor "
                    f"al total ({format_usd(total_usd)})",
                )
                return
            self._amount_received = received_usd
            self._change = received_usd - total_usd
            self._payments = [
                {
                    "method": EFECTIVO_USD,
                    "currency": "USD",
                    "amount": received_usd,
                    "amount_bs": self._bs_of_usd(float(received_usd)),
                    "rate_used": rate,
                }
            ]

        elif method in (PAGO_MOVIL, ZELLE):
            self._amount_received = self._total
            self._change = Decimal("0")
            self._payments = [
                {
                    "method": method,
                    "currency": "Bs",
                    "amount": self._total,
                    "amount_bs": self._total,
                    "rate_used": None,
                }
            ]

        elif method == MIXTO:
            total_bs = self._sum_mixed_bs()
            if total_bs < self._total:
                QMessageBox.warning(
                    self,
                    "Monto insuficiente",
                    f"Los pagos suman {format_bs(total_bs)}, menor "
                    f"al total ({format_bs(self._total)})",
                )
                return
            # Build the payments list from rows.
            payments: list[dict] = []
            has_cash = any(
                r.method_combo.currentText() == EFECTIVO_BS for r in self._mixed_rows
            )
            for row in self._mixed_rows:
                m = row.method_combo.currentText()
                amt = Decimal(str(row.amount_spin.value()))
                if amt <= 0:
                    continue
                if m == EFECTIVO_USD:
                    payments.append(
                        {
                            "method": m,
                            "currency": "USD",
                            "amount": amt,
                            "amount_bs": self._bs_of_usd(float(amt)),
                            "rate_used": _rate(),
                        }
                    )
                else:
                    payments.append(
                        {
                            "method": m,
                            "currency": "Bs",
                            "amount": amt,
                            "amount_bs": amt,
                            "rate_used": None,
                        }
                    )
            self._payments = payments
            # Excess = change if any row is cash-in-Bs, else hold as info.
            excess = (total_bs - self._total).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            if has_cash and excess > 0:
                self._change = excess
                self._amount_received = total_bs
            else:
                self._change = Decimal("0")
                self._amount_received = total_bs

        elif method == ABONO:
            abono = Decimal(str(self._abono_spin.value()))
            if abono <= 0:
                QMessageBox.warning(
                    self,
                    "Monto inválido",
                    "El monto a abonar debe ser mayor a cero.",
                )
                return
            if abono > self._total:
                QMessageBox.warning(
                    self,
                    "Monto excesivo",
                    f"El monto a abonar ({format_bs(abono)}) excede "
                    f"el total ({format_bs(self._total)}).",
                )
                return
            self._amount_received = abono
            self._change = Decimal("0")
            self._payments = [
                {
                    "method": ABONO,
                    "currency": "Bs",
                    "amount": abono,
                    "amount_bs": abono,
                    "rate_used": None,
                }
            ]

        self._payment_method = method
        self.accept()

    # ── Public properties ──────────────────────

    @property
    def payment_method(self) -> str:
        return self._payment_method

    @property
    def payments(self) -> list[dict]:
        return self._payments

    @property
    def amount_received(self) -> Decimal | None:
        return self._amount_received

    @property
    def change_amount(self) -> Decimal | None:
        return self._change


# ──────────────────────────────────────────────
#  Cash session dialogs
# ──────────────────────────────────────────────


class _CashOpenDialog(QDialog):
    """Dialog to open a cash register session."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._initial_balance: Decimal = Decimal("0")
        self.setWindowTitle("Apertura de Caja")
        self.setMinimumWidth(380)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout()

        title = QLabel("Apertura de Caja")
        title.setObjectName("dialog-title")
        layout.addWidget(title)

        form = QFormLayout()
        self._balance_spin = QDoubleSpinBox()
        self._balance_spin.setRange(0, 9_999_999.99)
        self._balance_spin.setDecimals(2)
        self._balance_spin.setPrefix("Bs. ")
        self._balance_spin.setValue(0)
        form.addRow("Saldo inicial:", self._balance_spin)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.setLayout(layout)

    def _accept(self) -> None:
        self._initial_balance = Decimal(str(self._balance_spin.value()))
        self.accept()

    @property
    def initial_balance(self) -> Decimal:
        return self._initial_balance


class _CashCloseDialog(QDialog):
    """Dialog to close a cash session with reconciliation."""

    def __init__(
        self, cs: CashSession, summary: dict, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._cs = cs
        self._summary = summary
        self._final_balance: Decimal = Decimal("0")
        self._difference: Decimal = Decimal("0")
        self.setWindowTitle("Cierre de Caja")
        self.setMinimumWidth(500)
        self._setup_ui()
        self._recalc()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout()

        title = QLabel("Cierre de Caja — Resumen")
        title.setObjectName("dialog-title")
        layout.addWidget(title)

        # Session info
        info = QFrame()
        info.setFrameStyle(QFrame.Shape.StyledPanel)
        info_layout = QVBoxLayout(info)

        opened = self._cs.opened_at.strftime("%d/%m/%Y %H:%M")
        info_layout.addWidget(QLabel(f"Apertura: {opened}"))
        info_layout.addWidget(
            QLabel(f"Saldo inicial: <b>{format_bs(self._cs.initial_balance)}</b>")
        )
        info_layout.addWidget(
            QLabel(
                f"Ventas en sesión: <b>{self._summary['sales_count']}</b> "
                f"(total {format_bs(self._summary['total_sales'])})"
            )
        )

        # Breakdown by payment method
        if self._summary["by_method"]:
            methods = QVBoxLayout()
            methods.setContentsMargins(0, 0, 0, 0)
            methods.addWidget(QLabel("<b>Desglose por método:</b>"))
            for method, amount in sorted(self._summary["by_method"].items()):
                methods.addWidget(QLabel(f"  {method}: {format_bs(amount)}"))
            info_layout.addLayout(methods)

        info_layout.addWidget(
            QLabel(
                f"Saldo esperado: <b>{format_bs(self._summary['expected_balance'])}</b>"
            )
        )
        layout.addWidget(info)

        # Counted cash input
        form = QFormLayout()
        self._final_spin = QDoubleSpinBox()
        self._final_spin.setRange(0, 99_999_999.99)
        self._final_spin.setDecimals(2)
        self._final_spin.setPrefix("Bs. ")
        self._final_spin.valueChanged.connect(self._recalc)
        form.addRow("Efectivo contado:", self._final_spin)
        layout.addLayout(form)

        # Difference
        diff_row = QHBoxLayout()
        diff_row.addWidget(QLabel("<b>Diferencia:</b>"))
        self._diff_label = QLabel("Bs. 0,00")
        self._diff_label.setObjectName("diff-pos")
        diff_row.addWidget(self._diff_label)
        diff_row.addStretch()
        layout.addLayout(diff_row)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.setLayout(layout)

    def _recalc(self) -> None:
        counted = Decimal(str(self._final_spin.value()))
        expected = self._summary["expected_balance"]
        self._difference = counted - expected
        _sign = "+" if self._difference > 0 else ""
        diff_text = f"Bs. {_sign}{format_ve(self._difference)}"
        if self._difference < 0:
            self._diff_label.setProperty("accent", "red")
        elif self._difference > 0:
            self._diff_label.setProperty("accent", "orange")
        else:
            self._diff_label.setProperty("accent", "green")
        self._diff_label.style().unpolish(self._diff_label)
        self._diff_label.style().polish(self._diff_label)
        self._diff_label.setText(diff_text)

    def _accept(self) -> None:
        self._final_balance = Decimal(str(self._final_spin.value()))

        if self._difference != 0:
            _sign = "+" if self._difference > 0 else ""
            msg = (
                f"Hay una diferencia de <b>Bs. {_sign}{format_ve(self._difference)}</b> "
                "entre el saldo esperado y el efectivo contado.\n\n"
                "¿Desea cerrar la caja de todas formas?"
            )
            if not dialogo_confirmacion(
                self, "Diferencia detectada", msg, rich_text=True
            ):
                return
        self.accept()

    @property
    def final_balance(self) -> Decimal:
        return self._final_balance

    @property
    def difference(self) -> Decimal:
        return self._difference


# ──────────────────────────────────────────────
#  POS main view
# ──────────────────────────────────────────────


class _SaleTab(QWidget):
    """Container widget for one sale tab (cart table, customer, totals)."""

    def __init__(self) -> None:
        super().__init__()
        self.session: _CartSession = _CartSession()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Customer search row + selected-customer card
        cust_row = QHBoxLayout()
        self.customer_edit = QLineEdit()
        self.customer_edit.setPlaceholderText(_PLACEHOLDER_BUSCAR)
        self.customer_edit.setClearButtonEnabled(True)
        cust_row.addWidget(self.customer_edit, 1)

        layout.addLayout(cust_row)

        # Card shown once a customer is selected for this sale
        self.customer_card = QFrame()
        self.customer_card.setObjectName("pos-customer-card")
        card_layout = QHBoxLayout(self.customer_card)
        card_layout.setContentsMargins(10, 6, 10, 6)
        card_layout.setSpacing(8)

        self.lbl_customer_name = QLabel("")
        self.lbl_customer_name.setObjectName("customer-name")
        card_layout.addWidget(self.lbl_customer_name)

        self.lbl_customer_meta = QLabel("")
        self.lbl_customer_meta.setObjectName("customer-meta")
        card_layout.addWidget(self.lbl_customer_meta)

        card_layout.addStretch()

        self.lbl_prescription = QLabel("")
        self.lbl_prescription.setObjectName("customer-label")
        card_layout.addWidget(self.lbl_prescription)

        self.btn_pick_rx = QPushButton("📋 Receta")
        self.btn_pick_rx.setVisible(False)
        card_layout.addWidget(self.btn_pick_rx)

        self.btn_rx_history = QPushButton("Historial")
        self.btn_rx_history.setVisible(False)
        card_layout.addWidget(self.btn_rx_history)

        self.btn_quit_customer = QPushButton("✕ Quitar")
        self.btn_quit_customer.setObjectName("btn-quit-customer")
        card_layout.addWidget(self.btn_quit_customer)

        self.customer_card.setVisible(False)
        layout.addWidget(self.customer_card)

        # Cart table
        self.cart_table = QTableWidget()
        self.cart_table.setColumnCount(5)
        self.cart_table.setHorizontalHeaderLabels(
            ["Producto", "Cant.", "Precio USD", "Precio Bs", "Subtotal Bs"]
        )
        self.cart_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.cart_table.verticalHeader().hide()
        self.cart_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        layout.addWidget(self.cart_table, stretch=1)

        # Totals
        totals_grid = QFormLayout()
        totals_grid.setSpacing(4)
        self.subtotal_label = QLabel("Bs. 0,00")
        self.subtotal_label.setObjectName("total-value")
        totals_grid.addRow("Subtotal:", self.subtotal_label)
        self.iva_label = QLabel("Bs. 0,00")
        self.iva_label.setObjectName("total-value")
        totals_grid.addRow(f"IVA ({get_iva_rate_pct()}%):", self.iva_label)
        self.total_label = QLabel("Bs. 0,00")
        self.total_label.setObjectName("total-bs")
        totals_grid.addRow("TOTAL:", self.total_label)
        self.total_usd_label = QLabel("$ 0,00")
        self.total_usd_label.setObjectName("total-usd")
        totals_grid.addRow("Total USD:", self.total_usd_label)
        layout.addLayout(totals_grid)

        # Actions
        btn_row = QHBoxLayout()
        self.btn_checkout = QPushButton("💳 Procesar Venta")
        self.btn_checkout.setProperty("success", True)
        self.btn_checkout.setMinimumHeight(32)
        btn_row.addWidget(self.btn_checkout)
        self.btn_clear = QPushButton("Cancelar")
        btn_row.addWidget(self.btn_clear)
        layout.addLayout(btn_row)

    def set_customer_display(self) -> None:
        c = self.session.customer
        rx = self.session.prescription
        if c:
            self.customer_card.setVisible(True)
            self.lbl_customer_name.setText(c.name)
            meta = c.id_document
            if c.phone:
                meta += f"   ·   {c.phone}"
            self.lbl_customer_meta.setText(meta)
            if rx and rx.id:
                fecha = rx.issued_date.strftime("%d/%m/%Y")
                self.lbl_prescription.setText(f"Receta #{rx.id} ({fecha})")
            else:
                self.lbl_prescription.setText("")
            self.btn_pick_rx.setVisible(True)
            self.btn_rx_history.setVisible(True)
        else:
            self.customer_card.setVisible(False)
            self.lbl_customer_name.setText("")
            self.lbl_customer_meta.setText("")
            self.lbl_prescription.setText("")
            self.btn_pick_rx.setVisible(False)
            self.btn_rx_history.setVisible(False)


class POSView(QWidget):
    """Point of sale: product panel on the left, sales tabs on the right."""

    def __init__(self) -> None:
        super().__init__()
        self._active_session: CashSession | None = None
        self._started: bool = False
        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.setInterval(60_000)  # every 60 s
        self._elapsed_timer.timeout.connect(self._update_elapsed_time)
        self._customer_completer: QCompleter | None = None
        self._customer_model: QStandardItemModel | None = None
        self._customer_index: list[Customer] = []
        self._customer_by_id: dict[int, Customer] = {}
        self._completer_tab: _SaleTab | None = None
        self._pending_search_tab: _SaleTab | None = None
        self._pending_search_text: str = ""
        self._customer_timer = QTimer(self)
        self._customer_timer.setSingleShot(True)
        self._customer_timer.setInterval(120)
        self._customer_timer.timeout.connect(self._flush_customer_search)
        # Cart sessions held keyed by tab index; each _SaleTab owns its session.
        self._cart_tabs: dict[int, _SaleTab] = {}
        # Sales history view (VentasView) embedded via QStackedWidget; built lazily.
        self._history_view: VentasView | None = None
        self._setup_ui()

    # ── UI setup ──────────────────────────────

    def _setup_ui(self) -> None:
        # Root stack: index 0 = POS (products + sale tabs), index 1 = sales history.
        self._stack = QStackedWidget()

        # ── POS page ──
        pos_page = QWidget()
        main_layout = QHBoxLayout(pos_page)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(10)

        # ── Left panel: product search + listing ──
        left = QVBoxLayout()
        left.setSpacing(6)

        title_left = QLabel("Productos")
        title_left.setObjectName("pos-title")
        left.addWidget(title_left)

        self._product_table = TablaPersonalizada()
        self._product_table.set_columns(
            ["ID", "Nombre", "Precio USD", "Precio Bs", "Stock"]
        )
        self._product_table.view().setColumnHidden(0, True)
        self._product_table.view().setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self._product_table.view().doubleClicked.connect(self._add_selected_to_cart)
        left.addWidget(self._product_table)

        left_widget = QWidget()
        left_widget.setLayout(left)

        # ── Right panel: session bar + sale tabs ──
        right = QVBoxLayout()
        right.setSpacing(6)

        title_right = QLabel("Ventas")
        title_right.setObjectName("pos-title")
        right.addWidget(title_right)

        # Session info bar
        self._session_bar = QFrame()
        self._session_bar.setFrameStyle(QFrame.Shape.StyledPanel)
        self._session_bar.setObjectName("pos-session-bar")
        session_layout = QHBoxLayout(self._session_bar)
        session_layout.setContentsMargins(8, 4, 8, 4)
        self._session_label = QLabel("🔴  Sesión: <b>Cerrada</b>")
        self._session_label.setObjectName("session-label")
        session_layout.addWidget(self._session_label)
        session_layout.addStretch()
        self._btn_history = QPushButton("🕘 Historial")
        self._btn_history.setFixedHeight(26)
        self._btn_history.setToolTip("Historial de ventas (solo admin)")
        self._btn_history.clicked.connect(self._show_history)
        self._btn_history.setVisible(UserSession().has_role("Admin"))
        session_layout.addWidget(self._btn_history)
        self._btn_open_session = QPushButton("🔓 Abrir Caja")
        self._btn_open_session.setFixedHeight(26)
        self._btn_open_session.clicked.connect(self._open_session_dialog)
        session_layout.addWidget(self._btn_open_session)
        self._btn_close_session = QPushButton("🔒 Cerrar Caja")
        self._btn_close_session.setFixedHeight(26)
        self._btn_close_session.clicked.connect(self._close_session_dialog)
        self._btn_close_session.setVisible(False)
        session_layout.addWidget(self._btn_close_session)
        right.addWidget(self._session_bar)

        # Exchange rate widget
        self._exchange_rate_widget = ExchangeRateWidget()
        right.addWidget(self._exchange_rate_widget)

        # Sale tabs
        self._tabs = QTabWidget()
        self._tabs.setObjectName("pos-tabs")
        self._tabs.setTabsClosable(True)
        self._tabs.setMovable(True)
        self._tabs.tabCloseRequested.connect(self._close_sale_tab)
        right.addWidget(self._tabs, stretch=1)

        self._btn_new_sale = QToolButton()
        self._btn_new_sale.setText("+")
        self._btn_new_sale.setObjectName("pos-new-sale-tab")
        self._btn_new_sale.setToolTip("Nueva venta")
        self._btn_new_sale.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_new_sale.clicked.connect(self._new_sale_tab)
        self._tabs.setCornerWidget(self._btn_new_sale, Qt.Corner.TopRightCorner)

        right_widget = QWidget()
        right_widget.setLayout(right)

        main_layout.addWidget(right_widget, 2)
        main_layout.addWidget(left_widget, 3)

        self._stack.addWidget(pos_page)

        # ── Sales history page ──
        history_page = QWidget()
        history_layout = QVBoxLayout(history_page)
        history_layout.setContentsMargins(8, 8, 8, 8)
        history_layout.setSpacing(8)

        history_header = QHBoxLayout()
        btn_back = QPushButton("← Volver al POS")
        btn_back.setFixedHeight(28)
        btn_back.clicked.connect(self._back_to_pos)
        history_header.addWidget(btn_back)
        history_header.addStretch()
        history_layout.addLayout(history_header)

        self._history_container = QVBoxLayout()
        history_layout.addLayout(self._history_container)
        self._stack.addWidget(history_page)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.addWidget(self._stack)

        # Start with one sale tab.
        self._new_sale_tab()

    def _show_history(self) -> None:
        """Show the sales history page, building VentasView lazily on first use."""
        if self._history_view is None:
            from opticamanager.ui.views.ventas_view import VentasView  # noqa: PLC0415

            self._history_view = VentasView()
            self._history_container.addWidget(self._history_view)
        self._history_view._load_ventas()
        self._stack.setCurrentIndex(1)

    def _back_to_pos(self) -> None:
        self._stack.setCurrentIndex(0)

    # ── Startup deferral ──────────────────────

    def showEvent(self, a0) -> None:  # noqa: N802
        """Keep the customer index in sync on every show; defer heavy work."""
        super().showEvent(a0)
        self._refresh_customer_index()
        if self._started:
            return
        self._started = True
        self._configure_customer_completer()
        self._ensure_session()
        self._load_products()

    def _configure_customer_completer(self) -> None:
        """Build a shared completer for customer search across sale tabs."""
        self._customer_model = QStandardItemModel(self)
        self._customer_completer = QCompleter(self._customer_model, self)
        self._customer_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._customer_completer.setCompletionMode(
            QCompleter.CompletionMode.UnfilteredPopupCompletion
        )
        self._customer_completer.setMaxVisibleItems(8)
        # `activated` is overloaded; bind the QModelIndex variant so the slot
        # receives a row index instead of the plain text (str).
        self._customer_completer.activated[QModelIndex].connect(
            self._on_customer_activated
        )

    def _refresh_customer_index(self) -> None:
        """Reload the in-memory customer index (keeps ClientesView changes visible)."""
        with SessionManager() as session:
            customers = session.exec(select(Customer).order_by(Customer.name)).all()
        self._customer_index = list(customers)
        self._customer_by_id = {c.id: c for c in customers if c.id is not None}

    # ── Sale tab management ───────────────────

    def _new_sale_tab(self) -> _SaleTab:
        tab = _SaleTab()
        idx = self._tabs.addTab(tab, f"Venta {self._tabs.count() + 1}")
        self._cart_tabs[idx] = tab

        tab.customer_edit.textChanged.connect(
            lambda text, t=tab: self._on_customer_search_text(t, text)
        )
        tab.customer_edit.returnPressed.connect(
            lambda t=tab: self._on_customer_return_pressed(t)
        )
        tab.btn_quit_customer.clicked.connect(lambda: self._remove_customer(tab))
        tab.btn_pick_rx.clicked.connect(lambda: self._pick_prescription(tab))
        tab.btn_rx_history.clicked.connect(lambda: self._show_rx_history(tab))
        tab.btn_checkout.clicked.connect(self._checkout)
        tab.btn_clear.clicked.connect(lambda: self._clear_tab(tab))
        tab.btn_clear.clicked.connect(lambda: self._tabs.setCurrentWidget(tab))

        self._tabs.setCurrentWidget(tab)
        self._render_cart(tab)
        return tab

    def _close_sale_tab(self, idx: int) -> None:
        tab = self._cart_tabs.get(idx)
        if tab is None:
            return
        if len(self._cart_tabs) <= 1:
            return
        if not tab.session.cart_empty():
            msg = (
                "Esta venta contiene productos sin vender.\n"
                "¿Desea cerrar la pestaña de todas formas? "
                "Los productos se perderán."
            )
            if not dialogo_confirmacion(self, "Venta no vacía", msg):
                return
        self._tabs.removeTab(idx)
        # QTabWidget shifts tabs after idx: rebuild the dict keyed by visual
        # index so the remaining tabs stay tracked (bugfix: desync).
        # _tabs only ever contains _SaleTab instances (added in _new_sale_tab),
        # so the cast is safe.
        self._cart_tabs = {
            i: cast(_SaleTab, self._tabs.widget(i))
            for i in range(self._tabs.count())
            if self._tabs.widget(i) is not None
        }
        # Renumber titles so they always follow visual order (bugfix: closing
        # the middle tab used to leave "Venta 3" on what is now the 2nd tab).
        self._renumber_tabs()

    def _renumber_tabs(self) -> None:
        """Keep tab titles sequential (1..N) according to visual position."""
        for i in range(self._tabs.count()):
            self._tabs.setTabText(i, f"Venta {i + 1}")

    def _active_tab(self) -> _SaleTab | None:
        w = self._tabs.currentWidget()
        if isinstance(w, _SaleTab):
            return w
        return None

    def _active_session_obj(self) -> _CartSession | None:
        tab = self._active_tab()
        return tab.session if tab else None

    # ── Customer search (inline) ──────────────

    def _on_customer_search_text(self, tab: _SaleTab, text: str) -> None:
        """Debounce customer search. Typing never mutates the selected customer."""
        self._pending_search_tab = tab
        self._pending_search_text = text
        self._customer_timer.start()

    def _cancel_customer_search(self) -> None:
        """Stop any pending search and close the completer popup.

        Prevents the debounce timer from re-opening the popup while a modal
        dialog runs or right after a customer is applied/removed.
        """
        self._customer_timer.stop()
        self._pending_search_tab = None
        self._pending_search_text = ""
        if self._customer_completer is not None:
            self._customer_completer.setCompletionPrefix("")
            self._customer_completer.popup().hide()

    def _flush_customer_search(self) -> None:
        tab = self._pending_search_tab
        if tab is None:
            return
        self._pending_search_tab = None
        self._update_customer_suggestions(tab, self._pending_search_text)

    def _update_customer_suggestions(self, tab: _SaleTab, text: str) -> None:
        """Fill the completer popup with live matches, or a create-new row."""
        if self._customer_completer is None or self._customer_model is None:
            return
        text = text.strip()
        self._customer_model.clear()
        if text:
            matches = _filtrar_clientes(self._customer_index, text)
            for c in matches:
                item = QStandardItem(_etiqueta_busqueda_cliente(c))
                item.setData(c.id, Qt.ItemDataRole.UserRole)
                self._customer_model.appendRow(item)
            if not matches:
                item = QStandardItem(f"➕  Crear «{text}»…")
                item.setData(_CREATE_SENTINEL, Qt.ItemDataRole.UserRole)
                self._customer_model.appendRow(item)
        self._customer_completer.setWidget(tab.customer_edit)
        self._completer_tab = tab
        self._customer_completer.setCompletionPrefix(text)
        if text and self._customer_model.rowCount():
            self._customer_completer.complete()
            # Preselect the first suggestion so Enter activates it: either an
            # existing customer or the "Crear" row when there are no matches.
            self._customer_completer.popup().setCurrentIndex(
                self._customer_model.index(0, 0)
            )
        else:
            self._customer_completer.popup().hide()

    def _on_customer_activated(self, index: QModelIndex) -> None:
        tab = self._completer_tab
        if tab is None:
            return
        self._cancel_customer_search()
        cid = index.data(Qt.ItemDataRole.UserRole)
        if cid == _CREATE_SENTINEL:
            self._crear_cliente_desde_busqueda(tab, tab.customer_edit.text())
            return
        customer = self._customer_by_id.get(cid)
        if customer:
            self._apply_customer(tab, customer)

    def _on_customer_return_pressed(self, tab: _SaleTab) -> None:
        """Enter resolves a customer: activate the highlighted popup row if there
        is one, otherwise apply a unique match or open the creation form."""
        if self._customer_completer is not None:
            popup = self._customer_completer.popup()
            if popup.isVisible():
                idx = popup.currentIndex()
                if idx.isValid() and idx.row() >= 0:
                    self._on_customer_activated(idx)
                    return
        text = tab.customer_edit.text().strip()
        if not text:
            return
        matches = _filtrar_clientes(self._customer_index, text, limite=50)
        if len(matches) == 1:
            self._apply_customer(tab, matches[0])
        elif not matches:
            self._crear_cliente_desde_busqueda(tab, text)
        else:
            self._update_customer_suggestions(tab, text)

    def _apply_customer(self, tab: _SaleTab, customer: Customer) -> None:
        """Select a customer for `tab`. Only explicit choices land here."""
        tab.session.customer = customer
        tab.session.prescription = None
        tab.customer_edit.clear()
        tab.customer_edit.setPlaceholderText(_PLACEHOLDER_CAMBIAR)
        tab.set_customer_display()
        self._cancel_customer_search()

    def _remove_customer(self, tab: _SaleTab) -> None:
        """Deselect the customer and reset the search field."""
        tab.session.customer = None
        tab.session.prescription = None
        tab.customer_edit.clear()
        tab.customer_edit.setPlaceholderText(_PLACEHOLDER_BUSCAR)
        tab.set_customer_display()
        self._cancel_customer_search()

    def _crear_cliente_desde_busqueda(self, tab: _SaleTab, texto: str) -> None:
        """Create a customer from search text, pre-filling the dialog."""
        self._cancel_customer_search()
        prefill: dict[str, str] = {}
        doc = _parse_documento_busqueda(texto)
        if doc:
            prefill["id_document"] = doc
        else:
            prefill["name"] = texto.strip()[:150]
        customer = _create_customer_from_dialog(self, prefill)
        if customer is not None:
            self._refresh_customer_index()
            self._apply_customer(tab, customer)

    def _create_customer_from_tab(self) -> None:
        tab = self._active_tab()
        if tab is None:
            return
        self._cancel_customer_search()
        customer = _create_customer_from_dialog(self)
        if customer is not None:
            self._refresh_customer_index()
            self._apply_customer(tab, customer)

    # ── Prescription ──────────────────────────

    def _pick_prescription(self, tab: _SaleTab) -> None:
        if not tab.session.customer:
            QMessageBox.information(
                self, "Cliente requerido", "Seleccione un cliente primero"
            )
            return
        dlg = _PrescriptionHistoryDialog(tab.session.customer, self)
        dlg.set_pick_mode()
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        if dlg.selected_prescription:
            tab.session.prescription = dlg.selected_prescription
        tab.set_customer_display()

    def _show_rx_history(self, tab: _SaleTab) -> None:
        if not tab.session.customer:
            return
        dlg = _PrescriptionHistoryDialog(tab.session.customer, self)
        dlg.exec()

    # ── Session management ────────────────────

    def _ensure_session(self) -> None:
        """Check for an active cash session and show open dialog if needed."""
        user = UserSession().current_user
        if not user:
            return
        assert user.id is not None

        cs = cash_session_service.get_active_session(user.id)
        if cs:
            self._set_session(cs)
        else:
            self._open_session_dialog()
            # If the dialog was cancelled/failed, enforce the closed state so
            # the +tab button and checkouts are not left enabled (bugfix).
            if not self._active_session:
                self._clear_session_ui()

    def _set_session(self, cs: CashSession) -> None:
        """Update UI to reflect the active session."""
        self._active_session = cs
        self._session_bar.setProperty("state", "open")
        self._session_bar.style().unpolish(self._session_bar)
        self._session_bar.style().polish(self._session_bar)
        self._btn_open_session.setVisible(False)
        self._btn_close_session.setVisible(True)
        self._btn_new_sale.setEnabled(True)
        for tab in self._cart_tabs.values():
            tab.btn_checkout.setEnabled(True)
        self._update_elapsed_time()
        self._elapsed_timer.start()

    def _clear_session_ui(self) -> None:
        """Reset UI to no-session state."""
        self._active_session = None
        self._elapsed_timer.stop()
        self._session_label.setText("🔴  Sesión: <b>Cerrada</b>")
        self._session_bar.setProperty("state", "closed")
        self._session_bar.style().unpolish(self._session_bar)
        self._session_bar.style().polish(self._session_bar)
        self._btn_open_session.setVisible(True)
        self._btn_close_session.setVisible(False)
        self._btn_new_sale.setEnabled(False)
        for tab in self._cart_tabs.values():
            tab.btn_checkout.setEnabled(False)

    def _update_elapsed_time(self) -> None:
        """Refresh the session elapsed time display."""
        cs = self._active_session
        if not cs:
            return
        elapsed = datetime.now() - cs.opened_at
        hours = int(elapsed.total_seconds() // 3600)
        minutes = int((elapsed.total_seconds() % 3600) // 60)
        self._session_label.setText(
            f"🟢  Sesión: <b>Abierta</b> ({hours}h {minutes:02d}m)  ·  "
            f"Saldo inicial: {format_bs(cs.initial_balance)}"
        )

    def _open_session_dialog(self) -> None:
        dlg = _CashOpenDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        user = UserSession().current_user
        if not user:
            return
        assert user.id is not None
        try:
            cs = cash_session_service.open_session(user.id, dlg.initial_balance)
            self._set_session(cs)
            self._load_products()
        except Exception as e:
            dialogo_error(self, "Error", "No se pudo abrir la caja", str(e))

    def _close_session_dialog(self) -> None:
        if not self._active_session:
            return

        # Warn if any tab has items
        if any(not t.session.cart_empty() for t in self._cart_tabs.values()):
            msg = (
                "Hay ventas con productos sin procesar.\n"
                "¿Desea cerrar la caja de todas formas?\n\n"
                "Los productos en los carritos se perderán."
            )
            if not dialogo_confirmacion(self, "Carritos no vacíos", msg):
                return

        try:
            summary = cash_session_service.get_session_summary(self._active_session)
        except Exception as e:
            dialogo_error(self, "Error", "No se pudo obtener el resumen", str(e))
            return

        dlg = _CashCloseDialog(self._active_session, summary, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            cash_session_service.close_session(
                self._active_session.id,
                dlg.final_balance,  # type: ignore[union-attr]
            )
            _sign = "+" if dlg.difference > 0 else ""
            diff_text = f"Bs. {_sign}{format_ve(dlg.difference)}"
            QMessageBox.information(
                self,
                "Caja cerrada",
                f"Sesión cerrada exitosamente.\n\n"
                f"Saldo final: {format_bs(dlg.final_balance)}\n"
                f"Diferencia: {diff_text}",
            )
            for tab in self._cart_tabs.values():
                self._clear_tab(tab)
            self._clear_session_ui()
        except Exception as e:
            dialogo_error(self, "Error", "No se pudo cerrar la caja", str(e))

    # ── Product loading ───────────────────────

    def _load_products(self, search_text: str = "") -> None:
        self._product_table.clear()
        with SessionManager() as session:
            stmt = select(Product).where(Product.active == True)  # noqa: E712
            if search_text := search_text.strip():
                like = f"%{search_text}%"
                stmt = stmt.where(Product.name.ilike(like))
            stmt = stmt.order_by(Product.name)
            products = session.exec(stmt).all()

        # One rate lookup for the whole table: calling convert_to_bs() per
        # product issued one BCV request per row.
        rate = get_usd_rate()
        for p in products:
            bs_price = convert_to_bs(p.sale_price_usd, rate)
            bs_str = format_bs(bs_price) if bs_price else "—"
            self._product_table.add_row(
                [
                    str(p.id),
                    p.name,
                    format_usd(p.sale_price_usd),
                    bs_str,
                    str(p.stock_quantity),
                ]
            )

    # ── Cart operations ───────────────────────

    def _add_selected_to_cart(self) -> None:
        tab = self._active_tab()
        if tab is None:
            return
        session = tab.session

        row = self._product_table.view().currentIndex().row()
        if row < 0:
            QMessageBox.information(
                self, "Agregar", "Seleccione un producto de la lista"
            )
            return
        proxy = self._product_table.proxy()
        source_idx = proxy.mapToSource(proxy.index(row, 0))
        model = self._product_table.model()
        item = model.item(source_idx.row(), 0)
        product_id = int(item.text()) if item else 0

        with SessionManager() as session_db:
            product = session_db.get(Product, product_id)
            if not product or not product.active:
                return
            if product.stock_quantity <= 0:
                QMessageBox.warning(
                    self,
                    "Sin stock",
                    f"'{product.name}' no tiene stock disponible",
                )
                return

            # Check if already in cart (this tab's cart)
            for ci in session.cart:
                if ci.product_id == product.id:
                    if ci.quantity >= product.stock_quantity:
                        QMessageBox.warning(
                            self,
                            "Stock insuficiente",
                            f"Stock disponible de '{product.name}': {product.stock_quantity}",
                        )
                        return
                    ci.quantity += 1
                    self._render_cart(tab)
                    return

            assert product.id is not None
            bs_price = convert_to_bs(product.sale_price_usd)
            if bs_price is None:
                QMessageBox.warning(
                    self,
                    "Tasa no disponible",
                    "No se pudo obtener la tasa BCV para convertir el precio. "
                    "Actualice la tasa en el widget de tasa cambiaria.",
                )
                return
            session.cart.append(
                _CartItem(
                    product_id=product.id,
                    name=product.name,
                    unit_price=bs_price,
                    unit_price_usd=product.sale_price_usd,
                )
            )
            self._render_cart(tab)

    def _render_cart(self, tab: _SaleTab) -> None:
        session = tab.session
        table = tab.cart_table
        table.setRowCount(len(session.cart))
        for i, ci in enumerate(session.cart):
            # Product name
            table.setItem(i, 0, QTableWidgetItem(ci.name))
            table.item(i, 0).setFlags(
                table.item(i, 0).flags() & ~Qt.ItemFlag.ItemIsEditable
            )

            # Quantity controls: [ ✕ ] [ − ] N [ + ]
            qty_widget = QWidget()
            qty_layout = QHBoxLayout(qty_widget)
            qty_layout.setContentsMargins(4, 2, 4, 2)
            qty_layout.setSpacing(4)

            btn_del = QPushButton("✕")
            btn_del.setFixedSize(24, 24)
            btn_del.setObjectName("btn-delete-item")
            btn_del.clicked.connect(
                lambda checked, row=i, t=tab: self._cart_remove(t, row)
            )
            qty_layout.addWidget(btn_del)

            btn_minus = QPushButton("−")
            btn_minus.setFixedSize(24, 24)
            btn_minus.clicked.connect(
                lambda checked, row=i, t=tab: self._cart_decrement(t, row)
            )
            qty_layout.addWidget(btn_minus)

            qty_label = QLabel(format_ve_int(ci.quantity))
            qty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            qty_label.setObjectName("qty-label")
            qty_layout.addWidget(qty_label)

            btn_plus = QPushButton("+")
            btn_plus.setFixedSize(24, 24)
            btn_plus.clicked.connect(
                lambda checked, row=i, t=tab: self._cart_increment(t, row)
            )
            qty_layout.addWidget(btn_plus)

            qty_layout.addStretch()
            table.setCellWidget(i, 1, qty_widget)

            # Unit price in USD
            price_usd_item = QTableWidgetItem(format_usd(ci.unit_price_usd))
            price_usd_item.setFlags(
                price_usd_item.flags() & ~Qt.ItemFlag.ItemIsEditable
            )
            price_usd_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            table.setItem(i, 2, price_usd_item)

            # Unit price in Bs
            price_bs_item = QTableWidgetItem(format_bs(ci.unit_price))
            price_bs_item.setFlags(price_bs_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            price_bs_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            table.setItem(i, 3, price_bs_item)

            # Subtotal
            sub_item = QTableWidgetItem(format_bs(ci.subtotal))
            sub_item.setFlags(sub_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            sub_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            table.setItem(i, 4, sub_item)
            table.setRowHeight(i, 40)

        self._recalculate_totals(tab)

    def _cart_increment(self, tab: _SaleTab, row: int) -> None:
        session = tab.session
        if row < 0 or row >= len(session.cart):
            return
        ci = session.cart[row]
        with SessionManager() as session_db:
            product = session_db.get(Product, ci.product_id)
            if product and ci.quantity >= product.stock_quantity:
                QMessageBox.warning(
                    self,
                    "Stock insuficiente",
                    f"Stock disponible de '{ci.name}': {product.stock_quantity}",
                )
                return
        ci.quantity += 1
        self._render_cart(tab)

    def _cart_decrement(self, tab: _SaleTab, row: int) -> None:
        session = tab.session
        if row < 0 or row >= len(session.cart):
            return
        ci = session.cart[row]
        if ci.quantity <= 1:
            self._cart_remove(tab, row)
            return
        ci.quantity -= 1
        self._render_cart(tab)

    def _cart_remove(self, tab: _SaleTab, row: int) -> None:
        session = tab.session
        if 0 <= row < len(session.cart):
            session.cart.pop(row)
            self._render_cart(tab)

    def _clear_tab(self, tab: _SaleTab) -> None:
        tab.session.cart.clear()
        tab.session.customer = None
        tab.session.prescription = None
        tab.customer_edit.clear()
        tab.customer_edit.setPlaceholderText(_PLACEHOLDER_BUSCAR)
        tab.set_customer_display()
        tab.cart_table.setRowCount(0)
        self._recalculate_totals(tab)

    # ── Totals ────────────────────────────────

    def _recalculate_totals(self, tab: _SaleTab) -> None:
        s = tab.session
        subtotal = s.subtotal()
        iva = s.iva()
        total = s.total()
        tab.subtotal_label.setText(format_bs(subtotal))
        tab.iva_label.setText(format_bs(iva))
        tab.total_label.setText(format_bs(total))

        total_usd = convert_to_usd(total)
        if total_usd:
            tab.total_usd_label.setText(format_usd(total_usd))
            tab.total_usd_label.setVisible(True)
        else:
            tab.total_usd_label.setVisible(False)

    # ── Checkout ──────────────────────────────

    def _demanda_total_excede_stock(self) -> list[tuple[str, int, int]]:
        """Return (name, requested, stock) for products whose aggregate demand
        across ALL open sale tabs exceeds available stock.

        Validates before the payment dialog so the sale is blocked with a clear
        message instead of failing inside registrar_venta after confirmation.
        """
        demand: dict[int, int] = {}
        for tab in self._cart_tabs.values():
            for ci in tab.session.cart:
                demand[ci.product_id] = demand.get(ci.product_id, 0) + ci.quantity
        if not demand:
            return []
        excedidos: list[tuple[str, int, int]] = []
        with SessionManager() as session_db:
            for pid, qty in demand.items():
                prod = session_db.get(Product, pid)
                if prod and qty > prod.stock_quantity:
                    excedidos.append((prod.name, qty, prod.stock_quantity))
        return excedidos

    def _checkout(self) -> None:
        tab = self._active_tab()
        if tab is None:
            return
        session = tab.session

        if not self._active_session:
            QMessageBox.information(
                self,
                "Sesión requerida",
                "Debe abrir una sesión de caja antes de procesar ventas",
            )
            return
        if session.cart_empty():
            QMessageBox.information(
                self,
                "Carrito vacío",
                "Agregue productos al carrito antes de procesar la venta",
            )
            return
        if not session.customer:
            QMessageBox.information(
                self,
                "Cliente requerido",
                "Busque, seleccione o cree un cliente antes de procesar la venta",
            )
            return

        excedidos = self._demanda_total_excede_stock()
        if excedidos:
            detalle = "\n".join(
                f"  • {nombre}: demanda {demanda} / stock {stock}"
                for nombre, demanda, stock in excedidos
            )
            QMessageBox.warning(
                self,
                "Stock insuficiente",
                "La demanda total entre pestañas de venta excede el stock "
                f"disponible:\n\n{detalle}",
            )
            return

        subtotal = session.subtotal()
        iva = session.iva()
        total = session.total()

        # ── Payment method dialog ──
        checkout_total_usd = convert_to_usd(total)
        pay_dlg = _PaymentDialog(total, checkout_total_usd, self)
        if pay_dlg.exec() != QDialog.DialogCode.Accepted:
            return

        # Build confirmation message
        total_usd_line = (
            f"<br><b>TOTAL USD:</b> {format_usd(checkout_total_usd)}"
            if checkout_total_usd
            else ""
        )

        items_summary = "\n".join(
            f"  {ci.name}  x{format_ve_int(ci.quantity)}  @ {format_bs(ci.unit_price)}"
            for ci in session.cart
        )

        pay_line = f"<b>Método de pago:</b> {pay_dlg.payment_method}"
        if pay_dlg.payment_method in (EFECTIVO_BS, EFECTIVO_USD) and (
            pay_dlg.amount_received is not None
        ):
            _fmt = format_usd if pay_dlg.payment_method == EFECTIVO_USD else format_bs
            pay_line += (
                f"<br><b>Recibido:</b> {_fmt(pay_dlg.amount_received)}"
                f"<br><b>Cambio:</b> {_fmt(pay_dlg.change_amount)}"
            )
        elif pay_dlg.payment_method == MIXTO:
            breakdown = "<br>".join(
                f"  - {p['method']} ({p['currency']}): {format_ve(p['amount'])}"
                for p in pay_dlg.payments
            )
            pay_line += f"<br><b>Desglose:</b><br>{breakdown}"

        customer = session.customer
        msg = (
            f"<b>Cliente:</b> {customer.name} ({customer.id_document})<br><br>"  # type: ignore[union-attr]
            f"<b>Productos:</b><br>{items_summary}<br><br>"
            f"<b>Subtotal:</b> {format_bs(subtotal)}<br>"
            f"<b>IVA ({get_iva_rate_pct()}%):</b> {format_bs(iva)}<br>"
            f"<b>TOTAL:</b> {format_bs(total)}{total_usd_line}<br><br>"
            f"{pay_line}"
        )

        if not dialogo_confirmacion(self, "Confirmar Venta", msg, rich_text=True):
            return

        # Process the sale
        user = UserSession().current_user
        if not user:
            dialogo_error(self, "Error", "No hay sesión activa", "")
            return

        items_data = [
            {
                "product_id": ci.product_id,
                "quantity": ci.quantity,
                "unit_price": ci.unit_price,
            }
            for ci in session.cart
        ]

        try:
            sale = registrar_venta(
                customer_id=customer.id,  # type: ignore[union-attr]
                user_id=user.id,
                items=items_data,
                discount=Decimal("0"),
                status_id=2 if pay_dlg.payment_method == ABONO else 1,
                prescription_id=(
                    session.prescription.id if session.prescription else None
                ),
                payment_method=pay_dlg.payment_method,
                amount_received=pay_dlg.amount_received,
                change_amount=pay_dlg.change_amount,
                taxes=iva,
                payments=pay_dlg.payments,
            )

            # Show the invoice preview with print and save actions
            assert sale.id is not None
            show_sale_receipt(self, sale.id, lineas=self._resumen_venta(sale))

            log.info(
                "venta_pos: factura=%s total=%.2f metodo=%s items=%d",
                sale.invoice_number,
                sale.total,
                sale.payment_method,
                len(items_data),
            )
            self._clear_tab(tab)
            self._load_products()  # refresh stock shown in the catalog (bugfix)
        except Exception as e:
            log.error("Error al procesar venta: %s", e)
            dialogo_error(self, "Error", "No se pudo procesar la venta", str(e))

    # ── Print receipt ─────────────────────────

    def _resumen_venta(self, sale: Sale) -> list[str]:
        """Summary lines shown above the invoice preview."""
        lineas = [f"Factura: {sale.invoice_number}", f"Total: {format_bs(sale.total)}"]
        sale_usd = convert_to_usd(sale.total)
        if sale_usd:
            lineas.append(f"Total USD: {format_usd(sale_usd)}")
        lineas.append(f"Método de pago: {sale.payment_method}")
        if sale.change_amount and sale.change_amount > 0:
            _fmt = format_usd if sale.payment_method == EFECTIVO_USD else format_bs
            lineas.append(f"Cambio: {_fmt(sale.change_amount)}")
        if sale.payment_method == ABONO:
            pagado = sale.amount_received or Decimal("0")
            lineas.append(f"Pagado: {format_bs(pagado)}")
            lineas.append(f"Saldo pendiente: {format_bs(sale.total - pagado)}")
        return lineas

    def _print_receipt(self, sale_id: int) -> None:
        """Open the receipt dialog for an existing sale (print or save PDF)."""
        show_sale_receipt(self, sale_id)
