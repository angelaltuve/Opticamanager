from __future__ import annotations

from decimal import Decimal
from functools import wraps
import re
from typing import TYPE_CHECKING, Callable, ParamSpec, TypeVar

from sqlmodel import Session, select

from opticamanager.core.logging_config import get_logger
from opticamanager.core.session import require_role
from opticamanager.db import SessionManager

if TYPE_CHECKING:
    from opticamanager.models.product import Product
    from opticamanager.models.sale import Sale

log = get_logger(__name__)

P = ParamSpec("P")
R = TypeVar("R")

#: Numeric suffix of an invoice (``FAC-000123`` -> ``123``).
_SUFIJO_FACTURA = re.compile(r"(\d+)\s*$")


def atomic_stock(
    reason: str = "",
    validate_stock: bool = True,
) -> Callable[[Callable[..., R]], Callable[..., R]]:
    def decorator(func: Callable[..., R]) -> Callable[P, R]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            with SessionManager() as managed_session:
                # A caller may pass its own session. Reuse it instead of
                # failing on TypeError from the injected `session=session`.
                call_kwargs = dict(kwargs)
                provided = call_kwargs.pop("session", None)
                session: Session = (
                    provided if isinstance(provided, Session) else managed_session
                )
                result = func(*args, session=session, **call_kwargs)
                if validate_stock:
                    _check_negative_stock(session)
                session.commit()
                log.info(
                    "stock_transaction: reason=%s func=%s",
                    reason,
                    func.__name__,
                )
                return result

        return wrapper

    return decorator


def _check_negative_stock(session: Session) -> None:
    from opticamanager.models.product import Product

    for obj in list(session.dirty) + list(session.new):
        if isinstance(obj, Product) and obj.stock_quantity < 0:
            raise ValueError(
                f"Stock insuficiente para '{obj.name}' (stock: {obj.stock_quantity})"
            )


@atomic_stock(reason="Venta", validate_stock=True)
def registrar_venta(
    session: Session,
    *,
    customer_id: int,
    user_id: int,
    items: list[dict],
    discount: Decimal = Decimal("0"),
    status_id: int = 1,
    prescription_id: int | None = None,
    payment_method: str = "Efectivo",
    amount_received: Decimal | None = None,
    change_amount: Decimal | None = None,
    taxes: Decimal = Decimal("0"),
    payments: list[dict] | None = None,
) -> Sale:
    from opticamanager.models.inventory_log import InventoryLog
    from opticamanager.models.product import Product
    from opticamanager.models.sale import Sale
    from opticamanager.models.sale_detail import SaleDetail
    from opticamanager.models.sale_payment import SalePayment
    from opticamanager.models.sale_status import SaleStatus

    status = session.get(SaleStatus, status_id)
    if not status:
        raise ValueError(f"Estado de venta {status_id} no encontrado")

    # Derive the consecutive from the highest numeric suffix, not COUNT(Sale):
    # once a sale is deleted, COUNT+1 hands out a number that already exists and
    # collides with the unique index on `sales.invoice_number`, which surfaces
    # as an opaque IntegrityError. CAST(... AS INTEGER) is no help either:
    # SQLite casts 'FAC-000001' to 0.
    ultimo = 0
    for factura in session.exec(select(Sale.invoice_number)).all():
        coincidencia = _SUFIJO_FACTURA.search(factura or "")
        if coincidencia:
            ultimo = max(ultimo, int(coincidencia.group(1)))
    invoice_number = f"FAC-{ultimo + 1:06d}"

    details: list[SaleDetail] = []
    total = Decimal("0")

    for item in items:
        product = session.get(Product, item["product_id"])
        if not product:
            raise ValueError(f"Producto ID {item['product_id']} no encontrado")
        if not product.active:
            raise ValueError(f"'{product.name}' no está activo")
        if product.stock_quantity < item["quantity"]:
            raise ValueError(
                f"Stock insuficiente para '{product.name}': "
                f"tiene {product.stock_quantity}, requiere {item['quantity']}"
            )

        unit_price = Decimal(str(item["unit_price"]))
        qty = int(item["quantity"])
        subtotal = unit_price * qty
        total += subtotal

        assert product.id is not None
        product.stock_quantity -= qty

        detail = SaleDetail(  # type: ignore[reportCallIssue]
            quantity=qty,
            unit_price=unit_price,
            subtotal=subtotal,
            product_id=product.id,
        )
        details.append(detail)

        log_entry = InventoryLog(
            product_id=product.id,
            quantity=-qty,
            unit_cost=product.cost_price_usd,
            reason="Venta",
            user_id=user_id,
        )
        session.add(log_entry)

    subtotal = total
    grand_total = total + taxes - discount
    if grand_total < 0:
        raise ValueError(
            f"El total no puede ser negativo (subtotal={subtotal}, "
            f"impuestos={taxes}, descuento={discount})"
        )

    if payments:
        paid_bs = sum(
            (Decimal(str(p.get("amount_bs", 0))) for p in payments),
            Decimal("0"),
        )
        if abs(paid_bs - grand_total) > Decimal("0.01"):
            raise ValueError(
                f"Los pagos suman {paid_bs} pero el total de la venta es {grand_total}"
            )

    sale = Sale(
        invoice_number=invoice_number,
        customer_id=customer_id,
        user_id=user_id,
        status_id=status_id,
        prescription_id=prescription_id,
        payment_method=payment_method,
        amount_received=amount_received,
        change_amount=change_amount,
        subtotal=subtotal,
        taxes=taxes,
        discount=discount,
        total=grand_total,
        details=details,
    )
    session.add(sale)
    session.flush()

    # ── Payment breakdown (mixed payments / currency tracking) ──
    if payments:
        payment_rows: list[SalePayment] = []
        for p in payments:
            assert sale.id is not None
            payment_rows.append(
                SalePayment(  # type: ignore[reportCallIssue]
                    sale_id=sale.id,
                    method=p["method"],
                    currency=p["currency"],
                    amount=Decimal(str(p["amount"])),
                    amount_bs=Decimal(str(p["amount_bs"])),
                    rate_used=(
                        Decimal(str(p["rate_used"]))
                        if p.get("rate_used") is not None
                        else None
                    ),
                )
            )
        session.add_all(payment_rows)
        log.info(
            "pagos_registrados: factura=%s metodos=%d",
            invoice_number,
            len(payment_rows),
        )

    log.info(
        "venta_creada: factura=%s items=%d total=%.2f",
        invoice_number,
        len(items),
        grand_total,
    )
    return sale


