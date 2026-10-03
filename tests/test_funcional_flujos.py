"""Functional/integration tests for OpticaManager core business flows.

Tests exercise real DB operations through service-layer functions.
All test data uses the TEST_FUNC_ prefix for safe cleanup.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlmodel import select

from opticamanager.db import SessionManager
from opticamanager.models import (
    CashSession,
    Category,
    Customer,
    InventoryLog,
    Prescription,
    Product,
    Role,
    Sale,
    SaleDetail,
    SaleStatus,
    Supplier,
    User,
)
from opticamanager.services import (
    registrar_venta,
    registrar_compra,
    ajustar_stock,
    create_category,
    get_category,
    update_category,
    delete_category,
    list_categories,
    get_rate_info,
    set_manual_rate,
    clear_manual_rate,
)
from opticamanager.services.cash_session_service import (
    open_session,
    close_session,
    get_active_session,
    get_session_summary,
)

# ── Module-level shared fixture IDs ──────────────────────────────────
_ROLE_ID: int | None = None
_USER_ID: int | None = None
_STATUS_ID: int | None = None
_CUSTOMER_ID: int | None = None

# Track per-test sale IDs for targeted cleanup (invoices don't carry
# a TEST_FUNC_ prefix)
_SALE_IDS: set[int] = set()

# ── Module-level fixtures ───────────────────────────────────────────


def setup_module() -> None:
    """Create shared fixtures for all tests in this module."""
    global _ROLE_ID, _USER_ID, _STATUS_ID, _CUSTOMER_ID  # noqa: PLW0603
    with SessionManager() as session:
        role = session.exec(select(Role).where(Role.name == "TEST_FUNC_Admin")).first()
        if not role:
            role = Role(name="TEST_FUNC_Admin")
            session.add(role)
            session.commit()
            session.refresh(role)
        _ROLE_ID = role.id

        user = session.exec(select(User).where(User.username == "test_func")).first()
        if not user:
            user = User(
                username="test_func",
                name="Test Func User",
                email="test_func@optica.com",
                password="x",
                role_id=_ROLE_ID,
            )
            session.add(user)
            session.commit()
            session.refresh(user)
        _USER_ID = user.id

        status = session.exec(
            select(SaleStatus).where(SaleStatus.name == "Completada")
        ).first()
        if not status:
            status = SaleStatus(name="Completada")
            session.add(status)
            session.commit()
            session.refresh(status)
        _STATUS_ID = status.id

        cust = session.exec(
            select(Customer).where(Customer.id_document == "TEST_FUNC_V-99999")
        ).first()
        if not cust:
            cust = Customer(
                id_document="TEST_FUNC_V-99999",
                name="TEST_FUNC_Cliente",
                phone="04121234567",
            )
            session.add(cust)
            session.commit()
            session.refresh(cust)
        _CUSTOMER_ID = cust.id


def teardown_module() -> None:
    """Remove all TEST_FUNC_ data left by tests, including fixtures."""
    _do_cleanup(include_fixtures=True)


# ── Helpers ──────────────────────────────────────────────────────────


def _create_test_product(
    session,
    name: str,
    stock: int = 100,
    sale_price_usd: str = "50.00",
    cost_price_usd: str = "25.00",
    active: bool = True,
) -> Product:
    """Create a Product with the TEST_FUNC_ prefix and return it."""
    p = Product(
        name=f"TEST_FUNC_{name}",
        cost_price_usd=Decimal(cost_price_usd),
        sale_price_usd=Decimal(sale_price_usd),
        stock_quantity=stock,
        active=active,
    )
    session.add(p)
    session.commit()
    session.refresh(p)
    return p


def _do_cleanup(*, include_fixtures: bool = False) -> None:
    """Delete all TEST_FUNC_ records.

    Parameters
    ----------
    include_fixtures : bool
        If True, also deletes the shared fixtures (Role, User, Status, Customer).
    """
    with SessionManager() as session:
        # ── SaleDetail + Sale (by tracked IDs) ──
        for sid in list(_SALE_IDS):
            s = session.get(Sale, sid)
            if s is not None:
                for d in session.exec(
                    select(SaleDetail).where(SaleDetail.sale_id == sid)
                ).all():
                    session.delete(d)
                session.delete(s)
        _SALE_IDS.clear()
        session.commit()

        # ── InventoryLog ──
        for p in session.exec(
            select(Product).where(Product.name.like("TEST_FUNC_%"))
        ).all():
            for log in session.exec(
                select(InventoryLog).where(InventoryLog.product_id == p.id)
            ).all():
                session.delete(log)
        session.commit()

        # ── Product ──
        for p in session.exec(
            select(Product).where(Product.name.like("TEST_FUNC_%"))
        ).all():
            session.delete(p)
        session.commit()

        # ── CashSession ──
        for cs in session.exec(
            select(CashSession).where(CashSession.user_id == _USER_ID)
        ).all():
            session.delete(cs)
        session.commit()

        # ── Prescription ──
        for rx in session.exec(
            select(Prescription).where(Prescription.customer_id == _CUSTOMER_ID)
        ).all():
            session.delete(rx)
        session.commit()

        # ── Category ──
        for c in session.exec(
            select(Category).where(Category.name.like("TEST_FUNC_%"))
        ).all():
            session.delete(c)
        session.commit()

        # ── Supplier ──
        for s in session.exec(
            select(Supplier).where(Supplier.company_name.like("TEST_FUNC_%"))
        ).all():
            session.delete(s)
        session.commit()

        # ── Shared fixtures (only on full teardown) ──
        if include_fixtures:
            session.exec(select(User).where(User.username == "test_func")).all()
            for u in session.exec(
                select(User).where(User.username == "test_func")
            ).all():
                session.delete(u)
            session.commit()

            for r in session.exec(
                select(Role).where(Role.name == "TEST_FUNC_Admin")
            ).all():
                session.delete(r)
            session.commit()

            session.exec(
                select(SaleStatus).where(SaleStatus.name == "Completada")
            ).all()
            for st in session.exec(
                select(SaleStatus).where(SaleStatus.name == "Completada")
            ).all():
                session.delete(st)
            session.commit()

            for c in session.exec(
                select(Customer).where(Customer.id_document == "TEST_FUNC_V-99999")
            ).all():
                session.delete(c)
            session.commit()


# ═══════════════════════════════════════════════════════════════════
# TEST 1: Complete sale flow (the most critical business path)
# ═══════════════════════════════════════════════════════════════════


def test_1_complete_sale_flow() -> None:
    """Register a sale and verify stock, invoice, logs, details, cash session."""
    _do_cleanup()

    try:
        # ── Setup ──
        with SessionManager() as session:
            p = _create_test_product(
                session, "VentaFlow", stock=50, sale_price_usd="60.00"
            )
            pid = p.id

        # Open cash session for the test user
        cs = open_session(_USER_ID, Decimal("1000"))

        # ── Execute ──
        sale = registrar_venta(
            customer_id=_CUSTOMER_ID,
            user_id=_USER_ID,
            items=[{"product_id": pid, "quantity": 3, "unit_price": "60.00"}],
            payment_method="Efectivo",
            status_id=_STATUS_ID,
        )
        _SALE_IDS.add(sale.id)

        # ── Assertions ──
        # Invoice number format
        assert sale.invoice_number.startswith("FAC-"), (
            f"Expected invoice to start with FAC-, got {sale.invoice_number}"
        )
        # Total calculation: 60.00 * 3 = 180.00
        assert sale.total == Decimal("180.00"), (
            f"Expected total 180.00, got {sale.total}"
        )
        assert sale.subtotal == sale.total, (
            f"Expected subtotal == total ({sale.total}), got {sale.subtotal}"
        )
        assert sale.discount == Decimal("0")
        assert sale.payment_method == "Efectivo"

        # Stock decrement: 50 - 3 = 47
        with SessionManager() as session:
            p = session.get(Product, pid)
            assert p is not None
            assert p.stock_quantity == 47, f"Expected stock 47, got {p.stock_quantity}"

        # InventoryLog with quantity=-3, reason="Venta"
        with SessionManager() as session:
            logs = session.exec(
                select(InventoryLog).where(
                    InventoryLog.product_id == pid,
                    InventoryLog.reason == "Venta",
                )
            ).all()
            matching = [log for log in logs if log.quantity == -3]
            assert len(matching) >= 1, (
                "No InventoryLog found with quantity=-3, reason=Venta"
            )
            assert matching[0].user_id == _USER_ID

        # SaleDetail with quantity=3
        with SessionManager() as session:
            details = session.exec(
                select(SaleDetail).where(SaleDetail.sale_id == sale.id)
            ).all()
            assert len(details) == 1, f"Expected 1 detail, got {len(details)}"
            assert details[0].quantity == 3
            assert details[0].unit_price == Decimal("60.00")

        # Cash session summary includes this sale
        active_cs = get_active_session(_USER_ID)
        assert active_cs is not None
        summary = get_session_summary(cs)
        assert summary["sales_count"] >= 1, (
            "Expected at least 1 sale in session summary"
        )
        assert summary["total_sales"] >= Decimal("180.00")
        assert "Efectivo" in summary["by_method"]
        assert summary["by_method"]["Efectivo"] >= Decimal("180.00")

    finally:
        _do_cleanup()


# ═══════════════════════════════════════════════════════════════════
# TEST 2: Multi-item sale with discount
# ═══════════════════════════════════════════════════════════════════


def test_2_multi_item_sale_with_discount() -> None:
    """Sell two products at once with a discount, verify totals and stocks."""
    _do_cleanup()

    try:
        with SessionManager() as session:
            p1 = _create_test_product(
                session, "MultiItemA", stock=20, sale_price_usd="100.00"
            )
            p2 = _create_test_product(
                session, "MultiItemB", stock=15, sale_price_usd="50.00"
            )
            pid1, pid2 = p1.id, p2.id

        sale = registrar_venta(
            customer_id=_CUSTOMER_ID,
            user_id=_USER_ID,
            items=[
                {"product_id": pid1, "quantity": 2, "unit_price": "100.00"},
                {"product_id": pid2, "quantity": 3, "unit_price": "50.00"},
            ],
            discount=Decimal("10"),
            status_id=_STATUS_ID,
        )
        _SALE_IDS.add(sale.id)

        # Expected: (2*100 + 3*50) - 10 = (200+150) - 10 = 340
        expected_total = Decimal("340.00")
        expected_subtotal = Decimal("350.00")

        assert sale.total == expected_total, (
            f"Expected total {expected_total}, got {sale.total}"
        )
        assert sale.subtotal == expected_subtotal
        assert sale.discount == Decimal("10")

        # Stock checks
        with SessionManager() as session:
            p1 = session.get(Product, pid1)
            assert p1 is not None
            assert p1.stock_quantity == 18, (
                f"p1 stock: expected 18, got {p1.stock_quantity}"
            )

            p2 = session.get(Product, pid2)
            assert p2 is not None
            assert p2.stock_quantity == 12, (
                f"p2 stock: expected 12, got {p2.stock_quantity}"
            )

    finally:
        _do_cleanup()


# ═══════════════════════════════════════════════════════════════════
# TEST 3: Sale with mixed payment
# ═══════════════════════════════════════════════════════════════════


def test_3_mixed_payment_sale() -> None:
    """Register a sale with payment_method='Mixto' and verify stored value."""
    _do_cleanup()

    try:
        with SessionManager() as session:
            p = _create_test_product(
                session, "PagoMixto", stock=10, sale_price_usd="30.00"
            )
            pid = p.id

        sale = registrar_venta(
            customer_id=_CUSTOMER_ID,
            user_id=_USER_ID,
            items=[{"product_id": pid, "quantity": 1, "unit_price": "30.00"}],
            payment_method="Mixto",
            amount_received=Decimal("100"),
            change_amount=Decimal("0"),
            status_id=_STATUS_ID,
        )
        _SALE_IDS.add(sale.id)

        assert sale.payment_method == "Mixto", (
            f"Expected payment_method='Mixto', got '{sale.payment_method}'"
        )
        assert sale.amount_received == Decimal("100")
        assert sale.change_amount == Decimal("0")

    finally:
        _do_cleanup()


# ═══════════════════════════════════════════════════════════════════
# TEST 4: Insufficient stock rejection
# ═══════════════════════════════════════════════════════════════════


def test_4_insufficient_stock_rejection() -> None:
    """Attempt to sell more than available stock; must raise ValueError."""
    _do_cleanup()

    try:
        with SessionManager() as session:
            p = _create_test_product(
                session, "SinStock", stock=2, sale_price_usd="25.00"
            )
            pid = p.id

        try:
            registrar_venta(
                customer_id=_CUSTOMER_ID,
                user_id=_USER_ID,
                items=[{"product_id": pid, "quantity": 10, "unit_price": "25.00"}],
                status_id=_STATUS_ID,
            )
            msg = "Expected ValueError for insufficient stock — not raised"
            raise AssertionError(msg)  # noqa: TRY301
        except ValueError as e:
            assert "Stock insuficiente" in str(e), f"Unexpected error: {e}"

        # Verify stock unchanged
        with SessionManager() as session:
            p = session.get(Product, pid)
            assert p is not None
            assert p.stock_quantity == 2, (
                f"Stock should remain 2, got {p.stock_quantity}"
            )

    finally:
        _do_cleanup()


# ═══════════════════════════════════════════════════════════════════
# TEST 5: Buying inactive product
# ═══════════════════════════════════════════════════════════════════


def test_5_inactive_product_rejection() -> None:
    """Attempt to sell a product with active=False; must raise ValueError."""
    _do_cleanup()

    try:
        with SessionManager() as session:
            p = _create_test_product(
                session, "Inactivo", stock=10, sale_price_usd="40.00", active=False
            )
            pid = p.id

        try:
            registrar_venta(
                customer_id=_CUSTOMER_ID,
                user_id=_USER_ID,
                items=[{"product_id": pid, "quantity": 1, "unit_price": "40.00"}],
                status_id=_STATUS_ID,
            )
            msg = "Expected ValueError for inactive product — not raised"
            raise AssertionError(msg)  # noqa: TRY301
        except ValueError as e:
            assert "no está activo" in str(e), f"Unexpected error: {e}"

        # Stock unchanged
        with SessionManager() as session:
            p = session.get(Product, pid)
            assert p is not None
            assert p.stock_quantity == 10

    finally:
        _do_cleanup()


# ═══════════════════════════════════════════════════════════════════
# TEST 6: Purchase flow
# ═══════════════════════════════════════════════════════════════════


def test_6_purchase_flow() -> None:
    """Register a purchase and verify stock increase and log."""
    _do_cleanup()

    try:
        with SessionManager() as session:
            p = _create_test_product(session, "Compra", stock=10, cost_price_usd="8.00")
            pid = p.id

        producto = registrar_compra(
            product_id=pid, quantity=50, unit_cost=Decimal("8.00"), user_id=_USER_ID
        )

        # Stock: 10 + 50 = 60
        assert producto.stock_quantity == 60, (
            f"Expected stock 60, got {producto.stock_quantity}"
        )

        # Verify log entry
        with SessionManager() as session:
            logs = session.exec(
                select(InventoryLog).where(
                    InventoryLog.product_id == pid,
                    InventoryLog.reason == "Compra",
                )
            ).all()
            matching = [log for log in logs if log.quantity == 50]
            assert len(matching) >= 1, "No InventoryLog with quantity=50, reason=Compra"
            assert matching[0].unit_cost == Decimal("8.00"), (
                f"Expected unit_cost 8.00, got {matching[0].unit_cost}"
            )

    finally:
        _do_cleanup()


# ═══════════════════════════════════════════════════════════════════
# TEST 7: Stock adjustment
# ═══════════════════════════════════════════════════════════════════


def test_7_stock_adjustment() -> None:
    """Adjust stock downward for damage and verify the change."""
    _do_cleanup()

    try:
        with SessionManager() as session:
            p = _create_test_product(session, "Ajuste", stock=100)
            pid = p.id

        ajustar_stock(product_id=pid, quantity=-15, reason="Dañado", user_id=_USER_ID)

        with SessionManager() as session:
            p = session.get(Product, pid)
            assert p is not None
            assert p.stock_quantity == 85, f"Expected stock 85, got {p.stock_quantity}"

            logs = session.exec(
                select(InventoryLog).where(
                    InventoryLog.product_id == pid,
                    InventoryLog.reason == "Dañado",
                )
            ).all()
            matching = [log for log in logs if log.quantity == -15]
            assert len(matching) >= 1, (
                "No InventoryLog with quantity=-15, reason=Dañado"
            )

    finally:
        _do_cleanup()


# ═══════════════════════════════════════════════════════════════════
# TEST 8: Category CRUD via service
# ═══════════════════════════════════════════════════════════════════


def test_8_category_crud() -> None:
    """Create, read, update, list, and delete categories via service layer."""
    _do_cleanup()

    try:
        cat_name = "TEST_FUNC_Lentes"
        cat_desc = "Lentes ópticos"

        # ── Create ──
        cat = create_category(cat_name, cat_desc)
        assert cat.id is not None
        assert cat.name == cat_name
        assert cat.description == cat_desc

        cid = cat.id

        # ── Get ──
        fetched = get_category(cid)
        assert fetched is not None
        assert fetched.name == cat_name
        assert fetched.description == cat_desc

        # ── Update ──
        new_name = "TEST_FUNC_Lentes Sol"
        new_desc = "Lentes de sol"
        updated = update_category(cid, new_name, new_desc)
        assert updated.name == new_name
        assert updated.description == new_desc

        # ── List ──
        all_cats = list_categories()
        names = [c.name for c in all_cats]
        assert new_name in names

        # ── Delete ──
        result = delete_category(cid)
        assert result is True

        # Verify it's gone
        assert get_category(cid) is None

        # ── Delete non-existent → False ──
        result = delete_category(99999999)
        assert result is False

        # ── Update non-existent → ValueError ──
        try:
            update_category(99999999, "x", "y")
            msg = "Expected ValueError for non-existent category — not raised"
            raise AssertionError(msg)  # noqa: TRY301
        except ValueError as e:
            assert "no encontrada" in str(e)

    finally:
        _do_cleanup()


# ═══════════════════════════════════════════════════════════════════
# TEST 9: Cash Session service
# ═══════════════════════════════════════════════════════════════════


def test_9_cash_session_service() -> None:
    """Open, query, close, and verify cash session lifecycle."""
    _do_cleanup()

    try:
        # Open session
        cs = open_session(_USER_ID, Decimal("500"))
        cs_id = cs.id
        assert cs_id is not None
        assert cs.initial_balance == Decimal("500")
        assert cs.closed_at is None

        # Get active session
        active = get_active_session(_USER_ID)
        assert active is not None
        assert active.id == cs_id
        assert active.closed_at is None

        # Close session
        closed = close_session(cs_id, Decimal("1500"))
        assert closed.closed_at is not None
        assert closed.final_balance == Decimal("1500")

        # Close again → ValueError
        try:
            close_session(cs_id, Decimal("2000"))
            msg = "Expected ValueError for double close — not raised"
            raise AssertionError(msg)  # noqa: TRY301
        except ValueError as e:
            assert "ya está cerrada" in str(e)

    finally:
        _do_cleanup()


# ═══════════════════════════════════════════════════════════════════
# TEST 10: Exchange Rate service
# ═══════════════════════════════════════════════════════════════════


def test_10_exchange_rate_service() -> None:
    """Query rate info, set manual rate, clear it, and verify source changes."""
    # No test data cleanup needed; this module is stateless beyond
    # module-level globals that are restored by the test itself.

    # ── get_rate_info always returns something ──
    info = get_rate_info()
    assert info.rate is not None
    assert info.source in ("bcv", "manual", "unknown")
    # updated_at may be None when source is "unknown"

    # ── Set manual rate ──
    set_manual_rate(Decimal("60"))
    info = get_rate_info()
    assert info.rate == Decimal("60"), f"Expected 60, got {info.rate}"
    assert info.source == "manual"
    assert info.updated_at is not None

    # ── Clear manual rate: source should NOT be "manual" ──
    clear_manual_rate()
    info = get_rate_info()
    assert info.source != "manual", (
        "After clear_manual_rate(), source should not be 'manual'"
    )


# ═══════════════════════════════════════════════════════════════════
# TEST 11: Prescription and sale linkage
# ═══════════════════════════════════════════════════════════════════


def test_11_prescription_sale_linkage() -> None:
    """Create a prescription and link it to a sale via prescription_id."""
    _do_cleanup()

    try:
        # ── Create prescription for the shared test customer ──
        rx = Prescription(
            customer_id=_CUSTOMER_ID,
            od_sphere=Decimal("-2.00"),
            od_cylinder=Decimal("-0.50"),
            od_axis=180,
            od_addition=Decimal("0.00"),
            os_sphere=Decimal("-1.50"),
            os_cylinder=Decimal("-0.25"),
            os_axis=175,
            os_addition=Decimal("0.00"),
            pupillary_distance=Decimal("62.0"),
            issued_date=date.today(),
            notes="TEST_FUNC_ Prescription notes",
        )
        with SessionManager() as session:
            session.add(rx)
            session.commit()
            session.refresh(rx)
            rx_id = rx.id

        assert rx_id is not None
        assert rx.customer_id == _CUSTOMER_ID

        # ── Create a product ──
        with SessionManager() as session:
            p = _create_test_product(
                session, "RxLink", stock=5, sale_price_usd="120.00"
            )
            pid = p.id

        # ── Register sale with prescription link ──
        sale = registrar_venta(
            customer_id=_CUSTOMER_ID,
            user_id=_USER_ID,
            items=[{"product_id": pid, "quantity": 1, "unit_price": "120.00"}],
            prescription_id=rx_id,
            status_id=_STATUS_ID,
        )
        _SALE_IDS.add(sale.id)

        # ── Verify linkage ──
        assert sale.prescription_id == rx_id, (
            f"Expected prescription_id={rx_id}, got {sale.prescription_id}"
        )

        # Verify from the DB side
        with SessionManager() as session:
            sale_db = session.get(Sale, sale.id)
            assert sale_db is not None
            assert sale_db.prescription_id == rx_id

            # Verify prescription has the sale in its relationship
            rx_db = session.get(Prescription, rx_id)
            assert rx_db is not None
            # The relationship may not be loaded unless we query explicitly
            sales_from_rx = session.exec(
                select(Sale).where(Sale.prescription_id == rx_id)
            ).all()
            assert len(sales_from_rx) >= 1
            assert sales_from_rx[0].id == sale.id

    finally:
        _do_cleanup()
