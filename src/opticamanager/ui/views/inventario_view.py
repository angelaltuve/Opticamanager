from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from shutil import copy2
from uuid import uuid4

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor, QPixmap, QStandardItemModel
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from opticamanager.services.category_service import create_category

from sqlmodel import desc, select

from opticamanager.db import SessionManager
from opticamanager.models import Category, InventoryLog, Product, User
from opticamanager.ui.widgets.dialogs import dialogo_confirmacion, dialogo_error
from opticamanager.ui.widgets.table_widget import TablaPersonalizada
from opticamanager.ui.widgets.validators import (
    validador_codigo_barras,
    validador_entero,
    validador_moneda,
)

IMAGES_DIR = (
    Path(__file__).resolve().parent.parent.parent.parent.parent / "data" / "images"
)


def _copiar_imagen(origen: str) -> str:
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    ext = Path(origen).suffix or ".jpg"
    destino = IMAGES_DIR / f"{uuid4().hex}{ext}"
    copy2(origen, destino)
    return str(destino.relative_to(destino.parent.parent))


class _ProductoDialog(QDialog):
    def __init__(
        self, parent: QWidget | None = None, producto: Product | None = None
    ) -> None:
        super().__init__(parent)
        self._producto = producto
        self._imagen_origen: str | None = None
        self.setWindowTitle("Editar Producto" if producto else "Nuevo Producto")
        self.setMinimumWidth(480)
        self._setup_ui()
        self._load_categories()
        if producto:
            self._fill_form(producto)

    def _setup_ui(self) -> None:
        form = QFormLayout()

        self._nombre = QLineEdit()
        self._nombre.setMaxLength(150)
        form.addRow("Nombre:", self._nombre)

        self._barcode = QLineEdit()
        self._barcode.setMaxLength(50)
        self._barcode.setValidator(validador_codigo_barras())
        form.addRow("Código barras:", self._barcode)

        cat_row = QHBoxLayout()
        self._categoria = QComboBox()
        self._categoria.setMinimumWidth(200)
        self._btn_add_cat = QPushButton("+")
        self._btn_add_cat.setFixedWidth(30)
        self._btn_add_cat.setToolTip("Crear nueva categoría")
        self._btn_add_cat.clicked.connect(self._crear_categoria_inline)
        cat_row.addWidget(self._categoria)
        cat_row.addWidget(self._btn_add_cat)
        form.addRow("Categoría:", cat_row)

        self._cost_price = QLineEdit()
        self._cost_price.setValidator(validador_moneda())
        form.addRow("Precio compra (USD):", self._cost_price)

        self._sale_price = QLineEdit()
        self._sale_price.setValidator(validador_moneda())
        form.addRow("Precio venta (USD):", self._sale_price)

        self._stock = QLineEdit()
        self._stock.setValidator(validador_entero())
        form.addRow("Stock actual:", self._stock)

        self._min_stock = QLineEdit()
        self._min_stock.setValidator(validador_entero())
        form.addRow("Stock mínimo:", self._min_stock)

        self._description = QTextEdit()
        self._description.setMaximumHeight(80)
        form.addRow("Descripción:", self._description)

        image_row = QHBoxLayout()
        self._btn_imagen = QPushButton("Seleccionar imagen...")
        self._btn_imagen.clicked.connect(self._seleccionar_imagen)
        self._btn_limpiar = QPushButton("Quitar")
        self._btn_limpiar.clicked.connect(self._limpiar_imagen)
        self._btn_limpiar.setVisible(False)
        self._imagen_label = QLabel()
        self._imagen_label.setFixedSize(80, 80)
        self._imagen_label.setObjectName("image-placeholder")
        self._imagen_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._imagen_label.setScaledContents(True)
        image_row.addWidget(self._btn_imagen)
        image_row.addWidget(self._btn_limpiar)
        image_row.addStretch()
        image_row.addWidget(self._imagen_label)
        form.addRow("Imagen:", image_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(buttons)
        self.setLayout(layout)

    def _load_categories(self) -> None:
        with SessionManager() as session:
            cats = session.exec(select(Category).order_by(Category.name)).all()
        self._categoria.clear()
        for c in cats:
            self._categoria.addItem(c.name, c.id)

    def _crear_categoria_inline(self) -> None:
        from opticamanager.ui.views.categorias_view import _CategoryDialog

        dlg = _CategoryDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        data = dlg.get_data()
        try:
            cat = create_category(**data)
            self._categoria.addItem(cat.name, cat.id)
            self._categoria.setCurrentIndex(self._categoria.count() - 1)
        except Exception as e:
            dialogo_error(self, "Error", "No se pudo crear la categoría", str(e))

    def _seleccionar_imagen(self) -> None:
        ruta, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar imagen del producto",
            "",
            "Imágenes (*.png *.jpg *.jpeg *.webp *.bmp)",
        )
        if not ruta:
            return
        self._imagen_origen = ruta
        pixmap = QPixmap(ruta)
        if not pixmap.isNull():
            self._imagen_label.setPixmap(pixmap)
        self._btn_limpiar.setVisible(True)

    def _limpiar_imagen(self) -> None:
        self._imagen_origen = None
        self._imagen_label.clear()
        self._imagen_label.setText("")
        self._btn_limpiar.setVisible(False)

    def _fill_form(self, p: Product) -> None:
        self._nombre.setText(p.name)
        if p.barcode:
            self._barcode.setText(p.barcode)
        for i in range(self._categoria.count()):
            if self._categoria.itemData(i) == p.category_id:
                self._categoria.setCurrentIndex(i)
                break
        self._cost_price.setText(str(p.cost_price_usd))
        self._sale_price.setText(str(p.sale_price_usd))
        self._stock.setText(str(p.stock_quantity))
        self._min_stock.setText(str(p.min_stock))
        if p.description:
            self._description.setPlainText(p.description)
        if p.image_path:
            ruta = IMAGES_DIR.parent / p.image_path
            if ruta.exists():
                self._imagen_label.setPixmap(QPixmap(str(ruta)))
                self._btn_limpiar.setVisible(True)

    def _validate_and_accept(self) -> None:
        if not self._nombre.text().strip():
            QMessageBox.warning(self, "Validación", "El nombre es obligatorio")
            return
        if not self._cost_price.text().strip():
            QMessageBox.warning(
                self, "Validación", "El precio de compra es obligatorio"
            )
            return
        if not self._sale_price.text().strip():
            QMessageBox.warning(self, "Validación", "El precio de venta es obligatorio")
            return
        self.accept()

    def get_data(self) -> dict:
        data: dict = {
            "name": self._nombre.text().strip(),
            "barcode": self._barcode.text().strip() or None,
            "category_id": self._categoria.currentData(),
            "cost_price_usd": Decimal(self._cost_price.text()),
            "sale_price_usd": Decimal(self._sale_price.text()),
            "stock_quantity": int(self._stock.text() or "0"),
            "min_stock": int(self._min_stock.text() or "0"),
            "description": self._description.toPlainText().strip() or None,
        }
        if self._imagen_origen:
            data["image_path"] = _copiar_imagen(self._imagen_origen)
        return data


