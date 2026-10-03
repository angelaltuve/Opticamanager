from decimal import Decimal
import uuid

from sqlmodel import select

from opticamanager.db import SessionManager
from opticamanager.models import Category, InventoryLog, Product, Role, User


def _clean_test_data() -> None:
    with SessionManager() as session:
        for log in session.exec(
            select(InventoryLog).where(
                InventoryLog.reason.in_(["Entrada manual", "Salida manual"])
            )
        ).all():
            session.delete(log)
        for c in session.exec(select(Product).where(Product.name.like("TEST-%"))).all():
            session.delete(c)
        for c in session.exec(
            select(Category).where(Category.name.like("TEST-%"))
        ).all():
            session.delete(c)
        session.commit()


def test_flujo_completo_crear_categoria_y_producto() -> None:
    _clean_test_data()

    cat_name = "TEST-Lentes Deportivos"
    prod_name = "TEST-Gafa Polarizada Roja"

    try:
        with SessionManager() as session:
            cat = Category(name=cat_name)
            session.add(cat)
            session.commit()
            cat_id = cat.id

        assert cat_id is not None
        assert cat_id > 0

        with SessionManager() as session:
            prod = Product(
                name=prod_name,
                barcode="TEST-ABC-123",
                cost_price_usd=Decimal("25.00"),
                sale_price_usd=Decimal("65.00"),
                stock_quantity=10,
                min_stock=3,
                category_id=cat_id,
            )
            session.add(prod)
            session.commit()
            prod_id = prod.id

        assert prod_id is not None

        with SessionManager() as session:
            producto = session.get(Product, prod_id)
            assert producto is not None
            assert producto.name == prod_name
            assert producto.barcode == "TEST-ABC-123"
            assert producto.cost_price_usd == Decimal("25.00")
            assert producto.sale_price_usd == Decimal("65.00")
            assert producto.stock_quantity == 10
            assert producto.min_stock == 3
            assert producto.active is True
            assert producto.category_id == cat_id
            assert producto.category is not None
            assert producto.category.name == cat_name

    finally:
        _clean_test_data()


def test_editar_producto() -> None:
    _clean_test_data()
    try:
        with SessionManager() as session:
            p = Product(
                name="TEST-Original",
                cost_price_usd=Decimal("10"),
                sale_price_usd=Decimal("20"),
                stock_quantity=5,
            )
            session.add(p)
            session.commit()
            pid = p.id

        with SessionManager() as session:
            p = session.get(Product, pid)
            assert p is not None
            p.name = "TEST-Modificado"
            p.sale_price_usd = Decimal("25")
            p.stock_quantity = 15
            p.active = False
            session.add(p)
            session.commit()

        with SessionManager() as session:
            p = session.get(Product, pid)
            assert p is not None
            assert p.name == "TEST-Modificado"
            assert p.sale_price_usd == Decimal("25")
            assert p.stock_quantity == 15
            assert p.active is False
            assert p.cost_price_usd == Decimal("10")
    finally:
        _clean_test_data()


def test_eliminar_producto() -> None:
    _clean_test_data()
    try:
        with SessionManager() as session:
            p = Product(
                name="TEST-ParaEliminar",
                cost_price_usd=Decimal("10"),
                sale_price_usd=Decimal("20"),
            )
            session.add(p)
            session.commit()
            pid = p.id

        with SessionManager() as session:
            p = session.get(Product, pid)
            assert p is not None
            session.delete(p)
            session.commit()

        with SessionManager() as session:
            p = session.get(Product, pid)
            assert p is None
    finally:
        _clean_test_data()


