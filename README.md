# SISTEMA-IM

Sistema web de gestión de alquileres y cobros, desarrollado con Flask y SQLite.

## Ejecutar localmente

```powershell
cd inmobiliaria
py -m pip install -r requirements.txt
$env:SECRET_KEY = py -c "import secrets; print(secrets.token_hex(32))"
py app.py
```

Luego abre <http://localhost:5000>. Para instrucciones, módulos y credenciales de
demostración, consulta [inmobiliaria/README.md](inmobiliaria/README.md).

La base SQLite local no se versiona: puede contener información personal y
operativa. Ejecuta `py seed.py` dentro de `inmobiliaria` solo si quieres cargar
datos de demostración.
# SISTEMA-IM