GREEN = QColor("#27ae60")
RED = QColor("#e74c3c")
ALERTA_BG = QColor("#fcf3cf")  # warning yellow


class _MovimientosDialog(QDialog):
    def __init__(
        self, parent: QWidget | None = None, product_id: int | None = None
    ) -> None:
        super().__init__(parent)
        self._prefiltro_id = product_id
        self.setWindowTitle("Historial de Movimientos")
        self.setMinimumSize(800, 500)
        self._setup_ui()
        self._load_productos()
        self._load_data()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout()

        filtro_row = QHBoxLayout()
        filtro_row.addWidget(QLabel("Producto:"))
        self._filtro = QComboBox()
        self._filtro.setMinimumWidth(250)
        self._filtro.currentIndexChanged.connect(self._load_data)
        filtro_row.addWidget(self._filtro)
        filtro_row.addStretch()
        layout.addLayout(filtro_row)

        self._tabla = TablaPersonalizada()
        self._tabla.set_columns(
            ["ID", "Fecha", "Producto", "Cantidad", "Costo Unit.", "Razón", "Usuario"]
        )
        self._tabla.view().setColumnHidden(0, True)
        self._tabla.view().setColumnWidth(1, 160)
        layout.addWidget(self._tabla)

        btn_cerrar = QPushButton("Cerrar")
        btn_cerrar.clicked.connect(self.accept)
        layout.addWidget(btn_cerrar, alignment=Qt.AlignmentFlag.AlignRight)

        self.setLayout(layout)

    def _load_productos(self) -> None:
        self._filtro.addItem("Todos los productos", None)
        with SessionManager() as session:
            productos = session.exec(select(Product).order_by(Product.name)).all()
        for p in productos:
            self._filtro.addItem(f"[{p.id}] {p.name}", p.id)
        if self._prefiltro_id is not None:
            for i in range(self._filtro.count()):
                if self._filtro.itemData(i) == self._prefiltro_id:
                    self._filtro.setCurrentIndex(i)
                    break

    def _load_data(self) -> None:
        self._tabla.clear()
        pid = self._filtro.currentData()
        stmt = select(InventoryLog).order_by(desc(InventoryLog.created_at))
        if pid is not None:
            stmt = stmt.where(InventoryLog.product_id == pid)
        with SessionManager() as session:
            logs = session.exec(stmt).all()
            for log in logs:
                producto = session.get(Product, log.product_id)
                usuario = session.get(User, log.user_id)
                qty = log.quantity
                try:
                    es_positivo = qty > 0
                except TypeError:
                    # non-numeric quantity (corrupt row): treat as not positive
                    es_positivo = False
                qty_str = f"+{qty}" if es_positivo else str(qty)
                color = GREEN if es_positivo else RED
                items = [
                    str(log.id),
                    log.created_at.strftime("%d/%m/%Y %H:%M"),
                    producto.name if producto else "—",
                    qty_str,
                    f"Bs. {log.unit_cost:,.2f}" if log.unit_cost else "—",
                    log.reason,
                    usuario.name if usuario else "—",
                ]
                row_idx = self._tabla.add_row(items)
                item = self._tabla.model().item(row_idx, 3)
                if item:
                    item.setForeground(color)


