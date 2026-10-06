"""
app.py - Aplicación principal Flask
Sistema de Gestión de Cobros de Alquiler - Inmobiliaria Margherita S.A.
"""

from flask import (Flask, render_template, request, redirect, url_for,
                   flash, session, g, jsonify)
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime, date, timedelta
import calendar
import os
import secrets
from database import get_db, init_db

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)

# ─── Helpers de formato ───────────────────────────────────────────────────────

def fmt_gs(value):
    """Formatea un número como moneda guaraní: Gs. 1.300.000"""
    try:
        return f"Gs. {int(value):,.0f}".replace(",", ".")
    except (TypeError, ValueError):
        return "Gs. 0"

app.jinja_env.filters["fmt_gs"] = fmt_gs


def numero_a_letras(n):
    """Convierte un entero (guaraníes) a texto en mayúsculas."""
    unidades = ["", "UN", "DOS", "TRES", "CUATRO", "CINCO", "SEIS",
                "SIETE", "OCHO", "NUEVE", "DIEZ", "ONCE", "DOCE", "TRECE",
                "CATORCE", "QUINCE", "DIECISÉIS", "DIECISIETE", "DIECIOCHO",
                "DIECINUEVE", "VEINTE"]
    decenas = ["", "", "VEINTI", "TREINTA", "CUARENTA", "CINCUENTA",
               "SESENTA", "SETENTA", "OCHENTA", "NOVENTA"]
    centenas = ["", "CIEN", "DOSCIENTOS", "TRESCIENTOS", "CUATROCIENTOS",
                "QUINIENTOS", "SEISCIENTOS", "SETECIENTOS", "OCHOCIENTOS",
                "NOVECIENTOS"]

    def _dos_digitos(n):
        if n <= 20:
            return unidades[n]
        d, u = divmod(n, 10)
        if u == 0:
            return decenas[d]
        sep = "Y " if d > 2 else ""
        return decenas[d] + sep + unidades[u]

    def _tres_digitos(n):
        c, resto = divmod(n, 100)
        if c == 1 and resto == 0:
            return "CIEN"
        if c == 1:
            return "CIENTO " + _dos_digitos(resto)
        if resto == 0:
            return centenas[c]
        return centenas[c] + " " + _dos_digitos(resto)

    if n == 0:
        return "CERO"
    n = int(n)
    if n < 0:
        return "MENOS " + numero_a_letras(-n)

    partes = []
    millones, resto = divmod(n, 1_000_000)
    if millones:
        if millones == 1:
            partes.append("UN MILLÓN")
        else:
            partes.append(_tres_digitos(millones) + " MILLONES")
    miles, resto = divmod(resto, 1_000)
    if miles:
        if miles == 1:
            partes.append("MIL")
        else:
            partes.append(_tres_digitos(miles) + " MIL")
    if resto:
        partes.append(_tres_digitos(resto))
    return " ".join(partes)


# ─── Autenticación ────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            flash("Debes iniciar sesión para acceder.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get("rol") != "Administrador":
            flash("Acceso restringido a administradores.", "danger")
            return redirect(url_for("dashboard"))
        return f(*args, **kwargs)
    return login_required(decorated)


@app.before_request
def load_user():
    g.user = None
    if "user_id" in session:
        db = get_db()
        g.user = db.execute(
            "SELECT u.*, r.nombre AS rol FROM usuarios u "
            "JOIN roles r ON r.id = u.rol_id WHERE u.id = ?",
            (session["user_id"],)
        ).fetchone()
        db.close()


# ─── Login / Logout ───────────────────────────────────────────────────────────

