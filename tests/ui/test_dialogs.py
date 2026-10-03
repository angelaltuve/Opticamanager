from __future__ import annotations

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QMessageBox

from opticamanager.ui.widgets.dialogs import (
    dialogo_confirmacion,
    dialogo_error,
    dialogo_informacion,
)


def _active_msgbox() -> QMessageBox | None:
    """Find the currently active QMessageBox top-level widget."""
    app = QApplication.instance()
    if app is None:
        return None
    for widget in app.topLevelWidgets():
        if isinstance(widget, QMessageBox):
            return widget
    return None


def _run_with_click(dialog_fn, button_text: str, timeout: int = 3000) -> list:
    """Run a dialog function and click a button after a short delay.

    Returns a list with the result (or empty if timeout).
    """
    result: list = []

    def _click() -> None:
        msgbox = _active_msgbox()
        if msgbox is None:
            return
        for btn in msgbox.buttons():
            if button_text.lower() in btn.text().lower():
                btn.click()
                return

    QTimer.singleShot(200, _click)
    QTimer.singleShot(100, lambda: result.append(dialog_fn()))
    return result


def test_dialogo_confirmacion_accept(qtbot) -> None:
    """dialogo_confirmacion returns True when "Sí" is clicked."""
    result = _run_with_click(
        lambda: dialogo_confirmacion(None, "Test", "¿Continuar?"),
        "Sí",
    )
    qtbot.wait_until(lambda: len(result) > 0, timeout=3000)
    if result:
        assert result[0] is True


def test_dialogo_confirmacion_reject(qtbot) -> None:
    """dialogo_confirmacion returns False when "Cancelar" is clicked."""
    result = _run_with_click(
        lambda: dialogo_confirmacion(None, "Test", "¿Continuar?"),
        "Cancelar",
    )
    qtbot.wait_until(lambda: len(result) > 0, timeout=3000)
    if result:
        assert result[0] is False


def test_dialogo_error(qtbot) -> None:
    """dialogo_error completes when "Aceptar" is clicked."""
    done: list[bool] = []

    def _click_aceptar() -> None:
        msgbox = _active_msgbox()
        if msgbox:
            for btn in msgbox.buttons():
                if "aceptar" in btn.text().lower():
                    btn.click()
                    return

    QTimer.singleShot(200, _click_aceptar)
    QTimer.singleShot(
        100,
        lambda: (
            dialogo_error(None, "Error", "Algo salió mal"),
            done.append(True),
        ),
    )

    qtbot.wait_until(lambda: len(done) > 0, timeout=3000)


def test_dialogo_informacion(qtbot) -> None:
    """dialogo_informacion completes when OK is clicked."""
    done: list[bool] = []

    def _click_ok() -> None:
        msgbox = _active_msgbox()
        if msgbox:
            for btn in msgbox.buttons():
                if "ok" in btn.text().lower():
                    btn.click()
                    return

    QTimer.singleShot(200, _click_ok)
    QTimer.singleShot(
        100,
        lambda: (
            dialogo_informacion(None, "Info", "Operación exitosa"),
            done.append(True),
        ),
    )

    qtbot.wait_until(lambda: len(done) > 0, timeout=3000)