class InventarioView(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._setup_ui()
        self._load_data()

    def _setup_ui(self) -> None:
        title = QLabel("Inventario de Productos")
        title.setObjectName("title-h2")

        btn_nuevo = QPushButton("+ Nuevo Producto")
        btn_nuevo.setProperty("success", True)
        btn_nuevo.clicked.connect(self._nuevo_producto)

        self._btn_editar = QPushButton("Editar")
        self._btn_editar.clicked.connect(self._editar_producto)

        self._btn_eliminar = QPushButton("Eliminar")
        self._btn_eliminar.setProperty("danger", True)
        self._btn_eliminar.clicked.connect(self._eliminar_producto)

        btn_movimientos = QPushButton("📋 Movimientos")
        btn_movimientos.clicked.connect(self._ver_movimientos)

        toolbar = QHBoxLayout()
        toolbar.addWidget(btn_nuevo)
        toolbar.addWidget(self._btn_editar)
        toolbar.addWidget(self._btn_eliminar)
        toolbar.addWidget(btn_movimientos)
        toolbar.addStretch()

        self._alerta_label = QLabel()
        self._alerta_label.setVisible(False)
        self._alerta_label.setObjectName("stock-alert")

        self._tabla = TablaPersonalizada()
        self._tabla.set_columns(
            [
                "ID",
                "Código",
                "Nombre",
                "Categoría",
                "Precio Venta",
                "Stock",
                "Stock Mín.",
                "Estado",
            ]
        )
        self._tabla.view().setColumnHidden(0, True)

        layout = QVBoxLayout()
        layout.setContentsMargins(15, 10, 15, 10)
        layout.addWidget(title)
        layout.addLayout(toolbar)
        layout.addWidget(self._alerta_label)
        layout.addWidget(self._tabla)
        self.setLayout(layout)

    def _load_data(self) -> None:
        self._tabla.clear()
        bajos = 0
        with SessionManager() as session:
            productos = session.exec(select(Product).order_by(Product.name)).all()
        for p in productos:
            with SessionManager() as session:
                cat = session.get(Category, p.category_id) if p.category_id else None
            row_idx = self._tabla.add_row(
                [
                    str(p.id),
                    p.barcode or "",
                    p.name,
                    cat.name if cat else "—",
                    f"$ {p.sale_price_usd:,.2f}",
                    str(p.stock_quantity),
                    str(p.min_stock),
                    "Activo" if p.active else "Inactivo",
                ]
            )
            if p.stock_quantity < p.min_stock:
                bajos += 1
                item = self._tabla.model().item(row_idx, 5)
                if item:
                    item.setBackground(QBrush(ALERTA_BG))
                    item2 = self._tabla.model().item(row_idx, 6)
                    if item2:
                        item2.setBackground(QBrush(ALERTA_BG))
        if bajos > 0:
            self._alerta_label.setText(
                f"⚠️ {bajos} producto(s) con stock por debajo del mínimo"
            )
            self._alerta_label.setVisible(True)
        else:
            self._alerta_label.setVisible(False)

    def _nuevo_producto(self) -> None:
        dlg = _ProductoDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        data = dlg.get_data()
        try:
            with SessionManager() as session:
                p = Product(**data)
                session.add(p)
                session.commit()
            self._load_data()
        except Exception as e:
            dialogo_error(self, "Error", "No se pudo crear el producto", str(e))

    def _editar_producto(self) -> None:
        row = self._tabla.view().currentIndex().row()
        if row < 0:
            QMessageBox.information(
                self, "Seleccionar", "Seleccione un producto de la tabla"
            )
            return
        proxy = self._tabla.proxy()
        source_idx = proxy.mapToSource(proxy.index(row, 0))
        product_id = self._producto_id_modelo(self._tabla.model(), source_idx.row())
        with SessionManager() as session:
            p = session.get(Product, product_id)
            if not p:
                return
            dlg = _ProductoDialog(self, p)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return
            data = dlg.get_data()
            for key, val in data.items():
                setattr(p, key, val)
            session.add(p)
            session.commit()
        self._load_data()

    @staticmethod
    def _producto_id_modelo(model: QStandardItemModel, row: int) -> int:
        item = model.item(row, 0)
        return int(item.text()) if item else 0

    @staticmethod
    def _producto_name_modelo(model: QStandardItemModel, row: int) -> str:
        item = model.item(row, 2)
        return item.text() if item else ""

    def _eliminar_producto(self) -> None:
        row = self._tabla.view().currentIndex().row()
        if row < 0:
            QMessageBox.information(
                self, "Seleccionar", "Seleccione un producto de la tabla"
            )
            return
        proxy = self._tabla.proxy()
        source_idx = proxy.mapToSource(proxy.index(row, 0))
        product_id = self._producto_id_modelo(self._tabla.model(), source_idx.row())
        name = self._producto_name_modelo(self._tabla.model(), source_idx.row())
        if not dialogo_confirmacion(
            self,
            "Eliminar Producto",
            f"¿Eliminar '{name}'?",
        ):
            return
        try:
            with SessionManager() as session:
                p = session.get(Product, product_id)
                if p:
                    session.delete(p)
                    session.commit()
            self._load_data()
        except Exception as e:
            dialogo_error(self, "Error", "No se pudo eliminar el producto", str(e))

    def _ver_movimientos(self) -> None:
        row = self._tabla.view().currentIndex().row()
        pid: int | None = None
        if row >= 0:
            proxy = self._tabla.proxy()
            source_idx = proxy.mapToSource(proxy.index(row, 0))
            pid = self._producto_id_modelo(self._tabla.model(), source_idx.row())
        dlg = _MovimientosDialog(self, pid)
        dlg.exec()
