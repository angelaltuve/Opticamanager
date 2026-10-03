from __future__ import annotations

from PyQt6.QtCore import QModelIndex, Qt, QSortFilterProxyModel
from PyQt6.QtGui import QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)


class _TableFilterProxy(QSortFilterProxyModel):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setSortRole(Qt.ItemDataRole.DisplayRole)

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        text = self.filterRegularExpression().pattern()
        if not text:
            return True
        for col in range(self.sourceModel().columnCount()):
            idx = self.sourceModel().index(source_row, col, source_parent)
            value = self.sourceModel().data(idx, Qt.ItemDataRole.DisplayRole)
            if value and text.lower() in value.lower():
                return True
        return False


class TablaPersonalizada(QWidget):
    def __init__(self, page_size: int = 25) -> None:
        super().__init__()
        self._page_size = page_size
        self._current_page = 0
        self._model = QStandardItemModel()
        self._proxy = _TableFilterProxy()
        self._proxy.setSourceModel(self._model)

        self._setup_ui()
        self._update_pagination()

    def _setup_ui(self) -> None:
        search = QLineEdit()
        search.setPlaceholderText("Buscar...")
        search.setClearButtonEnabled(True)
        search.setFixedWidth(300)
        search.textChanged.connect(self._on_search)

        self._page_size_combo = QComboBox()
        self._page_size_combo.addItems(["10", "25", "50", "100"])
        self._page_size_combo.setCurrentText(str(self._page_size))
        self._page_size_combo.currentTextChanged.connect(self._on_page_size_changed)

        top_bar = QHBoxLayout()
        top_bar.addWidget(search)
        top_bar.addStretch()
        top_bar.addWidget(QLabel("Por página:"))
        top_bar.addWidget(self._page_size_combo)

        self._view = QTableView()
        self._view.setModel(self._proxy)
        self._view.setSortingEnabled(True)
        self._view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self._view.setAlternatingRowColors(True)
        self._view.horizontalHeader().setStretchLastSection(True)
        self._view.verticalHeader().hide()

        self._prev_btn = QPushButton("◀ Anterior")
        self._prev_btn.clicked.connect(self._prev_page)
        self._page_label = QLabel("Página 0 de 0")
        self._next_btn = QPushButton("Siguiente ▶")
        self._next_btn.clicked.connect(self._next_page)

        pagination = QHBoxLayout()
        pagination.addStretch()
        pagination.addWidget(self._prev_btn)
        pagination.addWidget(self._page_label)
        pagination.addWidget(self._next_btn)
        pagination.addStretch()

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(top_bar)
        layout.addWidget(self._view)
        layout.addLayout(pagination)
        self.setLayout(layout)

    def set_columns(self, headers: list[str]) -> None:
        self._model.setHorizontalHeaderLabels(headers)

    def add_row(self, values: list[str]) -> int:
        items = [QStandardItem(v) for v in values]
        self._model.appendRow(items)
        self._update_pagination()
        return self._model.rowCount() - 1

    def clear(self) -> None:
        self._model.removeRows(0, self._model.rowCount())
        self._current_page = 0
        self._update_pagination()

    def row_count(self) -> int:
        return self._model.rowCount()

    def _on_search(self, text: str) -> None:
        self._proxy.setFilterRegularExpression(text)
        self._current_page = 0
        self._update_pagination()

    def _on_page_size_changed(self, size: str) -> None:
        self._page_size = int(size)
        self._current_page = 0
        self._update_pagination()

    def _update_pagination(self) -> None:
        total = self._proxy.rowCount()
        pages = max(1, (total + self._page_size - 1) // self._page_size)
        self._page_label.setText(f"Página {self._current_page + 1} de {pages}")
        self._prev_btn.setEnabled(self._current_page > 0)
        self._next_btn.setEnabled(self._current_page < pages - 1)
        self._apply_page()

    def _apply_page(self) -> None:
        start = self._current_page * self._page_size
        for row in range(self._proxy.rowCount()):
            self._view.setRowHidden(row, row < start or row >= start + self._page_size)

    def _prev_page(self) -> None:
        if self._current_page > 0:
            self._current_page -= 1
            self._update_pagination()

    def _next_page(self) -> None:
        total = self._proxy.rowCount()
        pages = max(1, (total + self._page_size - 1) // self._page_size)
        if self._current_page < pages - 1:
            self._current_page += 1
            self._update_pagination()

    def model(self) -> QStandardItemModel:
        return self._model

    def proxy(self) -> QSortFilterProxyModel:
        return self._proxy

    def view(self) -> QTableView:
        return self._view