def test_buscar_producto() -> None:
    _clean_test_data()
    try:
        with SessionManager() as session:
            productos = [
                Product(
                    name="TEST-Lentes Sol",
                    barcode="SOL-001",
                    cost_price_usd=Decimal("10"),
                    sale_price_usd=Decimal("20"),
                ),
                Product(
                    name="TEST-Lentes Contacto",
                    barcode="CON-001",
                    cost_price_usd=Decimal("20"),
                    sale_price_usd=Decimal("40"),
                ),
                Product(
                    name="TEST-Accesorio Estuche",
                    barcode="ACC-001",
                    cost_price_usd=Decimal("5"),
                    sale_price_usd=Decimal("15"),
                ),
            ]
            for p in productos:
                session.add(p)
            session.commit()

        with SessionManager() as session:
            result = session.exec(
                select(Product)
                .where(Product.name.like("TEST-Lentes%"))
                .order_by(Product.name)
            ).all()
            assert len(result) == 2
            assert result[0].name == "TEST-Lentes Contacto"
            assert result[1].name == "TEST-Lentes Sol"

            result = session.exec(
                select(Product).where(Product.barcode == "ACC-001")
            ).all()
            assert len(result) == 1
            assert result[0].name == "TEST-Accesorio Estuche"

            result = session.exec(
                select(Product).where(
                    Product.name.like("TEST-%"),
                    Product.sale_price_usd > Decimal("15"),
                )
            ).all()
            assert len(result) == 2

            result = session.exec(
                select(Product).where(Product.name.like("TEST-Lentes Sol"))
            ).all()
            assert len(result) == 1
    finally:
        _clean_test_data()


def _crear_usuario_para_logs() -> User:
    """Create a real user: ``InventoryLog.user_id`` is a NOT NULL FK to ``users.id``.

    This test used to hardcode ``user_id=1``. Once ``PRAGMA foreign_keys=ON``
    reached every connection in the pool, that ID stopped existing and the
    INSERT failed with ``FOREIGN KEY constraint failed``.
    """
    with SessionManager() as session:
        role = session.exec(select(Role).where(Role.name == "Admin")).first()
        if role is None:
            role = Role(name="Admin", permissions="all")
            session.add(role)
            session.commit()
            session.refresh(role)

        user = User(
            username=f"test_logs_{uuid.uuid4().hex[:8]}",
            name="Test Logs",
            email=f"test_logs_{uuid.uuid4().hex[:8]}@test.com",
            password="x",
            role_id=role.id,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user


def test_movimiento_stock_entrada_manual() -> None:
    _clean_test_data()
    from opticamanager.models import InventoryLog

    user = _crear_usuario_para_logs()
    uid = user.id
    assert uid is not None

    try:
        with SessionManager() as session:
            p = Product(
                name="TEST-Stock Manual",
                cost_price_usd=Decimal("10"),
                sale_price_usd=Decimal("20"),
                stock_quantity=0,
            )
            session.add(p)
            session.commit()
            pid = p.id

        with SessionManager() as session:
            p = session.get(Product, pid)
            assert p is not None
            p.stock_quantity += 25
            log = InventoryLog(
                product_id=pid,
                quantity=25,
                reason="Entrada manual",
                user_id=uid,
            )
            session.add(log)
            session.add(p)
            session.commit()

        with SessionManager() as session:
            p = session.get(Product, pid)
            assert p is not None
            assert p.stock_quantity == 25

            logs = session.exec(
                select(InventoryLog).where(
                    InventoryLog.product_id == pid,
                    InventoryLog.reason == "Entrada manual",
                )
            ).all()
            assert len(logs) == 1
            assert logs[0].quantity == 25
            assert logs[0].user_id == uid

        with SessionManager() as session:
            p = session.get(Product, pid)
            assert p is not None
            p.stock_quantity -= 5
            log = InventoryLog(
                product_id=pid,
                quantity=-5,
                reason="Salida manual",
                user_id=uid,
            )
            session.add(log)
            session.add(p)
            session.commit()

        with SessionManager() as session:
            p = session.get(Product, pid)
            assert p is not None
            assert p.stock_quantity == 20

            logs = session.exec(
                select(InventoryLog).where(
                    InventoryLog.product_id == pid,
                    InventoryLog.reason == "Salida manual",
                )
            ).all()
            assert len(logs) == 1
            assert logs[0].quantity == -5
    finally:
        _clean_test_data()
        with SessionManager() as session:
            u = session.get(User, uid)
            if u is not None:
                session.delete(u)
            session.commit()