@require_role("Admin")
@atomic_stock(reason="Rembolso", validate_stock=False)
def reembolsar_venta(
    session: Session,
    *,
    sale_id: int,
    user_id: int,
) -> Sale:
    """Refund a whole sale: return its stock and mark the sale Rembolsada.

    Admin only. ``@require_role("Admin")`` raises ``PermissionError`` when the
    active session lacks that role. The decorator sits outside
    ``@atomic_stock`` so authorization runs before the transaction opens and
    before the success log is written. Stock only grows here, which is why
    ``validate_stock`` is ``False``. Recorded payments stay behind as history.
    """
    from opticamanager.models.inventory_log import InventoryLog
    from opticamanager.models.product import Product
    from opticamanager.models.sale import Sale
    from opticamanager.models.sale_detail import SaleDetail
    from opticamanager.models.sale_status import SaleStatus

    sale = session.get(Sale, sale_id)
    if not sale:
        raise ValueError(f"Venta ID {sale_id} no encontrada")

    refunded = session.exec(
        select(SaleStatus).where(SaleStatus.name == "Rembolsada")
    ).first()
    if not refunded:
        raise ValueError("Estado de venta 'Rembolsada' no encontrado")
    cancelled = session.exec(
        select(SaleStatus).where(SaleStatus.name == "Cancelada")
    ).first()

    if sale.status_id == refunded.id:
        raise ValueError(f"La venta '{sale.invoice_number}' ya fue rembolsada")
    if cancelled is not None and sale.status_id == cancelled.id:
        raise ValueError(f"La venta '{sale.invoice_number}' está cancelada")

    details: list[SaleDetail] = sale.details  # type: ignore[assignment]
    for detail in details:
        product = session.get(Product, detail.product_id)
        if not product:
            raise ValueError(f"Producto ID {detail.product_id} no encontrado")

        assert product.id is not None
        product.stock_quantity += detail.quantity

        log_entry = InventoryLog(
            product_id=product.id,
            quantity=detail.quantity,
            unit_cost=product.cost_price_usd,
            reason="Rembolso",
            user_id=user_id,
        )
        session.add(log_entry)

    assert refunded.id is not None
    sale.status_id = refunded.id
    log.info(
        "venta_rembolsada: factura=%s items=%d total=%.2f",
        sale.invoice_number,
        len(details),
        sale.total,
    )
    return sale


@atomic_stock(reason="Compra", validate_stock=True)
def registrar_compra(
    session: Session,
    *,
    product_id: int,
    quantity: int,
    unit_cost: Decimal,
    user_id: int,
) -> Product:
    from opticamanager.models.inventory_log import InventoryLog
    from opticamanager.models.product import Product

    product = session.get(Product, product_id)
    if not product:
        raise ValueError(f"Producto ID {product_id} no encontrado")
    if quantity <= 0:
        raise ValueError("La cantidad debe ser positiva")

    assert product.id is not None
    product.stock_quantity += quantity

    log_entry = InventoryLog(
        product_id=product.id,
        quantity=quantity,
        unit_cost=unit_cost,
        reason="Compra",
        user_id=user_id,
    )
    session.add(log_entry)
    session.flush()

    log.info(
        "compra_registrada: producto=%s cantidad=%d costo=%.2f",
        product.name,
        quantity,
        unit_cost,
    )
    return product


@atomic_stock(reason="Ajuste de inventario", validate_stock=True)
def ajustar_stock(
    session: Session,
    *,
    product_id: int,
    quantity: int,
    reason: str,
    user_id: int,
    unit_cost: Decimal | None = None,
) -> Product:
    from opticamanager.models.inventory_log import InventoryLog
    from opticamanager.models.product import Product

    product = session.get(Product, product_id)
    if not product:
        raise ValueError(f"Producto ID {product_id} no encontrado")

    assert product.id is not None
    product.stock_quantity += quantity

    log_entry = InventoryLog(
        product_id=product.id,
        quantity=quantity,
        unit_cost=unit_cost,
        reason=reason,
        user_id=user_id,
    )
    session.add(log_entry)
    session.flush()

    log.info(
        "stock_ajustado: producto=%s delta=%+d razon=%s",
        product.name,
        quantity,
        reason,
    )
    return product


__all__ = [
    "atomic_stock",
    "registrar_venta",
    "registrar_compra",
    "ajustar_stock",
    "reembolsar_venta",
]
