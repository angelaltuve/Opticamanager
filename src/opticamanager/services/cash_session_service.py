"""Cash session management: open, close, and reconcile."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlmodel import func, select

from opticamanager.db import SessionManager

if TYPE_CHECKING:
    from opticamanager.models.cash_session import CashSession
    from opticamanager.models.sale import Sale

# Sale statuses that must not count towards a cash reconciliation.
ESTADOS_EXCLUIDOS_DE_CAJA: tuple[str, ...] = ("Cancelada", "Rembolsada")


def _ids_de_estados_excluidos() -> tuple[int, ...]:
    """Resolve the excluded sale-status IDs by name.

    Looking the IDs up by name avoids the silent reconciliation corruption that
    hardcoded integers caused when the seed order changed.
    """
    from opticamanager.models.sale_status import SaleStatus

    with SessionManager() as session:
        ids = session.exec(
            select(SaleStatus.id).where(SaleStatus.name.in_(ESTADOS_EXCLUIDOS_DE_CAJA))
        ).all()
    return tuple(i for i in ids if i is not None)


def open_session(user_id: int, initial_balance: Decimal) -> CashSession:
    """Open a new cash session for the given user.

    Any stale open sessions for the same user are force-closed first, with their
    final balance reconciled from the sales recorded in the session window.
    """
    from opticamanager.models.cash_session import CashSession

    with SessionManager() as session:
        now = datetime.now()

        # Close any existing open sessions for this user
        existing = session.exec(
            select(CashSession).where(
                CashSession.user_id == user_id,
                CashSession.closed_at.is_(None),  # type: ignore[reportAttributeAccessIssue]
            )
        ).all()
        for s in existing:
            s.closed_at = now
            # A forced close must still carry a final balance, otherwise the
            # reconciliation is left with an unusable NULL.
            s.final_balance = _saldo_esperado(s, session)

        cs = CashSession(
            user_id=user_id,
            initial_balance=initial_balance,
            opened_at=now,
        )
        session.add(cs)
        session.commit()
        session.refresh(cs)
        return cs


def _saldo_esperado(cs: CashSession, session) -> Decimal:  # noqa: ANN001
    """Initial balance plus the payments recorded inside the session window."""
    from opticamanager.models.sale_payment import SalePayment
    from opticamanager.models.sale import Sale

    ids = _ids_de_estados_excluidos()
    stmt = select(Sale).where(
        Sale.user_id == cs.user_id,
        Sale.created_at >= cs.opened_at,
    )
    if ids:
        stmt = stmt.where(Sale.status_id.notin_(ids))
    if cs.closed_at is not None:
        stmt = stmt.where(Sale.created_at <= cs.closed_at)
    sales = session.exec(stmt).all()
    if not sales:
        return cs.initial_balance

    sale_ids = [s.id for s in sales if s.id is not None]
    total_pagado = session.exec(
        select(func.coalesce(func.sum(SalePayment.amount_bs), 0)).where(
            SalePayment.sale_id.in_(sale_ids)
        )
    ).one()

    pagado = Decimal(str(total_pagado))
    if pagado == 0:
        # No payment rows: fall back to the recorded sale totals.
        pagado = sum((s.total for s in sales), Decimal("0"))
    return cs.initial_balance + pagado


def close_session(cs_id: int, final_balance: Decimal) -> CashSession:
    """Close a cash session with the given counted balance."""
    from opticamanager.models.cash_session import CashSession

    with SessionManager() as session:
        cs = session.get(CashSession, cs_id)
        if not cs:
            raise ValueError(f"CashSession {cs_id} not found")
        if cs.closed_at is not None:
            raise ValueError("La sesión de caja ya está cerrada")
        cs.closed_at = datetime.now()
        cs.final_balance = final_balance
        session.add(cs)
        session.commit()
        session.refresh(cs)
        return cs


def get_active_session(user_id: int) -> CashSession | None:
    """Return the currently open cash session for a user, if any."""
    from opticamanager.models.cash_session import CashSession

    with SessionManager() as session:
        return session.exec(
            select(CashSession).where(
                CashSession.user_id == user_id,
                CashSession.closed_at.is_(None),  # type: ignore[reportAttributeAccessIssue]
            )
        ).first()


def _get_session_sales_raw(cs: CashSession) -> list[Sale]:
    """Return all sales belonging to this cash session.

    Sales are matched by user_id and created_at within the session's
    open → close time window. Cancelled and refunded sales are excluded by
    resolving their status IDs by name.
    """
    from opticamanager.models.sale import Sale

    with SessionManager() as session:
        stmt = select(Sale).where(
            Sale.user_id == cs.user_id,
            Sale.created_at >= cs.opened_at,
        )
        excluded = _ids_de_estados_excluidos()
        if excluded:
            stmt = stmt.where(Sale.status_id.notin_(excluded))
        if cs.closed_at is not None:
            stmt = stmt.where(Sale.created_at <= cs.closed_at)

        return list(session.exec(stmt.order_by(Sale.created_at)).all())


def get_session_summary(cs: CashSession) -> dict:
    """Build a summary dict for a cash session."""
    from opticamanager.models.sale_payment import SalePayment

    sales = _get_session_sales_raw(cs)

    total_sales = Decimal("0")
    by_method: dict[str, Decimal] = {}

    # One grouped query for the whole window instead of one per sale.
    sale_ids = [s.id for s in sales if s.id is not None]
    paid_by_sale: dict[int, Decimal] = {}
    if sale_ids:
        with SessionManager() as session:
            rows = session.execute(
                select(
                    SalePayment.sale_id,
                    SalePayment.method,
                    func.coalesce(func.sum(SalePayment.amount_bs), 0).label("total"),
                )
                .where(SalePayment.sale_id.in_(sale_ids))
                .group_by(SalePayment.sale_id, SalePayment.method)
            ).all()
        for sale_id, method, total in rows:
            amount = Decimal(str(total))
            paid_by_sale[sale_id] = paid_by_sale.get(sale_id, Decimal("0")) + amount
            by_method[method] = by_method.get(method, Decimal("0")) + amount

    for s in sales:
        sale_paid = (
            paid_by_sale.get(s.id, Decimal("0")) if s.id is not None else Decimal("0")
        )
        if sale_paid == 0:
            # No payment rows (legacy sale), count the full total.
            total_sales += s.total
            by_method[s.payment_method] = (
                by_method.get(s.payment_method, Decimal("0")) + s.total
            )
        else:
            total_sales += sale_paid

    expected = cs.initial_balance + total_sales

    return {
        "sales_count": len(sales),
        "total_sales": total_sales,
        "by_method": by_method,
        "expected_balance": expected,
        "sales": sales,
    }
