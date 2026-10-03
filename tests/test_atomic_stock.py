from decimal import Decimal

import pytest
from sqlmodel import Session, select

from opticamanager.core.session import UserData, UserSession
from opticamanager.db import SessionManager
from opticamanager.models.customer import Customer
from opticamanager.models.inventory_log import InventoryLog
from opticamanager.models.product import Product
from opticamanager.models.role import Role
from opticamanager.models.sale import Sale
from opticamanager.models.sale_detail import SaleDetail
from opticamanager.models.sale_payment import SalePayment
from opticamanager.models.sale_status import SaleStatus
from opticamanager.models.user import User
from opticamanager.services.stock_service import (
    ajustar_stock,
    atomic_stock,
    reembolsar_venta,
    registrar_compra,
    registrar_venta,
)

_UID: int | None = None
_CID: int | None = None
_SID: int = 1  # SaleStatus ID for Completada (default 1)
_ADMIN_RID: int | None = None


def setup_module() -> None:
    global _UID, _CID, _SID, _ADMIN_RID
    with SessionManager() as session:
        role = session.exec(select(Role).where(Role.name == "Admin")).first()
        if not role:
            role = Role(name="Admin")
            session.add(role)
            session.commit()
        _ADMIN_RID = role.id
        user = session.exec(select(User).where(User.username == "test_stock")).first()
        if not user:
            user = User(
                username="test_stock",
                name="Test Stock",
                email="test@stock.com",
                password="x",
                role_id=role.id,
            )
            session.add(user)
            session.commit()
        _UID = user.id

        st = session.exec(
            select(SaleStatus).where(SaleStatus.name == "Completada")
        ).first()
        if not st:
            st = SaleStatus(name="Completada")
            session.add(st)
            session.commit()
        _SID = st.id

        refunded = session.exec(
            select(SaleStatus).where(SaleStatus.name == "Rembolsada")
        ).first()
        if not refunded:
            session.add(SaleStatus(name="Rembolsada"))
            session.commit()

        cust = session.exec(
            select(Customer).where(Customer.id_document == "V-99999999")
        ).first()
        if not cust:
            cust = Customer(
                id_document="V-99999999",
                name="Cliente Test Stock",
                phone="04121234567",
            )
            session.add(cust)
            session.commit()
        _CID = cust.id


def teardown_module() -> None:
    with SessionManager() as session:
        for s in session.exec(select(Sale)).all():
            for pay in s.payments:
                session.delete(pay)
            for d in s.details:
                session.delete(d)
            session.delete(s)
        for p in session.exec(select(Product).where(Product.name.like("TEST-%"))).all():
            log_entries = session.exec(
                select(InventoryLog).where(InventoryLog.product_id == p.id)
            ).all()
            for log in log_entries:
                session.delete(log)
            session.delete(p)
        session.commit()


def _create_test_product(session: Session, name: str, stock: int = 100) -> Product:
    p = Product(
        name=f"TEST-{name}",
        cost_price_usd=Decimal("10"),
        sale_price_usd=Decimal("15"),
        stock_quantity=stock,
    )
    session.add(p)
    session.commit()
    return p


def test_atomic_stock_importable() -> None:
    assert callable(atomic_stock)


def test_atomic_stock_validates_negative_stock() -> None:
    @atomic_stock(reason="Test", validate_stock=True)
    def reducir_stock(session: Session, product_id: int, cantidad: int) -> Product:
        p = session.get(Product, product_id)
        p.stock_quantity -= cantidad
        return p

    with SessionManager() as session:
        p = _create_test_product(session, "Negativo", stock=5)
        pid = p.id

    try:
        reducir_stock(product_id=pid, cantidad=10)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "Stock insuficiente" in str(e)

    with SessionManager() as session:
        p = session.get(Product, pid)
        assert p is not None
        assert p.stock_quantity == 5


def test_atomic_stock_commits_success() -> None:
    @atomic_stock(reason="Test", validate_stock=True)
    def aumentar_stock(session: Session, product_id: int, cantidad: int) -> Product:
        p = session.get(Product, product_id)
        p.stock_quantity += cantidad
        return p

    with SessionManager() as session:
        p = _create_test_product(session, "Commit", stock=0)
        pid = p.id

    aumentar_stock(product_id=pid, cantidad=10)

    with SessionManager() as session:
        p = session.get(Product, pid)
        assert p is not None
        assert p.stock_quantity == 10


