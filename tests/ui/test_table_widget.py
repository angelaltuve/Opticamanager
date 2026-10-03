from __future__ import annotations

from PyQt6.QtCore import Qt

from opticamanager.ui.widgets.table_widget import TablaPersonalizada


def test_default_creation(qtbot) -> None:
    """TablaPersonalizada creates with default page_size=25 and no data."""
    table = TablaPersonalizada()
    qtbot.addWidget(table)

    assert table._page_size == 25
    assert table._current_page == 0
    assert table.row_count() == 0
    assert table._page_label.text() == "Página 1 de 1"


def test_custom_page_size(qtbot) -> None:
    """TablaPersonalizada accepts custom page_size."""
    table = TablaPersonalizada(page_size=50)
    qtbot.addWidget(table)

    assert table._page_size == 50
    assert table._page_size_combo.currentText() == "50"


def test_set_columns(qtbot) -> None:
    """set_columns sets horizontal header labels."""
    table = TablaPersonalizada()
    qtbot.addWidget(table)

    headers = ["Nombre", "Precio", "Cantidad"]
    table.set_columns(headers)

    for i, h in enumerate(headers):
        assert table._model.headerData(i, Qt.Orientation.Horizontal) == h


def test_add_row(qtbot) -> None:
    """add_row appends a row and returns its index."""
    table = TablaPersonalizada()
    qtbot.addWidget(table)
    table.set_columns(["A", "B"])

    idx = table.add_row(["x1", "y1"])
    assert idx == 0
    assert table.row_count() == 1

    idx2 = table.add_row(["x2", "y2"])
    assert idx2 == 1
    assert table.row_count() == 2


def test_add_row_data(qtbot) -> None:
    """Row data is stored in the model and retrievable."""
    table = TablaPersonalizada()
    qtbot.addWidget(table)
    table.set_columns(["Name", "Value"])

    table.add_row(["Foo", "42"])

    idx = table._model.index(0, 0)
    assert table._model.data(idx) == "Foo"
    idx2 = table._model.index(0, 1)
    assert table._model.data(idx2) == "42"


def test_clear(qtbot) -> None:
    """clear removes all rows and resets pagination."""
    table = TablaPersonalizada()
    qtbot.addWidget(table)
    table.set_columns(["X"])
    table.add_row(["a"])
    table.add_row(["b"])

    assert table.row_count() == 2

    table.clear()

    assert table.row_count() == 0
    assert table._current_page == 0


def test_search_filters_rows(qtbot) -> None:
    """Typing in search filters rows by matching text."""
    table = TablaPersonalizada()
    qtbot.addWidget(table)
    table.set_columns(["Name"])
    table.add_row(["Manzana"])
    table.add_row(["Banana"])
    table.add_row(["Cereza"])

    assert table._proxy.rowCount() == 3

    table._on_search("ana")

    assert table._proxy.rowCount() == 2  # Banana, Manzana


def test_search_clears(qtbot) -> None:
    """Empty search text shows all rows."""
    table = TablaPersonalizada()
    qtbot.addWidget(table)
    table.set_columns(["Name"])
    table.add_row(["Alpha"])
    table.add_row(["Beta"])

    table._on_search("Beta")
    assert table._proxy.rowCount() == 1

    table._on_search("")
    assert table._proxy.rowCount() == 2


def test_page_size_changes_pagination(qtbot) -> None:
    """Changing page size resets to first page."""
    table = TablaPersonalizada(page_size=1)
    qtbot.addWidget(table)
    table.set_columns(["X"])
    for i in range(5):
        table.add_row([f"Item {i}"])

    # Start on page 2
    table._next_page()
    assert table._current_page == 1

    # Change page size
    table._on_page_size_changed("10")
    assert table._current_page == 0


def test_pagination_navigation(qtbot) -> None:
    """Next/Prev buttons navigate through pages."""
    table = TablaPersonalizada(page_size=2)
    qtbot.addWidget(table)
    table.set_columns(["X"])
    for i in range(5):
        table.add_row([f"Item {i}"])

    # Initially on page 1 of 3
    assert "Página 1 de 3" in table._page_label.text()

    # Next page
    table._next_page()
    assert table._current_page == 1
    assert "Página 2 de 3" in table._page_label.text()

    # Prev page
    table._prev_page()
    assert table._current_page == 0
    assert "Página 1 de 3" in table._page_label.text()


def test_pagination_buttons_enabled_state(qtbot) -> None:
    """Prev is disabled on first page, Next is disabled on last page."""
    table = TablaPersonalizada(page_size=3)
    qtbot.addWidget(table)
    table.set_columns(["X"])
    for i in range(6):
        table.add_row([f"Item {i}"])

    # Page 1 of 2: prev disabled, next enabled
    assert table._prev_btn.isEnabled() is False
    assert table._next_btn.isEnabled() is True

    table._next_page()

    # Page 2 of 2: prev enabled, next disabled
    assert table._prev_btn.isEnabled() is True
    assert table._next_btn.isEnabled() is False


def test_page_size_combo(qtbot) -> None:
    """Page size combo has options 10, 25, 50, 100."""
    table = TablaPersonalizada()
    qtbot.addWidget(table)

    items = [
        table._page_size_combo.itemText(i)
        for i in range(table._page_size_combo.count())
    ]
    assert items == ["10", "25", "50", "100"]


def test_accessors(qtbot) -> None:
    """model(), proxy(), view() return the correct objects."""
    table = TablaPersonalizada()
    qtbot.addWidget(table)

    assert table.model() is table._model
    assert table.proxy() is table._proxy
    assert table.view() is table._view


def test_sorting_enabled(qtbot) -> None:
    """Table view has sorting enabled."""
    table = TablaPersonalizada()
    qtbot.addWidget(table)

    assert table._view.isSortingEnabled() is True


def test_alternating_row_colors(qtbot) -> None:
    """Table view has alternating row colors."""
    table = TablaPersonalizada()
    qtbot.addWidget(table)

    assert table._view.alternatingRowColors() is True


def test_empty_table_pagination(qtbot) -> None:
    """Empty table shows 'Página 1 de 1' with nav buttons disabled."""
    table = TablaPersonalizada()
    qtbot.addWidget(table)

    assert table._page_label.text() == "Página 1 de 1"
    assert table._prev_btn.isEnabled() is False
    assert table._next_btn.isEnabled() is False
