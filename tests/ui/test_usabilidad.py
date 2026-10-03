"""Usability tests: keyboard focus order and tooltips.

They cover usability criteria the per-view tests leave out:
1. Logical tab order in the auth windows (LoginWindow, RegisterWindow): focus
   must walk the fields in their natural order.
2. Explanatory tooltips on controls with an icon or non-obvious behaviour.

Note: destructive action confirmations already have coverage in the per-view
tests (test_usuarios_view, test_inventario_view, ...), and the Spanish
placeholders and messages live in the existing validation tests.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QWidget

from opticamanager.ui.login_window import LoginWindow
from opticamanager.ui.register_window import RegisterWindow

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


# ── Helpers ──────────────────────────────────────────────────────────────


def _accepts_tab_focus(widget: QWidget) -> bool:
    return widget.focusPolicy() != Qt.FocusPolicy.NoFocus


def _tab_chain(first: QWidget) -> list[QWidget]:
    """Walk the focus chain starting at *first* until it wraps around.

    Returns only the widgets that accept tab focus, in tab order.
    """
    chain: list[QWidget] = []
    current = first
    for _ in range(50):  # safety bound against a malformed chain
        if _accepts_tab_focus(current):
            chain.append(current)
        current = current.nextInFocusChain()
        if current is first:
            break
    return chain


# ── LoginWindow ──────────────────────────────────────────────────────────


class TestUsabilidadLoginTabOrder:
    """Tab must walk: "Usuario" → "Contraseña" → "Ingresar"."""

    def test_cadena_de_foco_sigue_orden_logico(self, qtbot: QtBot) -> None:
        window = LoginWindow()
        qtbot.addWidget(window)

        chain = _tab_chain(window._username_input)

        assert chain[0] is window._username_input
        assert chain[1] is window._password_input
        assert chain[2] is window._login_btn

    def test_tecla_tab_mueve_el_foco(self, qtbot: QtBot) -> None:
        window = LoginWindow()
        qtbot.addWidget(window)
        window.show()
        # Offscreen does not activate the window on its own; activate it so
        # local focus (hasFocus) responds to the Tab key.
        QApplication.setActiveWindow(window)

        window._username_input.setFocus(Qt.FocusReason.TabFocusReason)
        qtbot.keyClick(window._username_input, Qt.Key.Key_Tab)
        assert window._password_input.hasFocus()

        qtbot.keyClick(window._password_input, Qt.Key.Key_Tab)
        assert window._login_btn.hasFocus()


# ── RegisterWindow ───────────────────────────────────────────────────────


class TestUsabilidadRegisterTabOrder:
    """Tab must walk: "Usuario" → "Nombre" → "Email" → "Contraseña" →
    "Confirmar" → "Registrar"."""

    def test_cadena_de_foco_sigue_orden_logico(self, qtbot: QtBot) -> None:
        window = RegisterWindow()
        qtbot.addWidget(window)

        chain = _tab_chain(window._username_input)
        expected = [
            window._username_input,
            window._name_input,
            window._email_input,
            window._password_input,
            window._confirm_input,
        ]

        for i, widget in enumerate(expected):
            assert chain[i] is widget, (
                f"posición {i}: cadena de foco incorrecta "
                f"({len(chain)} widgets con foco)"
            )
        # The Registrar button precedes the demo checkbox in the chain (creation
        # order), and both come before the wrapper.
        assert window._register_btn in chain[:7]

    def test_tecla_tab_mueve_el_foco(self, qtbot: QtBot) -> None:
        window = RegisterWindow()
        qtbot.addWidget(window)
        window.show()
        QApplication.setActiveWindow(window)

        window._username_input.setFocus(Qt.FocusReason.TabFocusReason)
        qtbot.keyClick(window._username_input, Qt.Key.Key_Tab)
        assert window._name_input.hasFocus()

        qtbot.keyClick(window._name_input, Qt.Key.Key_Tab)
        assert window._email_input.hasFocus()


# ── Tooltips ─────────────────────────────────────────────────────────────


class TestUsabilidadTooltips:
    """Controls with an icon or special behaviour explain what they do."""

    def test_login_password_no_revela_longitud(self, qtbot: QtBot) -> None:
        # Privacy: typing into the password field must stay hidden.
        window = LoginWindow()
        qtbot.addWidget(window)
        assert window._password_input.echoMode().name == "Password"

    def test_register_demo_checkbox_explica_datos(self, qtbot: QtBot) -> None:
        window = RegisterWindow()
        qtbot.addWidget(window)
        tip = window._demo_checkbox.toolTip()
        assert "vendedor" in tip.lower()
        assert "ventas" in tip.lower()

    # ── (POS and inventory views: tooltips in tests/ui/views/test_pos_view.py and


# ──  test_inventario_view.py, which already hold the build helpers)
