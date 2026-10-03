from __future__ import annotations

from PyQt6.QtCore import QRegularExpression
from PyQt6.QtGui import QDoubleValidator, QIntValidator, QRegularExpressionValidator


def validador_moneda() -> QDoubleValidator:
    v = QDoubleValidator()
    v.setNotation(QDoubleValidator.Notation.StandardNotation)
    v.setRange(0.0, 999999.99, decimals=2)
    return v


def validador_entero() -> QIntValidator:
    v = QIntValidator()
    v.setRange(0, 999999999)
    return v


def validador_cedula() -> QRegularExpressionValidator:
    pattern = QRegularExpression(r"^[VEJPGvejpg]?-?\d{5,10}$")
    return QRegularExpressionValidator(pattern)


def validador_telefono() -> QRegularExpressionValidator:
    pattern = QRegularExpression(r"^\+?\d{7,15}$")
    return QRegularExpressionValidator(pattern)


def validador_codigo_barras() -> QRegularExpressionValidator:
    pattern = QRegularExpression(r"^\d{8,13}$")
    return QRegularExpressionValidator(pattern)
