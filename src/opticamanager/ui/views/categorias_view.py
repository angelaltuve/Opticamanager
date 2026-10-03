from __future__ import annotations

from PyQt6.QtGui import QStandardItemModel
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from opticamanager.core.logging_config import get_logger
from opticamanager.db import SessionManager
from opticamanager.models import Category
from opticamanager.services.category_service import (
    create_category,
    delete_category,
    list_categories,
    update_category,
)
from opticamanager.ui.widgets.dialogs import dialogo_confirmacion, dialogo_error
from opticamanager.ui.widgets.table_widget import TablaPersonalizada

log = get_logger(__name__)


class _CategoryDialog(QDialog):
    def __init__(
        self, parent: QWidget | None = None, category: Category | None = None
    ) -> None:
        super().__init__(parent)
        self._category = category
        self.setWindowTitle("Editar Categoría" if category else "Nueva Categoría")
        self.setMinimumWidth(400)
        self._setup_ui()
        if category:
            self._fill_form(category)

    def _setup_ui(self) -> None:
        form = QFormLayout()

        self._name = QLineEdit()
        self._name.setMaxLength(100)
        form.addRow("Nombre:", self._name)

        self._description = QLineEdit()
        self._description.setMaxLength(255)
        form.addRow("Descripción:", self._description)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(buttons)
        self.setLayout(layout)

    def _fill_form(self, c: Category) -> None:
        self._name.setText(c.name)
        if c.description:
            self._description.setText(c.description)

    def _validate_and_accept(self) -> None:
        if not self._name.text().strip():
            QMessageBox.warning(self, "Validación", "El nombre es obligatorio")
            return
        self.accept()

    def get_data(self) -> dict:
        return {
            "name": self._name.text().strip(),
            "description": self._description.text().strip() or None,
        }


class CategoriasView(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._setup_ui()
        self._load_data()

    @staticmethod
    def _get_selected_id(model: QStandardItemModel, row: int) -> int:
        item = model.item(row, 0)
        return int(item.text()) if item else 0

    @staticmethod
    def _get_selected_name(model: QStandardItemModel, row: int) -> str:
        item = model.item(row, 1)
        return item.text() if item else ""

    def _selected_row(self) -> int | None:
        row = self._tabla.view().currentIndex().row()
        if row < 0:
            QMessageBox.information(
                self, "Seleccionar", "Seleccione una categoría de la tabla"
            )
            return None
        return row

    def _selected_category_id(self) -> int | None:
        row = self._selected_row()
        if row is None:
            return None
        proxy = self._tabla.proxy()
        source_idx = proxy.mapToSource(proxy.index(row, 0))
        return self._get_selected_id(self._tabla.model(), source_idx.row())

    def _setup_ui(self) -> None:
        title = QLabel("Categorías")
        title.setObjectName("title-h2")

        btn_nuevo = QPushButton("+ Nueva Categoría")
        btn_nuevo.setProperty("success", True)
        btn_nuevo.clicked.connect(self._nueva_categoria)

        self._btn_editar = QPushButton("Editar")
        self._btn_editar.clicked.connect(self._editar_categoria)

        self._btn_eliminar = QPushButton("Eliminar")
        self._btn_eliminar.setProperty("danger", True)
        self._btn_eliminar.clicked.connect(self._eliminar_categoria)

        toolbar = QHBoxLayout()
        toolbar.addWidget(btn_nuevo)
        toolbar.addWidget(self._btn_editar)
        toolbar.addWidget(self._btn_eliminar)
        toolbar.addStretch()

        self._tabla = TablaPersonalizada()
        self._tabla.set_columns(["ID", "Nombre", "Descripción"])
        self._tabla.view().setColumnHidden(0, True)

        layout = QVBoxLayout()
        layout.setContentsMargins(15, 10, 15, 10)
        layout.addWidget(title)
        layout.addLayout(toolbar)
        layout.addWidget(self._tabla)
        self.setLayout(layout)

    def _load_data(self) -> None:
        self._tabla.clear()
        cats = list_categories()
        for c in cats:
            self._tabla.add_row(
                [
                    str(c.id),
                    c.name,
                    c.description or "—",
                ]
            )

    def _nueva_categoria(self) -> None:
        dlg = _CategoryDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        data = dlg.get_data()
        try:
            create_category(**data)
            self._load_data()
        except Exception as e:
            dialogo_error(self, "Error", "No se pudo crear la categoría", str(e))

    def _editar_categoria(self) -> None:
        category_id = self._selected_category_id()
        if category_id is None:
            return
        with SessionManager() as session:
            c = session.get(Category, category_id)
            if not c:
                return
            dlg = _CategoryDialog(self, c)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return
            data = dlg.get_data()
            try:
                update_category(category_id, **data)
                self._load_data()
            except Exception as e:
                dialogo_error(self, "Error", "No se pudo editar la categoría", str(e))

    def _eliminar_categoria(self) -> None:
        category_id = self._selected_category_id()
        if category_id is None:
            return
        row = self._tabla.view().currentIndex().row()
        proxy = self._tabla.proxy()
        source_idx = proxy.mapToSource(proxy.index(row, 0))
        name = self._get_selected_name(self._tabla.model(), source_idx.row())

        # Check if category has products
        from opticamanager.models.product import Product
        from sqlmodel import select

        with SessionManager() as session:
            products = session.exec(
                select(Product).where(Product.category_id == category_id)
            ).all()
            if products:
                QMessageBox.warning(
                    self,
                    "No se puede eliminar",
                    f"La categoría '{name}' tiene {len(products)} producto(s) asociado(s).\n"
                    "Reasigne los productos a otra categoría antes de eliminarla.",
                )
                return

        if not dialogo_confirmacion(
            self,
            "Eliminar Categoría",
            f"¿Eliminar '{name}'?",
        ):
            return
        try:
            delete_category(category_id)
            self._load_data()
        except Exception as e:
            dialogo_error(self, "Error", "No se pudo eliminar la categoría", str(e))