def test_registrar_venta_creates_sale_and_logs() -> None:
    with SessionManager() as session:
        p = _create_test_product(session, "VentaTest", stock=20)
        pid = p.id

    sale = registrar_venta(
        customer_id=_CID,
        user_id=_UID,
        items=[{"product_id": pid, "quantity": 3, "unit_price": "15.00"}],
        status_id=_SID,
    )

    assert sale.invoice_number.startswith("FAC-")
    assert sale.total == Decimal("45.00")

    with SessionManager() as session:
        p = session.get(Product, pid)
        assert p is not None
        assert p.stock_quantity == 17

        logs = session.exec(
            select(InventoryLog).where(
                InventoryLog.product_id == pid, InventoryLog.reason == "Venta"
            )
        ).all()
        assert len(logs) >= 1
        log_entry = next(log for log in logs if log.quantity == -3)
        assert log_entry.user_id == _UID

        details = session.exec(
            select(SaleDetail).where(SaleDetail.sale_id == sale.id)
        ).all()
        assert len(details) == 1
        assert details[0].quantity == 3


def test_registrar_venta_insufficient_stock() -> None:
    with SessionManager() as session:
        p = _create_test_product(session, "VentaSinStock", stock=2)
        pid = p.id

    try:
        registrar_venta(
            customer_id=_CID,
            user_id=_UID,
            items=[{"product_id": pid, "quantity": 10, "unit_price": "15.00"}],
            status_id=_SID,
        )
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "Stock insuficiente" in str(e)

    with SessionManager() as session:
        p = session.get(Product, pid)
        assert p is not None
        assert p.stock_quantity == 2


def test_registrar_compra_increases_stock_and_logs() -> None:
    with SessionManager() as session:
        p = _create_test_product(session, "CompraTest", stock=0)
        pid = p.id

    producto = registrar_compra(
        product_id=pid,
        quantity=50,
        unit_cost=Decimal("8.00"),
        user_id=_UID,
    )

    assert producto.stock_quantity == 50

    with SessionManager() as session:
        logs = session.exec(
            select(InventoryLog).where(
                InventoryLog.product_id == pid, InventoryLog.reason == "Compra"
            )
        ).all()
        assert len(logs) >= 1
        log_entry = next(log for log in logs if log.quantity == 50)
        assert log_entry.unit_cost == Decimal("8.00")


def test_ajustar_stock() -> None:
    with SessionManager() as session:
        p = _create_test_product(session, "AjusteTest", stock=10)
        pid = p.id

    ajustar_stock(
        product_id=pid,
        quantity=-3,
        reason="Dañado",
        user_id=_UID,
    )

    with SessionManager() as session:
        p = session.get(Product, pid)
        assert p is not None
        assert p.stock_quantity == 7

        logs = session.exec(
            select(InventoryLog).where(
                InventoryLog.product_id == pid, InventoryLog.reason == "Dañado"
            )
        ).all()
        assert len(logs) >= 1
        log_entry = next(log for log in logs if log.quantity == -3)
        assert log_entry.user_id == _UID


def test_registrar_venta_with_payments_mixto() -> None:
    """registrar_venta persists SalePayment rows and marks method 'Mixto'."""
    with SessionManager() as session:
        p = _create_test_product(session, "VentaPagos", stock=20)
        pid = p.id

    sale = registrar_venta(
        customer_id=_CID,
        user_id=_UID,
        items=[{"product_id": pid, "quantity": 2, "unit_price": "50.00"}],
        status_id=_SID,
        payment_method="Mixto",
        amount_received=Decimal("100.00"),
        change_amount=Decimal("0.00"),
        taxes=Decimal("0.00"),
        payments=[
            {
                "method": "Pago Móvil",
                "currency": "Bs",
                "amount": Decimal("40.00"),
                "amount_bs": Decimal("40.00"),
                "rate_used": None,
            },
            {
                "method": "Efectivo Bs",
                "currency": "Bs",
                "amount": Decimal("60.00"),
                "amount_bs": Decimal("60.00"),
                "rate_used": None,
            },
        ],
    )

    assert sale.payment_method == "Mixto"
    assert sale.total == Decimal("100.00")

    with SessionManager() as session:
        details = session.exec(
            select(SaleDetail).where(SaleDetail.sale_id == sale.id)
        ).all()
        assert len(details) == 1
        assert details[0].quantity == 2

        snaps = session.exec(
            select(SalePayment).where(SalePayment.sale_id == sale.id)
        ).all()
        assert len(snaps) == 2
        methods = {p.method for p in snaps}
        assert methods == {"Pago Móvil", "Efectivo Bs"}
        for p in snaps:
            assert p.amount_bs == p.amount
            assert p.currency == "Bs"
            assert p.rate_used is None


