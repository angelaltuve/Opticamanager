from __future__ import annotations

from PyQt6.QtWidgets import QLineEdit

from opticamanager.ui.widgets.validators import (
    validador_cedula,
    validador_codigo_barras,
    validador_entero,
    validador_moneda,
    validador_telefono,
)


def _assert_validation(line_edit: QLineEdit, text: str, expected_valid: bool) -> None:
    """Helper function to test validation using qtbot."""
    line_edit.clear()
    line_edit.setText(text)
    assert line_edit.hasAcceptableInput() == expected_valid


class TestValidadorMoneda:
    """Tests for validador_moneda function."""

    def test_validador_moneda_valid_values(self, qtbot):
        """Test validador_moneda with valid values."""
        validator = validador_moneda()
        line_edit = QLineEdit()
        line_edit.setValidator(validator)
        qtbot.addWidget(line_edit)

        # Valid values
        valid_values = ["0.00", "100.50", "999999.99"]
        for value in valid_values:
            _assert_validation(line_edit, value, True)

    def test_validador_moneda_invalid_values(self, qtbot):
        """Test validador_moneda with invalid values."""
        validator = validador_moneda()
        line_edit = QLineEdit()
        line_edit.setValidator(validator)
        qtbot.addWidget(line_edit)

        # Invalid values
        invalid_values = [
            "-1.00",  # Negative
            "1000000.00",  # Above max
            "999999.999",  # Too many decimals
            "abc",  # Non-numeric
            "",  # Empty
        ]
        for value in invalid_values:
            _assert_validation(line_edit, value, False)


class TestValidadorEntero:
    """Tests for validador_entero function."""

    def test_validador_entero_valid_values(self, qtbot):
        """Test validador_entero with valid values."""
        validator = validador_entero()
        line_edit = QLineEdit()
        line_edit.setValidator(validator)
        qtbot.addWidget(line_edit)

        # Valid values
        valid_values = ["0", "123", "999999999"]
        for value in valid_values:
            _assert_validation(line_edit, value, True)

    def test_validador_entero_invalid_values(self, qtbot):
        """Test validador_entero with invalid values."""
        validator = validador_entero()
        line_edit = QLineEdit()
        line_edit.setValidator(validator)
        qtbot.addWidget(line_edit)

        # Invalid values
        invalid_values = [
            "-1",  # Negative
            "1000000000",  # Above max
            "abc",  # Non-numeric
            "",  # Empty
        ]
        for value in invalid_values:
            _assert_validation(line_edit, value, False)


class TestValidadorCedula:
    """Tests for validador_cedula function."""

    def test_validador_cedula_valid_values(self, qtbot):
        """Test validador_cedula with valid values."""
        validator = validador_cedula()
        line_edit = QLineEdit()
        line_edit.setValidator(validator)
        qtbot.addWidget(line_edit)

        # Valid values
        valid_values = [
            "V12345678",
            "E-87654321",
            "J1234567890",
            "v12345678",
            "e-87654321",
            "j1234567890",
            "P12345678",
            "p12345678",
        ]
        for value in valid_values:
            _assert_validation(line_edit, value, True)

    def test_validador_cedula_invalid_values(self, qtbot):
        """Test validador_cedula with invalid values."""
        validator = validador_cedula()
        line_edit = QLineEdit()
        line_edit.setValidator(validator)
        qtbot.addWidget(line_edit)

        # Invalid values
        invalid_values = [
            "ABC",  # Non-numeric
            "1234",  # Too short (4 digits)
            "12345678901234567890",  # Too long (20 digits)
            "V1",  # Too short (1 digit)
            "V123456789012345",  # Too long (15 digits)
            "V12345678A",  # Contains letter
            "",  # Empty
        ]
        for value in invalid_values:
            _assert_validation(line_edit, value, False)


class TestValidadorTelefono:
    """Tests for validador_telefono function."""

    def test_validador_telefono_valid_values(self, qtbot):
        """Test validador_telefono with valid values."""
        validator = validador_telefono()
        line_edit = QLineEdit()
        line_edit.setValidator(validator)
        qtbot.addWidget(line_edit)

        # Valid values
        valid_values = [
            "04121234567",
            "+584121234567",
            "123456789",
            "+1234567890",
            "9999999",
        ]
        for value in valid_values:
            _assert_validation(line_edit, value, True)

    def test_validador_telefono_invalid_values(self, qtbot):
        """Test validador_telefono with invalid values."""
        validator = validador_telefono()
        line_edit = QLineEdit()
        line_edit.setValidator(validator)
        qtbot.addWidget(line_edit)

        # Invalid values
        invalid_values = [
            "abc",  # Non-numeric
            "123",  # Too short (less than 7)
            "123456",  # Too short (less than 7)
            "12345678901234567890",  # Too long (more than 15)
            "++1234567",  # Double plus sign
            "+",  # Just plus sign
            "",  # Empty
        ]
        for value in invalid_values:
            _assert_validation(line_edit, value, False)


class TestValidadorCodigoBarras:
    """Tests for validador_codigo_barras function."""

    def test_validador_codigo_barras_valid_values(self, qtbot):
        """Test validador_codigo_barras with valid values."""
        validator = validador_codigo_barras()
        line_edit = QLineEdit()
        line_edit.setValidator(validator)
        qtbot.addWidget(line_edit)

        # Valid values
        valid_values = [
            "12345678",
            "1234567890123",
            "123456789012",
            "12345678901",
            "1234567890",
            "123456789",
        ]
        for value in valid_values:
            _assert_validation(line_edit, value, True)

    def test_validador_codigo_barras_invalid_values(self, qtbot):
        """Test validador_codigo_barras with invalid values."""
        validator = validador_codigo_barras()
        line_edit = QLineEdit()
        line_edit.setValidator(validator)
        qtbot.addWidget(line_edit)

        # Invalid values
        invalid_values = [
            "1234567",  # Too short (less than 8)
            "123456789012345",  # Too long (more than 13)
            "abc",  # Non-numeric
            "12345678A",  # Contains letter
            "",  # Empty
        ]
        for value in invalid_values:
            _assert_validation(line_edit, value, False)