@app.route("/", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip()
        password = request.form.get("password", "")
        db = get_db()
        user = db.execute(
            "SELECT u.*, r.nombre AS rol FROM usuarios u "
            "JOIN roles r ON r.id = u.rol_id "
            "WHERE u.usuario = ? AND u.activo = 1", (usuario,)
        ).fetchone()
        db.close()
        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["nombre"] = user["nombre"]
            session["rol"] = user["rol"]
            flash(f"Bienvenido, {user['nombre']}.", "success")
            return redirect(url_for("dashboard"))
        flash("Usuario o contraseña incorrectos.", "danger")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Sesión cerrada correctamente.", "info")
    return redirect(url_for("login"))


# ─── Dashboard ────────────────────────────────────────────────────────────────

@app.route("/dashboard")
@login_required
def dashboard():
    db = get_db()
    hoy = date.today().isoformat()
    mes_actual = date.today().strftime("%Y-%m")

    stats = {}
    stats["propiedades"] = db.execute(
        "SELECT COUNT(*) FROM propiedades").fetchone()[0]
    stats["inquilinos"] = db.execute(
        "SELECT COUNT(*) FROM inquilinos").fetchone()[0]
    stats["contratos_activos"] = db.execute(
        "SELECT COUNT(*) FROM contratos WHERE activo=1").fetchone()[0]

    stats["recaudado_mes"] = db.execute("""
        SELECT COALESCE(SUM(p.monto_pagado), 0)
        FROM pagos p
        JOIN alquileres a ON a.id = p.alquiler_id
        WHERE a.periodo = ? AND p.anulado = 0
    """, (mes_actual,)).fetchone()[0]

    stats["en_mora"] = db.execute("""
        SELECT COUNT(*) FROM alquileres
        WHERE saldo > 0 AND fecha_vencimiento < ? AND estado_id != 3
    """, (hoy,)).fetchone()[0]

    stats["saldo_pendiente"] = db.execute("""
        SELECT COALESCE(SUM(saldo), 0) FROM alquileres WHERE saldo > 0
    """).fetchone()[0]

    # Últimos 5 recibos
    ultimos_recibos = db.execute("""
        SELECT r.nro_recibo, r.creado_en, i.nombre || ' ' || i.apellido AS inquilino,
               p.monto_pagado, al.periodo, tp.nombre AS tipo_pago
        FROM recibos r
        JOIN pagos p ON p.id = r.pago_id
        JOIN alquileres al ON al.id = p.alquiler_id
        JOIN contratos c ON c.id = al.contrato_id
        JOIN inquilinos i ON i.id = c.inquilino_id
        JOIN tipos_pago tp ON tp.id = p.tipo_pago_id
        WHERE r.anulado = 0
        ORDER BY r.nro_recibo DESC LIMIT 5
    """).fetchall()

    db.close()
    return render_template("dashboard.html", stats=stats, ultimos_recibos=ultimos_recibos)


# ═══════════════════════════════════════════════════════════════════════════════
# PROPIEDADES
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/propiedades")
@login_required
def propiedades():
    db = get_db()
    rows = db.execute("""
        SELECT p.*, tp.nombre AS tipo, ep.nombre AS estado
        FROM propiedades p
        LEFT JOIN tipos_propiedad tp ON tp.id = p.tipo_id
        LEFT JOIN estados_propiedad ep ON ep.id = p.estado_id
        ORDER BY p.id ASC
    """).fetchall()
    db.close()
    return render_template("propiedades/lista.html", propiedades=rows)


@app.route("/propiedades/nueva", methods=["GET", "POST"])
@login_required
@admin_required
def nueva_propiedad():
    db = get_db()
    tipos = db.execute("SELECT * FROM tipos_propiedad").fetchall()
    estados = db.execute("SELECT * FROM estados_propiedad").fetchall()
    if request.method == "POST":
        db.execute("""
            INSERT INTO propiedades(cta_cte_central, direccion, ciudad, tipo_id, estado_id, descripcion)
            VALUES (?,?,?,?,?,?)
        """, (
            request.form.get("cta_cte_central"),
            request.form.get("direccion"),
            request.form.get("ciudad"),
            request.form.get("tipo_id") or None,
            request.form.get("estado_id") or None,
            request.form.get("descripcion"),
        ))
        db.commit()
        db.close()
        flash("Propiedad registrada correctamente.", "success")
        return redirect(url_for("propiedades"))
    db.close()
    return render_template("propiedades/form.html", tipos=tipos, estados=estados, propiedad=None)


@app.route("/propiedades/<int:pid>/editar", methods=["GET", "POST"])
@login_required
@admin_required
def editar_propiedad(pid):
    db = get_db()
    propiedad = db.execute("SELECT * FROM propiedades WHERE id=?", (pid,)).fetchone()
    tipos = db.execute("SELECT * FROM tipos_propiedad").fetchall()
    estados = db.execute("SELECT * FROM estados_propiedad").fetchall()
    if not propiedad:
        db.close()
        flash("Propiedad no encontrada.", "danger")
        return redirect(url_for("propiedades"))
    if request.method == "POST":
        db.execute("""
            UPDATE propiedades SET cta_cte_central=?, direccion=?, ciudad=?,
            tipo_id=?, estado_id=?, descripcion=? WHERE id=?
        """, (
            request.form.get("cta_cte_central"),
            request.form.get("direccion"),
            request.form.get("ciudad"),
            request.form.get("tipo_id") or None,
            request.form.get("estado_id") or None,
            request.form.get("descripcion"),
            pid,
        ))
        db.commit()
        db.close()
        flash("Propiedad actualizada.", "success")
        return redirect(url_for("propiedades"))
    db.close()
    return render_template("propiedades/form.html", tipos=tipos, estados=estados, propiedad=propiedad)


@app.route("/propiedades/<int:pid>/eliminar", methods=["POST"])
@login_required
@admin_required
def eliminar_propiedad(pid):
    db = get_db()
    en_uso = db.execute(
        "SELECT COUNT(*) FROM contratos WHERE propiedad_id=? AND activo=1", (pid,)
    ).fetchone()[0]
    if en_uso:
        db.close()
        flash("No se puede eliminar: la propiedad tiene contratos activos.", "danger")
        return redirect(url_for("propiedades"))
    db.execute("DELETE FROM propiedades WHERE id=?", (pid,))
    db.commit()
    db.close()
    flash("Propiedad eliminada.", "success")
    return redirect(url_for("propiedades"))


# ═══════════════════════════════════════════════════════════════════════════════
# INQUILINOS
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/inquilinos")
@login_required
def inquilinos():
    db = get_db()
    rows = db.execute("SELECT * FROM inquilinos ORDER BY id ASC").fetchall()
    db.close()
    return render_template("inquilinos/lista.html", inquilinos=rows)


@app.route("/inquilinos/nuevo", methods=["GET", "POST"])
@login_required
@admin_required
def nuevo_inquilino():
    if request.method == "POST":
        db = get_db()
        db.execute("""
            INSERT INTO inquilinos(nombre, apellido, cotitular, ruc_ci, telefono, email, direccion)
            VALUES (?,?,?,?,?,?,?)
        """, (
            request.form.get("nombre"),
            request.form.get("apellido"),
            request.form.get("cotitular"),
            request.form.get("ruc_ci"),
            request.form.get("telefono"),
            request.form.get("email"),
            request.form.get("direccion"),
        ))
        db.commit()
        db.close()
        flash("Inquilino registrado.", "success")
        return redirect(url_for("inquilinos"))
    return render_template("inquilinos/form.html", inquilino=None)


@app.route("/inquilinos/<int:iid>/editar", methods=["GET", "POST"])
@login_required
@admin_required
def editar_inquilino(iid):
    db = get_db()
    inquilino = db.execute("SELECT * FROM inquilinos WHERE id=?", (iid,)).fetchone()
    if not inquilino:
        db.close()
        flash("Inquilino no encontrado.", "danger")
        return redirect(url_for("inquilinos"))
    if request.method == "POST":
        db.execute("""
            UPDATE inquilinos SET nombre=?, apellido=?, cotitular=?, ruc_ci=?,
            telefono=?, email=?, direccion=? WHERE id=?
        """, (
            request.form.get("nombre"),
            request.form.get("apellido"),
            request.form.get("cotitular"),
            request.form.get("ruc_ci"),
            request.form.get("telefono"),
            request.form.get("email"),
            request.form.get("direccion"),
            iid,
        ))
        db.commit()
        db.close()
        flash("Inquilino actualizado.", "success")
        return redirect(url_for("inquilinos"))
    db.close()
    return render_template("inquilinos/form.html", inquilino=inquilino)


@app.route("/inquilinos/<int:iid>/eliminar", methods=["POST"])
@login_required
@admin_required
def eliminar_inquilino(iid):
    db = get_db()
    en_uso = db.execute(
        "SELECT COUNT(*) FROM contratos WHERE inquilino_id=?", (iid,)
    ).fetchone()[0]
    if en_uso:
        db.close()
        flash("No se puede eliminar: el inquilino tiene contratos asociados.", "danger")
        return redirect(url_for("inquilinos"))
    db.execute("DELETE FROM inquilinos WHERE id=?", (iid,))
    db.commit()
    db.close()
    flash("Inquilino eliminado.", "success")
    return redirect(url_for("inquilinos"))


# ═══════════════════════════════════════════════════════════════════════════════
# CONTRATOS Y ALQUILERES
# ═══════════════════════════════════════════════════════════════════════════════

def _generar_alquileres(db, contrato_id):
    """
    Genera los registros de alquileres (cuotas) para un contrato.
    RN02: fecha_vencimiento = fecha_inicio del período + dias_periodo_pago (default 6).
    RN03: mora desde el día siguiente al vencimiento, sin tolerancia.
    """
    contrato = db.execute("SELECT * FROM contratos WHERE id=?", (contrato_id,)).fetchone()
    fecha_inicio = datetime.strptime(contrato["fecha_inicio"], "%Y-%m-%d").date()
    fecha_fin    = datetime.strptime(contrato["fecha_fin"],    "%Y-%m-%d").date()
    canon        = contrato["canon_mensual"]
    dias_pago    = contrato["dias_periodo_pago"]  # RN02: 6 días

    # Borrar alquileres previos sin pagos
    db.execute("""
        DELETE FROM alquileres WHERE contrato_id=?
        AND id NOT IN (SELECT DISTINCT alquiler_id FROM pagos)
    """, (contrato_id,))

    meses = (fecha_fin.year - fecha_inicio.year) * 12 + (fecha_fin.month - fecha_inicio.month) + 1
    estado_pendiente = db.execute(
        "SELECT id FROM estados_alquiler WHERE nombre='Pendiente'"
    ).fetchone()["id"]

    for i in range(meses):
        mes  = fecha_inicio.month + i
        anio = fecha_inicio.year + (mes - 1) // 12
        mes  = ((mes - 1) % 12) + 1
        periodo = f"{anio:04d}-{mes:02d}"

        # RN02: el período de pago son 6 días desde el primer día del mes
        fecha_inicio_periodo = date(anio, mes, 1)
        fecha_venc = (fecha_inicio_periodo + timedelta(days=dias_pago - 1)).isoformat()

        try:
            db.execute("""
                INSERT OR IGNORE INTO alquileres
                (contrato_id, periodo, nro_cuota, total_cuotas, monto, saldo, estado_id, fecha_vencimiento)
                VALUES (?,?,?,?,?,?,?,?)
            """, (contrato_id, periodo, i + 1, meses, canon, canon, estado_pendiente, fecha_venc))
        except Exception:
            pass


@app.route("/contratos")
@login_required
def contratos():
    db = get_db()
    rows = db.execute("""
        SELECT c.*, i.nombre || ' ' || i.apellido AS inquilino,
               p.direccion AS propiedad, p.cta_cte_central
        FROM contratos c
        JOIN inquilinos i ON i.id = c.inquilino_id
        JOIN propiedades p ON p.id = c.propiedad_id
        ORDER BY c.id ASC
    """).fetchall()
    db.close()
    return render_template("contratos/lista.html", contratos=rows)


@app.route("/contratos/nuevo", methods=["GET", "POST"])
@login_required
@admin_required
def nuevo_contrato():
    db = get_db()
    propiedades_list = db.execute(
        "SELECT * FROM propiedades ORDER BY direccion").fetchall()
    inquilinos_list = db.execute(
        "SELECT * FROM inquilinos ORDER BY apellido, nombre").fetchall()
    if request.method == "POST":
        cur = db.execute("""
            INSERT INTO contratos(propiedad_id, inquilino_id, fecha_inicio, fecha_fin,
            canon_mensual, dias_periodo_pago, recargo_mora_diario, observaciones)
            VALUES (?,?,?,?,?,?,?,?)
        """, (
            request.form.get("propiedad_id"),
            request.form.get("inquilino_id"),
            request.form.get("fecha_inicio"),
            request.form.get("fecha_fin"),
            float(request.form.get("canon_mensual", 0)),
            int(request.form.get("dias_periodo_pago", 6)),
            float(request.form.get("recargo_mora_diario", 5000)),
            request.form.get("observaciones"),
        ))
        contrato_id = cur.lastrowid
        # Marcar propiedad como alquilada
        db.execute("""
            UPDATE propiedades SET estado_id=(SELECT id FROM estados_propiedad WHERE nombre='Alquilada')
            WHERE id=?
        """, (request.form.get("propiedad_id"),))
        _generar_alquileres(db, contrato_id)
        db.commit()
        db.close()
        flash("Contrato creado y alquileres generados.", "success")
        return redirect(url_for("contratos"))
    db.close()
    return render_template("contratos/form.html",
                           propiedades=propiedades_list,
                           inquilinos=inquilinos_list,
                           contrato=None)


@app.route("/contratos/<int:cid>")
@login_required
def ver_contrato(cid):
    db = get_db()
    contrato = db.execute("""
        SELECT c.*, i.nombre || ' ' || i.apellido AS inquilino,
               i.cotitular, p.direccion AS propiedad, p.cta_cte_central,
               p.ciudad
        FROM contratos c
        JOIN inquilinos i ON i.id = c.inquilino_id
        JOIN propiedades p ON p.id = c.propiedad_id
        WHERE c.id=?
    """, (cid,)).fetchone()
    if not contrato:
        db.close()
        flash("Contrato no encontrado.", "danger")
        return redirect(url_for("contratos"))

    hoy = date.today().isoformat()
    alquileres = db.execute("""
        SELECT al.*, ea.nombre AS estado
        FROM alquileres al
        JOIN estados_alquiler ea ON ea.id = al.estado_id
        WHERE al.contrato_id=?
        ORDER BY al.periodo
    """, (cid,)).fetchall()

    # Actualizar estados de mora
    for al in alquileres:
        if al["saldo"] > 0 and al["fecha_vencimiento"] < hoy:
            db.execute("""
                UPDATE alquileres SET estado_id=(SELECT id FROM estados_alquiler WHERE nombre='En mora')
                WHERE id=? AND saldo > 0
            """, (al["id"],))
    db.commit()

    alquileres = db.execute("""
        SELECT al.*, ea.nombre AS estado
        FROM alquileres al
        JOIN estados_alquiler ea ON ea.id = al.estado_id
        WHERE al.contrato_id=?
        ORDER BY al.periodo
    """, (cid,)).fetchall()
    db.close()
    return render_template("contratos/ver.html", contrato=contrato, alquileres=alquileres)


@app.route("/contratos/<int:cid>/editar", methods=["GET", "POST"])
@login_required
@admin_required
def editar_contrato(cid):
    db = get_db()
    contrato = db.execute("SELECT * FROM contratos WHERE id=?", (cid,)).fetchone()
    propiedades_list = db.execute("SELECT * FROM propiedades ORDER BY direccion").fetchall()
    inquilinos_list = db.execute("SELECT * FROM inquilinos ORDER BY apellido").fetchall()
    if not contrato:
        db.close()
        flash("Contrato no encontrado.", "danger")
        return redirect(url_for("contratos"))
    if request.method == "POST":
        db.execute("""
            UPDATE contratos SET propiedad_id=?, inquilino_id=?, fecha_inicio=?,
            fecha_fin=?, canon_mensual=?, dias_periodo_pago=?, recargo_mora_diario=?,
            observaciones=?, activo=?
            WHERE id=?
        """, (
            request.form.get("propiedad_id"),
            request.form.get("inquilino_id"),
            request.form.get("fecha_inicio"),
            request.form.get("fecha_fin"),
            float(request.form.get("canon_mensual", 0)),
            int(request.form.get("dias_periodo_pago", 6)),
            float(request.form.get("recargo_mora_diario", 5000)),
            request.form.get("observaciones"),
            1 if request.form.get("activo") else 0,
            cid,
        ))
        db.commit()
        db.close()
        flash("Contrato actualizado.", "success")
        return redirect(url_for("ver_contrato", cid=cid))
    db.close()
    return render_template("contratos/form.html",
                           propiedades=propiedades_list,
                           inquilinos=inquilinos_list,
                           contrato=contrato)


# ═══════════════════════════════════════════════════════════════════════════════
# COBRANZAS - lógica central con RN01 a RN06 (versión final del documento)
#
# RN01: pago parcial mínimo 50% del canon (solo primer pago del período)
# RN02: período de pago = dias_periodo_pago días desde el día 1 del mes
# RN03: mora desde el día siguiente al vencimiento, sin tolerancia
# RN04: recargo = recargo_mora_diario × días de atraso
# RN05: pagos adelantados sin condiciones
# RN06: pago de varios meses → un recibo POR CADA MES pagado
# ═══════════════════════════════════════════════════════════════════════════════

def _calcular_recargo(fecha_vencimiento_str, hoy_str, recargo_diario):
    """
    RN03 + RN04: calcula el recargo por mora.
    La mora empieza el día siguiente al vencimiento (sin tolerancia).
    Recargo = días de atraso × recargo_mora_diario (Gs. 5.000).
    """
    fecha_venc = date.fromisoformat(fecha_vencimiento_str)
    hoy = date.fromisoformat(hoy_str)
    if hoy <= fecha_venc:
        return 0.0, 0
    dias_atraso = (hoy - fecha_venc).days  # mora desde día siguiente (hoy > fecha_venc)
    recargo = round(dias_atraso * recargo_diario, 0)
    return recargo, dias_atraso

@app.route("/cobranzas")
@login_required
def cobranzas():
    db = get_db()
    # Buscar contratos activos con saldos pendientes
    q = request.args.get("q", "")
    sql = """
        SELECT DISTINCT c.id AS contrato_id,
               i.nombre || ' ' || i.apellido AS inquilino,
               i.cotitular, p.direccion AS propiedad,
               SUM(al.saldo) AS saldo_total,
               COUNT(CASE WHEN al.fecha_vencimiento < date('now') AND al.saldo > 0 THEN 1 END) AS cuotas_mora
        FROM contratos c
        JOIN inquilinos i ON i.id = c.inquilino_id
        JOIN propiedades p ON p.id = c.propiedad_id
        JOIN alquileres al ON al.contrato_id = c.id
        WHERE c.activo = 1
    """
    params = []
    if q:
        sql += " AND (i.nombre LIKE ? OR i.apellido LIKE ? OR p.direccion LIKE ?)"
        like = f"%{q}%"
        params = [like, like, like]
    sql += " GROUP BY c.id ORDER BY cuotas_mora DESC, i.apellido"
    rows = db.execute(sql, params).fetchall()
    db.close()
    return render_template("cobranzas/lista.html", contratos=rows, q=q)


@app.route("/cobranzas/registrar/<int:contrato_id>", methods=["GET", "POST"])
@login_required
def registrar_cobro(contrato_id):
    db = get_db()
    hoy = date.today().isoformat()

    contrato = db.execute("""
        SELECT c.*, i.nombre || ' ' || i.apellido AS inquilino,
               i.cotitular, p.direccion AS propiedad, p.cta_cte_central
        FROM contratos c
        JOIN inquilinos i ON i.id = c.inquilino_id
        JOIN propiedades p ON p.id = c.propiedad_id
        WHERE c.id=?
    """, (contrato_id,)).fetchone()

    if not contrato:
        db.close()
        flash("Contrato no encontrado.", "danger")
        return redirect(url_for("cobranzas"))

    # Actualizar mora antes de mostrar (RN03: día siguiente al vencimiento)
    db.execute("""
        UPDATE alquileres SET estado_id=(SELECT id FROM estados_alquiler WHERE nombre='En mora')
        WHERE contrato_id=? AND saldo > 0 AND fecha_vencimiento < ?
    """, (contrato_id, hoy))
    db.commit()

    alquileres_raw = db.execute("""
        SELECT al.*, ea.nombre AS estado,
               c.recargo_mora_diario,
               (SELECT COALESCE(SUM(p2.monto_pagado),0) FROM pagos p2
                WHERE p2.alquiler_id = al.id AND p2.anulado=0) AS total_pagado
        FROM alquileres al
        JOIN estados_alquiler ea ON ea.id = al.estado_id
        JOIN contratos c ON c.id = al.contrato_id
        WHERE al.contrato_id=? AND al.saldo > 0
        ORDER BY al.periodo
    """, (contrato_id,)).fetchall()

    # Calcular recargo y días de mora para cada alquiler
    alquileres = []
    for al in alquileres_raw:
        recargo, dias = _calcular_recargo(al["fecha_vencimiento"], hoy, al["recargo_mora_diario"])
        alquileres.append({
            **dict(al),
            "recargo_calculado": recargo,
            "dias_mora": dias,
            "total_a_cobrar": al["saldo"] + recargo,
        })

    medios = db.execute("SELECT * FROM medios_pago").fetchall()

    if request.method == "POST":
        alquiler_ids  = request.form.getlist("alquiler_ids")
        monto_str     = request.form.get("monto_total", "0").replace(".", "").replace(",", "")
        monto_total   = float(monto_str) if monto_str else 0
        medio_pago_id = request.form.get("medio_pago_id")
        nro_cheque        = request.form.get("nro_cheque", "")
        nro_deposito      = request.form.get("nro_deposito", "")
        nro_transferencia = request.form.get("nro_transferencia", "")
        fecha_pago    = request.form.get("fecha_pago", hoy)
        observaciones = request.form.get("observaciones", "")
        nro_factura   = request.form.get("nro_factura", "")

        if not alquiler_ids:
            flash("Seleccioná al menos un período a pagar.", "warning")
            db.close()
            return render_template("cobranzas/registrar.html",
                                   contrato=contrato, alquileres=alquileres,
                                   medios=medios, today=hoy, today_str=hoy)

        errores = []
        recibos_generados = []
        monto_restante = monto_total

        for alq_id in alquiler_ids:
            alq = db.execute("""
                SELECT al.*, c.recargo_mora_diario, c.canon_mensual
                FROM alquileres al
                JOIN contratos c ON c.id = al.contrato_id
                WHERE al.id=?
            """, (alq_id,)).fetchone()

            if not alq:
                continue

            saldo_alq = alq["saldo"]
            canon     = alq["monto"]

            # RN03 + RN04: recargo = días de atraso × Gs. 5.000
            recargo, dias_mora = _calcular_recargo(
                alq["fecha_vencimiento"], fecha_pago, alq["recargo_mora_diario"]
            )

            total_a_cobrar  = saldo_alq + recargo
            monto_a_aplicar = min(monto_restante, total_a_cobrar)

            # RN01: mínimo 50% del canon solo en el primer pago del período
            total_pagado_previo = db.execute("""
                SELECT COALESCE(SUM(monto_pagado),0) FROM pagos
                WHERE alquiler_id=? AND anulado=0
            """, (alq_id,)).fetchone()[0]

            if total_pagado_previo == 0 and monto_a_aplicar < (canon * 0.5):
                errores.append(
                    f"Período {alq['periodo']}: el monto mínimo es el 50% del alquiler "
                    f"({fmt_gs(canon * 0.5)}). Ingresaste {fmt_gs(monto_a_aplicar)}."
                )
                continue

            if monto_a_aplicar <= 0:
                break

            # Determinar tipo de pago
            monto_al_saldo = round(monto_a_aplicar - recargo, 0)
            nuevo_saldo    = max(round(saldo_alq - monto_al_saldo, 0), 0)

            if total_pagado_previo == 0 and nuevo_saldo == 0:
                tipo_pago_nombre = "Pago total"
            elif total_pagado_previo > 0 and nuevo_saldo == 0:
                tipo_pago_nombre = "Cancelación de saldo"
            else:
                tipo_pago_nombre = "Pago parcial"

            tipo_pago_id = db.execute(
                "SELECT id FROM tipos_pago WHERE nombre=?", (tipo_pago_nombre,)
            ).fetchone()["id"]

            # Registrar pago
            cur = db.execute("""
                INSERT INTO pagos(alquiler_id, usuario_id, tipo_pago_id, medio_pago_id,
                monto_pagado, recargo_mora, fecha_pago, nro_cheque, nro_deposito,
                nro_transferencia, observaciones)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, (
                alq_id, session["user_id"], tipo_pago_id, medio_pago_id,
                monto_al_saldo, recargo, fecha_pago,
                nro_cheque, nro_deposito, nro_transferencia, observaciones,
            ))
            pago_id = cur.lastrowid

            # Actualizar saldo del alquiler
            nuevo_estado_id = db.execute(
                "SELECT id FROM estados_alquiler WHERE nombre=?",
                ("Pagado" if nuevo_saldo == 0 else "Pagado parcial",)
            ).fetchone()["id"]
            db.execute("UPDATE alquileres SET saldo=?, estado_id=? WHERE id=?",
                       (nuevo_saldo, nuevo_estado_id, alq_id))

            # RN06: un recibo correlativo por cada mes/período pagado
            max_recibo = db.execute(
                "SELECT COALESCE(MAX(nro_recibo),0) FROM recibos"
            ).fetchone()[0]
            nro_nuevo = max_recibo + 1
            db.execute("""
                INSERT INTO recibos(nro_recibo, pago_id, nro_factura)
                VALUES (?,?,?)
            """, (nro_nuevo, pago_id, nro_factura))

            recibos_generados.append(nro_nuevo)
            monto_restante -= monto_a_aplicar

        if errores:
            db.rollback()
            db.close()
            for e in errores:
                flash(e, "danger")
            return redirect(url_for("registrar_cobro", contrato_id=contrato_id))

        db.commit()
        db.close()
        if recibos_generados:
            numeros = ", ".join([f"N°{r:04d}" for r in recibos_generados])
            flash(f"Cobro registrado. Recibo(s) emitido(s): {numeros}.", "success")
        return redirect(url_for("ver_contrato", cid=contrato_id))

    db.close()
    return render_template("cobranzas/registrar.html",
                           contrato=contrato, alquileres=alquileres, medios=medios,
                           today=hoy, today_str=hoy)

# ═══════════════════════════════════════════════════════════════════════════════
# RECIBOS
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/recibos")
@login_required
def recibos():
    db = get_db()
    q = request.args.get("q", "")
    sql = """
        SELECT r.*, p.monto_pagado, p.recargo_mora, p.fecha_pago,
               tp.nombre AS tipo_pago, mp.nombre AS medio_pago,
               al.periodo, al.nro_cuota, al.total_cuotas, al.monto AS monto_alquiler,
               i.nombre || ' ' || i.apellido AS inquilino,
               pr.direccion AS propiedad
        FROM recibos r
        JOIN pagos p ON p.id = r.pago_id
        JOIN alquileres al ON al.id = p.alquiler_id
        JOIN contratos c ON c.id = al.contrato_id
        JOIN inquilinos i ON i.id = c.inquilino_id
        JOIN propiedades pr ON pr.id = c.propiedad_id
        JOIN tipos_pago tp ON tp.id = p.tipo_pago_id
        JOIN medios_pago mp ON mp.id = p.medio_pago_id
    """
    params = []
    if q:
        sql += " WHERE (i.nombre LIKE ? OR i.apellido LIKE ? OR CAST(r.nro_recibo AS TEXT) LIKE ?)"
        like = f"%{q}%"
        params = [like, like, like]
    sql += " ORDER BY r.nro_recibo DESC"
    rows = db.execute(sql, params).fetchall()
    db.close()
    return render_template("recibos/lista.html", recibos=rows, q=q)


@app.route("/recibos/<int:rid>")
@login_required
def ver_recibo(rid):
    db = get_db()
    recibo = db.execute("""
        SELECT r.*, p.monto_pagado, p.recargo_mora, p.fecha_pago,
               p.nro_cheque, p.nro_deposito, p.nro_transferencia,
               p.observaciones AS obs_pago,
               tp.nombre AS tipo_pago, mp.nombre AS medio_pago,
               al.periodo, al.nro_cuota, al.total_cuotas,
               al.monto AS monto_alquiler, al.saldo AS saldo_actual,
               i.nombre AS inq_nombre, i.apellido AS inq_apellido, i.cotitular,
               pr.direccion AS propiedad, pr.cta_cte_central, pr.ciudad,
               u.nombre AS registrado_por
        FROM recibos r
        JOIN pagos p ON p.id = r.pago_id
        JOIN alquileres al ON al.id = p.alquiler_id
        JOIN contratos c ON c.id = al.contrato_id
        JOIN inquilinos i ON i.id = c.inquilino_id
        JOIN propiedades pr ON pr.id = c.propiedad_id
        JOIN tipos_pago tp ON tp.id = p.tipo_pago_id
        JOIN medios_pago mp ON mp.id = p.medio_pago_id
        JOIN usuarios u ON u.id = p.usuario_id
        WHERE r.id=?
    """, (rid,)).fetchone()

    if not recibo:
        db.close()
        flash("Recibo no encontrado.", "danger")
        return redirect(url_for("recibos"))

    # Total pagado antes de este recibo para el mismo alquiler
    pagado_antes = db.execute("""
        SELECT COALESCE(SUM(p2.monto_pagado),0)
        FROM pagos p2
        JOIN recibos r2 ON r2.pago_id = p2.id
        WHERE p2.alquiler_id = ? AND p2.anulado=0 AND r2.nro_recibo < ?
    """, (recibo["periodo"], recibo["nro_recibo"])).fetchone()[0]

    # Calcular abonado antes correctamente con alquiler_id
    alquiler_id = db.execute(
        "SELECT alquiler_id FROM pagos WHERE id=?", (recibo["pago_id"],)
    ).fetchone()["alquiler_id"]

    pagado_antes = db.execute("""
        SELECT COALESCE(SUM(p2.monto_pagado),0)
        FROM pagos p2
        JOIN recibos r2 ON r2.pago_id = p2.id
        WHERE p2.alquiler_id=? AND p2.anulado=0 AND r2.nro_recibo < ?
    """, (alquiler_id, recibo["nro_recibo"])).fetchone()[0]

    monto_en_letras = numero_a_letras(int(recibo["monto_pagado"])) + ".-"
    db.close()
    return render_template("recibos/ver.html",
                           recibo=recibo,
                           pagado_antes=pagado_antes,
                           monto_en_letras=monto_en_letras)


@app.route("/recibos/<int:rid>/anular", methods=["GET", "POST"])
@login_required
def anular_recibo(rid):
    db = get_db()
    recibo = db.execute("""
        SELECT r.*, al.id AS alquiler_id, al.saldo, al.monto AS monto_alq,
               p.monto_pagado, p.recargo_mora,
               i.nombre || ' ' || i.apellido AS inquilino
        FROM recibos r
        JOIN pagos p ON p.id = r.pago_id
        JOIN alquileres al ON al.id = p.alquiler_id
        JOIN contratos c ON c.id = al.contrato_id
        JOIN inquilinos i ON i.id = c.inquilino_id
        WHERE r.id=?
    """, (rid,)).fetchone()

    if not recibo:
        db.close()
        flash("Recibo no encontrado.", "danger")
        return redirect(url_for("recibos"))

    if recibo["anulado"]:
        db.close()
        flash("Este recibo ya fue anulado.", "warning")
        return redirect(url_for("recibos"))

    if request.method == "POST":
        motivo = request.form.get("motivo", "").strip()
        if not motivo:
            flash("Debés ingresar el motivo de anulación.", "warning")
            db.close()
            return render_template("recibos/anular.html", recibo=recibo)

        ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # RN06: anular sin alterar correlatividad
        db.execute("""
            UPDATE recibos SET anulado=1, motivo_anulacion=?,
            anulado_por_id=?, anulado_en=? WHERE id=?
        """, (motivo, session["user_id"], ahora, rid))

        db.execute("UPDATE pagos SET anulado=1 WHERE id=?", (recibo["pago_id"],))

        # Restaurar saldo del alquiler
        nuevo_saldo = recibo["saldo"] + recibo["monto_pagado"]
        estado_id = db.execute(
            "SELECT id FROM estados_alquiler WHERE nombre='Pagado parcial'"
        ).fetchone()["id"]
        if nuevo_saldo >= recibo["monto_alq"]:
            estado_id = db.execute(
                "SELECT id FROM estados_alquiler WHERE nombre='Pendiente'"
            ).fetchone()["id"]

        db.execute("""
            UPDATE alquileres SET saldo=?, estado_id=? WHERE id=?
        """, (nuevo_saldo, estado_id, recibo["alquiler_id"]))

        db.commit()
        db.close()
        flash(f"Recibo N° {recibo['nro_recibo']} anulado. La numeración se mantiene por trazabilidad.", "success")
        return redirect(url_for("recibos"))

    db.close()
    return render_template("recibos/anular.html", recibo=recibo)


# ═══════════════════════════════════════════════════════════════════════════════
# REPORTES
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/reportes")
@login_required
def reportes():
    return render_template("reportes/index.html")


@app.route("/reportes/recaudacion")
@login_required
def reporte_recaudacion():
    db = get_db()
    fecha_desde = request.args.get("fecha_desde", date.today().replace(day=1).isoformat())
    fecha_hasta = request.args.get("fecha_hasta", date.today().isoformat())
    medio_id = request.args.get("medio_id", "")

    sql = """
        SELECT r.nro_recibo, p.fecha_pago, i.nombre || ' ' || i.apellido AS inquilino,
               al.periodo, al.nro_cuota || '/' || al.total_cuotas AS cuota,
               mp.nombre AS medio_pago, tp.nombre AS tipo_pago,
               p.monto_pagado, p.recargo_mora,
               pr.direccion AS propiedad
        FROM recibos r
        JOIN pagos p ON p.id = r.pago_id
        JOIN alquileres al ON al.id = p.alquiler_id
        JOIN contratos c ON c.id = al.contrato_id
        JOIN inquilinos i ON i.id = c.inquilino_id
        JOIN propiedades pr ON pr.id = c.propiedad_id
        JOIN medios_pago mp ON mp.id = p.medio_pago_id
        JOIN tipos_pago tp ON tp.id = p.tipo_pago_id
        WHERE p.anulado=0 AND p.fecha_pago BETWEEN ? AND ?
    """
    params = [fecha_desde, fecha_hasta]
    if medio_id:
        sql += " AND p.medio_pago_id = ?"
        params.append(medio_id)
    sql += " ORDER BY r.nro_recibo"

    rows = db.execute(sql, params).fetchall()
    total = sum(r["monto_pagado"] for r in rows)
    medios = db.execute("SELECT * FROM medios_pago").fetchall()
    db.close()
    return render_template("reportes/recaudacion.html",
                           rows=rows, total=total, medios=medios,
                           fecha_desde=fecha_desde, fecha_hasta=fecha_hasta,
                           medio_id=medio_id)


@app.route("/reportes/morosidad")
@login_required
def reporte_morosidad():
    db = get_db()
    fecha_corte = request.args.get("fecha_corte", date.today().isoformat())

    rows = db.execute("""
        SELECT i.nombre || ' ' || i.apellido AS inquilino,
               i.telefono, pr.direccion AS propiedad,
               al.periodo, al.nro_cuota || '/' || al.total_cuotas AS cuota,
               al.saldo,
               CAST(julianday(?) - julianday(al.fecha_vencimiento) AS INTEGER) AS dias_mora,
               al.fecha_vencimiento,
               c.id AS contrato_id
        FROM alquileres al
        JOIN contratos c ON c.id = al.contrato_id
        JOIN inquilinos i ON i.id = c.inquilino_id
        JOIN propiedades pr ON pr.id = c.propiedad_id
        WHERE al.saldo > 0 AND al.fecha_vencimiento < ?
        ORDER BY dias_mora DESC, i.apellido
    """, (fecha_corte, fecha_corte)).fetchall()

    total_mora = sum(r["saldo"] for r in rows)
    db.close()
    return render_template("reportes/morosidad.html",
                           rows=rows, total_mora=total_mora, fecha_corte=fecha_corte)


@app.route("/reportes/comprobantes")
@login_required
def reporte_comprobantes():
    db = get_db()
    fecha_desde = request.args.get("fecha_desde", date.today().replace(day=1).isoformat())
    fecha_hasta = request.args.get("fecha_hasta", date.today().isoformat())

    rows = db.execute("""
        SELECT r.id, r.nro_recibo, r.nro_factura, r.anulado, r.motivo_anulacion,
               p.fecha_pago, p.monto_pagado,
               i.nombre || ' ' || i.apellido AS inquilino,
               al.periodo, tp.nombre AS tipo_pago,
               u.nombre AS operador
        FROM recibos r
        JOIN pagos p ON p.id = r.pago_id
        JOIN alquileres al ON al.id = p.alquiler_id
        JOIN contratos c ON c.id = al.contrato_id
        JOIN inquilinos i ON i.id = c.inquilino_id
        JOIN tipos_pago tp ON tp.id = p.tipo_pago_id
        JOIN usuarios u ON u.id = p.usuario_id
        WHERE p.fecha_pago BETWEEN ? AND ?
        ORDER BY r.nro_recibo
    """, (fecha_desde, fecha_hasta)).fetchall()
    db.close()
    return render_template("reportes/comprobantes.html",
                           rows=rows, fecha_desde=fecha_desde, fecha_hasta=fecha_hasta)


@app.route("/reportes/cuotas_vencidas")
@login_required
def reporte_cuotas_vencidas():
    db = get_db()
    hoy = date.today().isoformat()
    dias = int(request.args.get("dias", 30))
    fecha_hasta = (date.today() + timedelta(days=dias)).isoformat()

    # Cuotas vencidas
    vencidas = db.execute("""
        SELECT al.*, i.nombre || ' ' || i.apellido AS inquilino,
               pr.direccion AS propiedad, ea.nombre AS estado
        FROM alquileres al
        JOIN contratos c ON c.id = al.contrato_id
        JOIN inquilinos i ON i.id = c.inquilino_id
        JOIN propiedades pr ON pr.id = c.propiedad_id
        JOIN estados_alquiler ea ON ea.id = al.estado_id
        WHERE al.saldo > 0 AND al.fecha_vencimiento < ?
        ORDER BY al.fecha_vencimiento
    """, (hoy,)).fetchall()

    # Cuotas por vencer en los próximos N días
    por_vencer = db.execute("""
        SELECT al.*, i.nombre || ' ' || i.apellido AS inquilino,
               pr.direccion AS propiedad, ea.nombre AS estado
        FROM alquileres al
        JOIN contratos c ON c.id = al.contrato_id
        JOIN inquilinos i ON i.id = c.inquilino_id
        JOIN propiedades pr ON pr.id = c.propiedad_id
        JOIN estados_alquiler ea ON ea.id = al.estado_id
        WHERE al.saldo > 0 AND al.fecha_vencimiento BETWEEN ? AND ?
        ORDER BY al.fecha_vencimiento
    """, (hoy, fecha_hasta)).fetchall()

    db.close()
    return render_template("reportes/cuotas_vencidas.html",
                           vencidas=vencidas, por_vencer=por_vencer, dias=dias)


# ═══════════════════════════════════════════════════════════════════════════════
# USUARIOS
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/usuarios")
@login_required
@admin_required
def usuarios():
    db = get_db()
    rows = db.execute("""
        SELECT u.*, r.nombre AS rol FROM usuarios u
        JOIN roles r ON r.id = u.rol_id ORDER BY u.nombre
    """).fetchall()
    db.close()
    return render_template("usuarios/lista.html", usuarios=rows)


@app.route("/usuarios/nuevo", methods=["GET", "POST"])
@login_required
@admin_required
def nuevo_usuario():
    db = get_db()
    roles = db.execute("SELECT * FROM roles").fetchall()
    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip()
        password = request.form.get("password", "")
        if not usuario or not password:
            flash("Usuario y contraseña son obligatorios.", "warning")
            db.close()
            return render_template("usuarios/form.html", roles=roles, usuario=None)
        existe = db.execute(
            "SELECT id FROM usuarios WHERE usuario=?", (usuario,)
        ).fetchone()
        if existe:
            flash("El nombre de usuario ya existe.", "danger")
            db.close()
            return render_template("usuarios/form.html", roles=roles, usuario=None)
        db.execute("""
            INSERT INTO usuarios(nombre, usuario, password_hash, email, rol_id)
            VALUES (?,?,?,?,?)
        """, (
            request.form.get("nombre"),
            usuario,
            generate_password_hash(password, method="pbkdf2:sha256"),
            request.form.get("email"),
            request.form.get("rol_id"),
        ))
        db.commit()
        db.close()
        flash("Usuario creado.", "success")
        return redirect(url_for("usuarios"))
    db.close()
    return render_template("usuarios/form.html", roles=roles, usuario=None)


@app.route("/usuarios/<int:uid>/editar", methods=["GET", "POST"])
@login_required
@admin_required
def editar_usuario(uid):
    db = get_db()
    usuario = db.execute("SELECT * FROM usuarios WHERE id=?", (uid,)).fetchone()
    roles = db.execute("SELECT * FROM roles").fetchall()
    if not usuario:
        db.close()
        flash("Usuario no encontrado.", "danger")
        return redirect(url_for("usuarios"))
    if request.method == "POST":
        nueva_pass = request.form.get("password", "")
        hash_pass = generate_password_hash(nueva_pass, method="pbkdf2:sha256") if nueva_pass else usuario["password_hash"]
        db.execute("""
            UPDATE usuarios SET nombre=?, usuario=?, password_hash=?,
            email=?, rol_id=?, activo=? WHERE id=?
        """, (
            request.form.get("nombre"),
            request.form.get("usuario"),
            hash_pass,
            request.form.get("email"),
            request.form.get("rol_id"),
            1 if request.form.get("activo") else 0,
            uid,
        ))
        db.commit()
        db.close()
        flash("Usuario actualizado.", "success")
        return redirect(url_for("usuarios"))
    db.close()
    return render_template("usuarios/form.html", roles=roles, usuario=usuario)


@app.route("/usuarios/<int:uid>/eliminar", methods=["POST"])
@login_required
@admin_required
def eliminar_usuario(uid):
    if uid == session.get("user_id"):
        flash("No podés eliminar tu propio usuario.", "danger")
        return redirect(url_for("usuarios"))
    db = get_db()
    db.execute("UPDATE usuarios SET activo=0 WHERE id=?", (uid,))
    db.commit()
    db.close()
    flash("Usuario desactivado.", "success")
    return redirect(url_for("usuarios"))


# ─── API auxiliar: calcular mora en tiempo real ───────────────────────────────

@app.route("/api/alquiler/<int:alq_id>/mora")
@login_required
def api_mora(alq_id):
    """
    RN03 + RN04: devuelve días de atraso y recargo (Gs. 5.000 × días).
    La mora empieza el día siguiente al vencimiento.
    """
    db = get_db()
    hoy = date.today().isoformat()
    alq = db.execute("""
        SELECT al.saldo, al.fecha_vencimiento, c.recargo_mora_diario
        FROM alquileres al JOIN contratos c ON c.id = al.contrato_id
        WHERE al.id=?
    """, (alq_id,)).fetchone()
    db.close()
    if not alq:
        return jsonify({"error": "not found"}), 404
    recargo, dias = _calcular_recargo(alq["fecha_vencimiento"], hoy, alq["recargo_mora_diario"])
    return jsonify({
        "recargo":    recargo,
        "dias_mora":  dias,
        "saldo":      alq["saldo"],
        "total":      alq["saldo"] + recargo,
        "diario":     alq["recargo_mora_diario"],
    })


# ─── Inicio ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)