def test_registrar_venta_with_payments_usd_efectivo() -> None:
    """registrar_venta persists a USD cash payment using the reference rate."""
    with SessionManager() as session:
        p = _create_test_product(session, "VentaUSD", stock=10)
        pid = p.id

    sale = registrar_venta(
        customer_id=_CID,
        user_id=_UID,
        items=[{"product_id": pid, "quantity": 1, "unit_price": "300.00"}],
        status_id=_SID,
        payment_method="Efectivo Dólares",
        amount_received=Decimal("7.50"),
        change_amount=Decimal("0.00"),
        taxes=Decimal("0.00"),
        payments=[
            {
                "method": "Efectivo Dólares",
                "currency": "USD",
                "amount": Decimal("7.50"),
                "amount_bs": Decimal("300.00"),
                "rate_used": Decimal("40.00"),
            }
        ],
    )

    assert sale.payment_method == "Efectivo Dólares"

    with SessionManager() as session:
        snaps = session.exec(
            select(SalePayment).where(SalePayment.sale_id == sale.id)
        ).all()
        assert len(snaps) == 1
        snap = snaps[0]
        assert snap.method == "Efectivo Dólares"
        assert snap.currency == "USD"
        assert snap.amount == Decimal("7.50")
        assert snap.amount_bs == Decimal("300.00")
        assert snap.rate_used == Decimal("40.00")


# ── Sale refunds ───────────────────────────────────────────────────────


def _loguear(rol: str, rol_id: int | None) -> None:
    UserSession._user = UserData(
        id=_UID or 0,
        username="test_stock",
        name="Test Stock",
        email="test@stock.com",
        role_id=rol_id,
        role_name=rol,
    )


@pytest.fixture
def admin_session_user() -> None:
    _loguear("Admin", _ADMIN_RID)
    yield
    UserSession._user = None


@pytest.fixture
def vendedor_session_user() -> None:
    _loguear("Vendedor", None)
    yield
    UserSession._user = None


def _crear_venta(pid: int, cantidad: int = 3) -> Sale:
    return registrar_venta(
        customer_id=_CID,
        user_id=_UID,
        items=[{"product_id": pid, "quantity": cantidad, "unit_price": "15.00"}],
        status_id=_SID,
    )


def test_reembolsar_venta_restaura_stock_y_marca_rembolsada(
    admin_session_user: None,
) -> None:
    with SessionManager() as session:
        p = _create_test_product(session, "RembolsoTest", stock=20)
        pid = p.id

    cantidad = 3
    sale = _crear_venta(pid, cantidad)

    with SessionManager() as session:
        p = session.get(Product, pid)
        assert p is not None
        assert p.stock_quantity == 17

    result = reembolsar_venta(sale_id=sale.id, user_id=_UID)

    assert result is not None
    assert result.id == sale.id

    with SessionManager() as session:
        sale_db = session.get(Sale, sale.id)
        assert sale_db is not None
        refunded = session.exec(
            select(SaleStatus).where(SaleStatus.name == "Rembolsada")
        ).first()
        assert refunded is not None
        assert sale_db.status_id == refunded.id

        p = session.get(Product, pid)
        assert p is not None
        assert p.stock_quantity == 20

        logs = session.exec(
            select(InventoryLog).where(
                InventoryLog.product_id == pid,
                InventoryLog.reason == "Rembolso",
            )
        ).all()
        assert len(logs) >= 1
        entry = next(log for log in logs if log.quantity == cantidad)
        assert entry.user_id == _UID


def test_reembolsar_venta_doble_rembolso_error(admin_session_user: None) -> None:
    with SessionManager() as session:
        p = _create_test_product(session, "RembolsoDoble", stock=20)
        pid = p.id

    sale = _crear_venta(pid)
    reembolsar_venta(sale_id=sale.id, user_id=_UID)

    try:
        reembolsar_venta(sale_id=sale.id, user_id=_UID)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "ya fue rembolsada" in str(e)


def test_reembolsar_venta_inexistente_error(admin_session_user: None) -> None:
    try:
        reembolsar_venta(sale_id=999_999, user_id=_UID)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "no encontrada" in str(e)


def test_reembolsar_venta_solo_admin(vendedor_session_user: None) -> None:
    with SessionManager() as session:
        p = _create_test_product(session, "RembolsoNoAdmin", stock=20)
        pid = p.id

    sale = _crear_venta(pid)

    with pytest.raises(PermissionError):
        reembolsar_venta(sale_id=sale.id, user_id=_UID)

    with SessionManager() as session:
        sale_db = session.get(Sale, sale.id)
        assert sale_db is not None
        assert sale_db.status_id == _SID

        p = session.get(Product, pid)
        assert p is not None
        assert p.stock_quantity == 17
