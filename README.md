# OpticaManager

Sistema de gestión para ópticas: inventario, punto de venta (POS), clientes, recetas, abonos, reportes y usuarios.

**Stack:** Python 3.14+ · PyQt6 · SQLModel · SQLite (WAL) · Alembic · bcrypt · pyvenezuela · openpyxl · PyQtGraph

## Características

- **POS:** carrito de ventas, IVA configurable, doble moneda (Bs/USD), tasa del BCV vía pyvenezuela con opción de tasa manual (solo en memoria), métodos de pago (Efectivo, Transferencia, Débito, Crédito, Mixto, Abono) y recibo en PDF.
- **Inventario:** control atómico de stock (`@atomic_stock`), alertas de stock crítico y registro de movimientos en `inventory_log`.
- **Clientes, proveedores, recetas (OD/OS), abonos y usuarios** con roles (Administrador/Vendedor).
- **Reportes y dashboard BI:** reportes en pantalla, exportación a Excel (openpyxl) y gráficas con PyQtGraph.
- **Caja:** apertura y cierre de sesión de caja (`cash_session`).
- **Ajustes:** IVA y parámetros generales configurables desde la UI (`AppSetting`).
- **Seguridad:** contraseñas con bcrypt (12 rondas), bloqueo de sesión tras 5 intentos fallidos durante 1 minuto, visibilidad por roles y redacción automática de datos sensibles en logs.

## Requisitos

- Python 3.14 o superior
- [`uv`](https://github.com/astral-sh/uv) (gestor de entornos y dependencias)
- 512 MB RAM (aprox.)
- 200 MB de espacio en disco (aprox.)

## Instalación y ejecución

```bash
uv sync                        # Instalar dependencias (incluye dev)
uv run alembic upgrade head    # Crear o actualizar la base de datos
uv run python -m opticamanager # Ejecutar la aplicación
```

Al primer inicio se solicitará registrar al usuario administrador.

## Base de datos y migraciones

- Base de datos: `data/opticamanager.db` (ignorada por Git). Se crea automáticamente.
- Migraciones: gestionadas con Alembic (`render_as_batch=True` por restricción de SQLite).
- Copia de seguridad: `scripts/backup_db.py` (conserva 30 copias por defecto en `backups/`).

## Pruebas

```bash
uv run pytest                                              # Ejecutar todas las pruebas
uv run pytest --cov=src/opticamanager --html=report.html  # Cobertura + informe HTML (~90 %)
```

Las pruebas de integración usan una base de datos temporal aislada en `data/_test/pid-<PID>/`, nunca la base de datos de producción.

### Ejecución sin interfaz gráfica (CI/headless)

```bash
QT_QPA_PLATFORM=offscreen env -u QT_QPA_PLATFORMTHEME uv run pytest
```

En algunos entornos con `QT_QPA_PLATFORMTHEME=gtk3` exportado, crear un `QApplication` en modo headless puede fallar. Eliminar esa variable temporalmente (`env -u QT_QPA_PLATFORMTHEME`) evita ese problema.

## Estructura del proyecto

```
src/opticamanager/
├── __main__.py          # Entrypoint: QApplication → RegisterWindow/LoginWindow
├── core/                # Transversales: logging, bcrypt, sesión de usuario
├── db/                  # Engine SQLite WAL, SessionManager
├── models/              # 15 entidades SQLModel (heredan AuditBase)
├── services/            # Lógica de negocio (stock, PDF, Excel, caja, ajustes…)
├── ui/                  # PyQt6: login, registro, ventana principal, 11 vistas, widgets
├── resources/           # Estilos Qt (styles.qss) y recursos Breeze
└── utils/               # Logger y formateadores Bs/USD

migrations/              # 4 migraciones Alembic (render_as_batch=True)
tests/                   # Pruebas (cobertura ~90 %; BD aislada por proceso)
```

## Empaquetado

```bash
uv run pyinstaller OpticaManager.spec  # Genera dist/OpticaManager (binario ELF)
```
