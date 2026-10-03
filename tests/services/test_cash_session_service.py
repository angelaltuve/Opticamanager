"""Tests for cash_session_service (open/close/reconcile).

Covers the reconciliation rules that were previously hardcoded or left NULL:
statuses excluded by name, final balance on a forced close, and the single
grouped payment query.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Generator

import pytest
from sqlmodel import select

from opticamanager.db.database import SessionManager
from opticamanager.models import Customer, Sale, SalePayment, SaleStatus
from opticamanager.services import cash_session_service

# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _sem_estados_duplicados() -> Generator[None, None, None]:
    """Ensure the four canonical statuses exist with stable names."""
    with SessionManager() as session:
        for sid, name in (
            (1, "Completada"),
            (2, "Pendiente"),
            (3, "Cancelada"),
            (4, "Rembolsada"),
        ):
            existing = session.exec(
                select(SaleStatus).where(SaleStatus.id == sid)  # type: ignore[reportAttributeAccessIssue]
            ).first()
            if existing is None:
                session.add(SaleStatus(id=sid, name=name))
            else:
                existing.name = name
        session.commit()
    yield


@pytest.fixture()
def usuario() -> int:
    """A real user id: cash sessions and sales have non-null FKs to users.

    Username/email are unique per test so repeated fixtures do not collide.
    """
    import uuid

    from opticamanager.core.security import hash_password
    from opticamanager.models import Role, User

    sufijo = uuid.uuid4().hex[:8]
    with SessionManager() as session:
        role = session.exec(select(Role).where(Role.name == "Admin")).first()
        if role is None:
            role = Role(name="Admin")
            session.add(role)
            session.commit()
            session.refresh(role)
        user = User(
            username=f"caja_{sufijo}",
            name="Caja Test",
            email=f"caja_{sufijo}@test.local",
            password=hash_password("CajaTest#2026"),
            role_id=role.id,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user.id  # type: ignore[return-value]


def _crear_cliente(nombre: str) -> int:
    import uuid

    with SessionManager() as session:
        cliente = Customer(
            name=nombre,
            id_document=f"V-{uuid.uuid4().int % 90_000_000 + 10_000_000}",
        )
        session.add(cliente)
        session.commit()
        session.refresh(cliente)
        return cliente.id  # type: ignore[return-value]


def _crear_venta(
    user_id: int,
    status_id: int,
    total: Decimal,
    cuando: datetime | None = None,
    pago: Decimal | None = None,
    metodo: str = "Efectivo Bs",
) -> Sale:
    """Create a sale plus its payment row (unless pago is None).

    ``cuando`` defaults to the current instant, which is what an in-window sale
    needs; pass an explicit timestamp to place the sale outside the window.
    """
    import uuid

    with SessionManager() as session:
        sale = Sale(
            user_id=user_id,
            customer_id=_crear_cliente(f"Cliente {user_id}"),
            status_id=status_id,
            invoice_number=f"TST-{uuid.uuid4().hex[:12]}",
            subtotal=total,
            taxes=Decimal("0"),
            discount=Decimal("0"),
            total=total,
            amount_received=pago,
            change_amount=Decimal("0") if pago is not None else None,
            payment_method=metodo,
        )
        if cuando is not None:
            sale.created_at = cuando
        session.add(sale)
        session.commit()
        session.refresh(sale)
        sale_id = sale.id
        if pago is not None:
            session.add(
                SalePayment(
                    sale_id=sale_id,  # type: ignore[arg-type]
                    method=metodo,
                    currency="Bs",
                    amount=pago,
                    amount_bs=pago,
                    rate_used=Decimal("1"),
                )
            )
            session.commit()
    return sale


# ── Excluded statuses resolved by name ────────────────────────────


class TestEstadosExcluidos:
    def test_resuelve_ids_por_nombre(self) -> None:
        ids = cash_session_service._ids_de_estados_excluidos()
        assert set(ids) == {3, 4}

    def test_sin_estados_excluidos_no_falla(self, mocker) -> None:
        """A missing status table must not break reconciliation."""
        mocker.patch(
            "opticamanager.services.cash_session_service._ids_de_estados_excluidos",
            return_value=(),
        )
        cs = mocker.MagicMock()
        cs.user_id = 1
        cs.opened_at = datetime.now() - timedelta(hours=1)
        cs.closed_at = None
        cs.initial_balance = Decimal("0")
        mocker.patch.object(
            cash_session_service, "_get_session_sales_raw", side_effect=lambda c: []
        )
        assert cash_session_service.get_session_summary(cs)["sales_count"] == 0


# ── Forced close carries a final balance ──────────────────────────


class TestCierreForzado:
    def test_cierre_forzado_registra_final_balance(self, usuario) -> None:
        """A stale session is closed with a reconciled balance, not NULL."""
        user_id = usuario

        cs = cash_session_service.open_session(user_id, Decimal("100.00"))
        _crear_venta(user_id, 1, Decimal("50.00"), pago=Decimal("50.00"))
        # Reopening force-closes the previous session.
        nuevo = cash_session_service.open_session(user_id, Decimal("10.00"))

        with SessionManager() as session:
            cerrado = session.get(type(cs), cs.id)
            assert cerrado is not None
            assert cerrado.closed_at is not None
            assert cerrado.final_balance == Decimal("150.00")
            assert nuevo.id != cs.id

    def test_cierre_forzado_sin_ventas_usa_saldo_inicial(self, usuario) -> None:
        user_id = usuario
        cs = cash_session_service.open_session(user_id, Decimal("75.00"))
        cash_session_service.open_session(user_id, Decimal("10.00"))

        with SessionManager() as session:
            cerrado = session.get(type(cs), cs.id)
            assert cerrado is not None
            assert cerrado.final_balance == Decimal("75.00")

    def test_cierre_forzado_ignora_venta_cancelada(self, usuario) -> None:
        user_id = usuario
        cs = cash_session_service.open_session(user_id, Decimal("20.00"))
        _crear_venta(user_id, 3, Decimal("999.00"), pago=Decimal("999.00"))
        cash_session_service.open_session(user_id, Decimal("10.00"))

        with SessionManager() as session:
            cerrado = session.get(type(cs), cs.id)
            assert cerrado is not None
            assert cerrado.final_balance == Decimal("20.00")


# ── Summary uses one grouped query ─────────────────────────────────


class TestResumen:
    def test_resumen_suma_pagos_por_metodo(self, usuario) -> None:
        user_id = usuario
        cs = cash_session_service.open_session(user_id, Decimal("0.00"))
        _crear_venta(user_id, 1, Decimal("100.00"), pago=Decimal("100.00"))
        _crear_venta(user_id, 1, Decimal("50.00"), pago=Decimal("50.00"))

        with SessionManager() as session:
            abierto = session.get(type(cs), cs.id)
            assert abierto is not None
            resumen = cash_session_service.get_session_summary(abierto)

        assert resumen["sales_count"] == 2
        assert resumen["total_sales"] == Decimal("150.00")
        assert resumen["by_method"]["Efectivo Bs"] == Decimal("150.00")
        assert resumen["expected_balance"] == Decimal("150.00")

    def test_resumen_ignora_canceladas_y_rembolsadas(self, usuario) -> None:
        user_id = usuario
        cs = cash_session_service.open_session(user_id, Decimal("0.00"))
        _crear_venta(user_id, 1, Decimal("100.00"), pago=Decimal("100.00"))
        _crear_venta(user_id, 3, Decimal("500.00"), pago=Decimal("500.00"))
        _crear_venta(user_id, 4, Decimal("700.00"), pago=Decimal("700.00"))

        with SessionManager() as session:
            abierto = session.get(type(cs), cs.id)
            assert abierto is not None
            resumen = cash_session_service.get_session_summary(abierto)

        assert resumen["sales_count"] == 1
        assert resumen["total_sales"] == Decimal("100.00")

    def test_venta_sin_pagos_usa_total_registrado(self, usuario) -> None:
        """Legacy sales without payment rows still count by their total."""
        user_id = usuario
        cs = cash_session_service.open_session(user_id, Decimal("0.00"))
        _crear_venta(user_id, 1, Decimal("42.00"), pago=None, metodo="Transferencia")

        with SessionManager() as session:
            abierto = session.get(type(cs), cs.id)
            assert abierto is not None
            resumen = cash_session_service.get_session_summary(abierto)

        assert resumen["total_sales"] == Decimal("42.00")
        assert resumen["by_method"]["Transferencia"] == Decimal("42.00")

    def test_venta_fuera_de_la_ventana_no_cuenta(self, usuario) -> None:
        user_id = usuario
        cs = cash_session_service.open_session(user_id, Decimal("0.00"))
        # Sale recorded two hours before the session was opened.
        _crear_venta(
            user_id,
            1,
            Decimal("80.00"),
            datetime.now() - timedelta(hours=2),
            pago=Decimal("80.00"),
        )

        with SessionManager() as session:
            abierto = session.get(type(cs), cs.id)
            assert abierto is not None
            resumen = cash_session_service.get_session_summary(abierto)

        assert resumen["sales_count"] == 0
        assert resumen["total_sales"] == Decimal("0.00")
