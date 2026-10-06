# Sistema de Gestión de Cobros de Alquiler
### Inmobiliaria Margherita S.A.

Aplicación web desarrollada con **Python + Flask + Bootstrap 5 + SQLite3**.

---

## Requisitos previos

- Python 3.10 o superior
- pip

---

## Instalación y primer uso

### 1. Instalar dependencias

```bash
cd "c:/SISTEMA IM/inmobiliaria"
pip install -r requirements.txt
```

Configura una clave secreta para las sesiones antes de iniciar la aplicación.
En PowerShell:

```powershell
$env:SECRET_KEY = py -c "import secrets; print(secrets.token_hex(32))"
```

En otros entornos, define `SECRET_KEY` como variable de entorno. Si no se define,
la aplicación genera una clave aleatoria al arrancar; las sesiones se invalidan
al reiniciar.

### 2. Cargar datos de prueba (opcional pero recomendado)

```bash
python seed.py
```

Esto crea la base de datos, las tablas y carga inquilinos, propiedades, contratos y pagos de ejemplo.

### 3. Iniciar el servidor

```bash
python app.py
```

Abrí el navegador en: **http://localhost:5000**

---

## Credenciales de acceso

Solo para la base de datos de demostración creada por `seed.py`; cámbialas antes
de usar la aplicación con datos reales.

| Rol | Usuario | Contraseña |
|-----|---------|------------|
| Administrador | `admin` | `admin123` |
| Operador de Cobranzas | `operador` | `oper123` |

---

## Estructura del proyecto

```
inmobiliaria/
├── app.py              # Aplicación Flask principal (rutas + lógica)
├── database.py         # Esquema SQLite e inicialización
├── seed.py             # Datos de prueba
├── requirements.txt
├── inmobiliaria.db     # Base de datos SQLite (se crea automáticamente)
├── static/
│   ├── css/style.css
│   └── js/main.js
└── templates/
    ├── base.html           # Layout con sidebar Bootstrap 5
    ├── login.html
    ├── dashboard.html
    ├── propiedades/        # lista.html, form.html
    ├── inquilinos/         # lista.html, form.html
    ├── contratos/          # lista.html, form.html, ver.html
    ├── cobranzas/          # lista.html, registrar.html
    ├── recibos/            # lista.html, ver.html, anular.html
    ├── reportes/           # index.html, recaudacion.html,
    │                       # morosidad.html, comprobantes.html,
    │                       # cuotas_vencidas.html
    └── usuarios/           # lista.html, form.html
```

---

## Módulos del sistema

| Módulo | Descripción |
|--------|-------------|
| **Dashboard** | Estadísticas en tiempo real: propiedades, inquilinos, recaudación del mes, mora |
| **Propiedades** | CRUD de inmuebles con cuenta corriente central, tipo y estado |
| **Inquilinos** | CRUD de clientes con co-titular (figura en recibos como Y/O) |
| **Contratos** | Registro de contratos con generación automática de cuotas mensuales |
| **Cobranzas** | Registro de pagos con validación de todas las reglas de negocio |
| **Recibos** | Visualización e impresión del recibo dúplex (recibo + talón) |
| **Reportes** | Recaudación, morosidad, comprobantes, cuotas vencidas y por vencer |
| **Usuarios** | Gestión de cuentas con roles Administrador / Operador |

---

## Reglas de negocio implementadas

| ID | Descripción |
|----|-------------|
| RN01 | Pago parcial mínimo del 50% del alquiler del mes |
| RN02 | Un recibo correlativo y una factura legal por cada pago |
| RN03 | Pagos múltiples y adelantados con imputación independiente por período |
| RN04 | Mora: saldo > 0 y fecha límite de pago vencida |
| RN05 | Recargo por mora calculado automáticamente según % del contrato |
| RN06 | Anulación de recibos sin alterar la correlatividad numérica |

---

## Roles y permisos

| Función | Administrador | Operador |
|---------|:---:|:---:|
| Ver todo | ✔ | ✔ |
| Registrar cobros / recibos | ✔ | ✔ |
| Anular recibos | ✔ | ✔ |
| Crear/editar propiedades, inquilinos, contratos | ✔ | ✗ |
| Gestionar usuarios | ✔ | ✗ |

---

## Base de datos (esquema resumido)

```
propiedades ──┐
              ├── contratos ── alquileres ── pagos ── recibos
inquilinos  ──┘
usuarios ──────────────────────────────── pagos
```

Catálogos: `tipos_propiedad`, `estados_propiedad`, `estados_alquiler`,
`medios_pago`, `tipos_pago`, `roles`.
