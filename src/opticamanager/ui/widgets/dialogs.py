from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMessageBox, QWidget


def dialogo_confirmacion(
    parent: QWidget | None,
    titulo: str,
    mensaje: str,
    detalle: str | None = None,
    rich_text: bool = False,
) -> bool:
    caja = QMessageBox(parent)
    caja.setWindowTitle(titulo)
    caja.setText(mensaje)
    if rich_text:
        caja.setTextFormat(Qt.TextFormat.RichText)
    caja.setIcon(QMessageBox.Icon.Question)
    caja.setStandardButtons(
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
    )
    caja.setDefaultButton(QMessageBox.StandardButton.No)
    caja.button(QMessageBox.StandardButton.Yes).setText("Sí")
    caja.button(QMessageBox.StandardButton.No).setText("Cancelar")
    if detalle:
        caja.setDetailedText(detalle)
    return caja.exec() == QMessageBox.StandardButton.Yes


def dialogo_error(
    parent: QWidget | None,
    titulo: str,
    mensaje: str,
    detalle: str | None = None,
) -> None:
    caja = QMessageBox(parent)
    caja.setWindowTitle(titulo)
    caja.setText(mensaje)
    caja.setIcon(QMessageBox.Icon.Warning)
    caja.setStandardButtons(QMessageBox.StandardButton.Ok)
    caja.button(QMessageBox.StandardButton.Ok).setText("Aceptar")
    if detalle:
        caja.setDetailedText(detalle)
    caja.exec()


def dialogo_informacion(
    parent: QWidget | None,
    titulo: str,
    mensaje: str,
) -> None:
    QMessageBox.information(parent, titulo, mensaje)
