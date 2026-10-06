"""
seed.py - Datos de prueba para el Sistema de Gestión de Cobros
Inmobiliaria Margherita S.A.

Ejecutar UNA VEZ después de inicializar la base de datos:
    python seed.py
"""

from database import get_db, init_db
from app import _generar_alquileres
from werkzeug.security import generate_password_hash
from datetime import date, timedelta
import random

def seed():
    init_db()
    db = get_db()

    print("Insertando datos de prueba...")

    # ── Propiedades ────────────────────────────────────────────────────────
    propiedades = [
        ("13-776-15", "Antonio Ortiz Mayans - Lambaré",   "Lambaré",   1, 2),
        ("14-201-07", "Mcal. López 1250 - Asunción",      "Asunción",  2, 2),
        ("15-088-22", "Av. Artigas 870 - Fernando",       "Fernando",  1, 2),
        ("16-340-11", "San Martín 455 - Luque",           "Luque",     3, 1),
        ("17-512-03", "Padre Cardozo 310 - San Lorenzo",  "San Lorenzo",1,1),
    ]
    prop_ids = []
    for cta, dir_, ciudad, tipo, estado in propiedades:
        cur = db.execute("""
            INSERT OR IGNORE INTO propiedades(cta_cte_central, direccion, ciudad, tipo_id, estado_id)
            VALUES (?,?,?,?,?)
        """, (cta, dir_, ciudad, tipo, estado))
        if cur.lastrowid:
            prop_ids.append(cur.lastrowid)
        else:
            row = db.execute("SELECT id FROM propiedades WHERE cta_cte_central=?", (cta,)).fetchone()
            prop_ids.append(row["id"])

    # ── Inquilinos ─────────────────────────────────────────────────────────
    inquilinos = [
        ("Demetrio",  "Jara",      "Carmen Aguilera",  "1234567-8",  "0981-111-222", "djara@gmail.com"),
        ("Rosa",      "Vera",      None,               "2345678-9",  "0991-333-444", "rvera@gmail.com"),
        ("Carlos",    "Benítez",   "Ana Benítez",      "3456789-0",  "0971-555-666", "cbenitez@gmail.com"),
        ("María",     "González",  None,               "4567890-1",  "0981-777-888", "mgonzalez@gmail.com"),
        ("Pablo",     "Sánchez",   "Laura Sánchez",    "5678901-2",  "0991-999-000", "psanchez@gmail.com"),
    ]
    inq_ids = []
    for nom, ape, cot, ruc, tel, mail in inquilinos:
        cur = db.execute("""
            INSERT OR IGNORE INTO inquilinos(nombre, apellido, cotitular, ruc_ci, telefono, email)
            VALUES (?,?,?,?,?,?)
        """, (nom, ape, cot, ruc, tel, mail))
        if cur.lastrowid:
            inq_ids.append(cur.lastrowid)
        else:
            row = db.execute("SELECT id FROM inquilinos WHERE ruc_ci=?", (ruc,)).fetchone()
            inq_ids.append(row["id"])

    # ── Operador de cobranzas ──────────────────────────────────────────────
    db.execute("""
        INSERT OR IGNORE INTO usuarios(nombre, usuario, password_hash, email, rol_id)
        VALUES ('Operador Cobranzas', 'operador', ?, 'operador@margherita.com', 2)
    """, (generate_password_hash("oper123", method="pbkdf2:sha256"),))

    db.commit()

    # ── Contratos (12 meses) ───────────────────────────────────────────────
    hoy = date.today()
    inicio = date(hoy.year - 1, hoy.month, 1)
    fin    = date(hoy.year,     hoy.month - 1 if hoy.month > 1 else 12,
                  28 if (hoy.month - 1) == 2 else 30) + timedelta(days=365//12*11)

    canonenes = [1_300_000, 900_000 + 600_000, 1_700_000, 1_100_000, 1_500_000]

    contrato_ids = []
    for i, (pid, iid, canon) in enumerate(zip(prop_ids, inq_ids, canonenes)):
        existente = db.execute(
            "SELECT id FROM contratos WHERE propiedad_id=? AND inquilino_id=?",
            (pid, iid)
        ).fetchone()
        if existente:
            contrato_ids.append(existente["id"])
            continue

        cur = db.execute("""
            INSERT INTO contratos(propiedad_id, inquilino_id, fecha_inicio, fecha_fin,
            canon_mensual, dias_periodo_pago, recargo_mora_diario, activo)
            VALUES (?,?,?,?,?,6,5000.0,1)
        """, (pid, iid,
              inicio.isoformat(),
              (inicio.replace(year=inicio.year + 1) - timedelta(days=1)).isoformat(),
              canon))
        cid = cur.lastrowid
        contrato_ids.append(cid)
        _generar_alquileres(db, cid)

    db.commit()

    # ── Pagos simulados ────────────────────────────────────────────────────
    # Obtener el id del usuario admin
    admin = db.execute("SELECT id FROM usuarios WHERE usuario='admin'").fetchone()
    uid = admin["id"]

    medio_ef  = db.execute("SELECT id FROM medios_pago WHERE nombre='Efectivo'").fetchone()["id"]
    medio_tr  = db.execute("SELECT id FROM medios_pago WHERE nombre='Transferencia bancaria'").fetchone()["id"]
    medio_dep = db.execute("SELECT id FROM medios_pago WHERE nombre='Depósito bancario'").fetchone()["id"]
    medios_rot = [medio_ef, medio_tr, medio_dep]

    tipo_total  = db.execute("SELECT id FROM tipos_pago WHERE nombre='Pago total'").fetchone()["id"]
    tipo_parc   = db.execute("SELECT id FROM tipos_pago WHERE nombre='Pago parcial'").fetchone()["id"]
    tipo_canc   = db.execute("SELECT id FROM tipos_pago WHERE nombre='Cancelación de saldo'").fetchone()["id"]

    estado_pagado  = db.execute("SELECT id FROM estados_alquiler WHERE nombre='Pagado'").fetchone()["id"]
    estado_parcial = db.execute("SELECT id FROM estados_alquiler WHERE nombre='Pagado parcial'").fetchone()["id"]

    factura_seq = [100]

    def next_recibo():
        row = db.execute("SELECT COALESCE(MAX(nro_recibo),0) FROM recibos").fetchone()[0]
        return row + 1

    def registrar_pago(alq_id, monto, medio_id, tipo_id, fecha, nuevo_saldo, nro_fact):
        cur = db.execute("""
            INSERT INTO pagos(alquiler_id, usuario_id, tipo_pago_id, medio_pago_id,
            monto_pagado, fecha_pago)
            VALUES (?,?,?,?,?,?)
        """, (alq_id, uid, tipo_id, medio_id, monto, fecha))
        pago_id = cur.lastrowid
        nro_rec = next_recibo()
        db.execute("""
            INSERT INTO recibos(nro_recibo, pago_id, nro_factura)
            VALUES (?,?,?)
        """, (nro_rec, pago_id, f"001-001-{nro_fact:07d}"))
        return pago_id

    # Pagar los primeros 10 alquileres de cada contrato con distintos escenarios
    for cid in contrato_ids:
        alqs = db.execute("""
            SELECT * FROM alquileres WHERE contrato_id=? ORDER BY periodo LIMIT 10
        """, (cid,)).fetchall()

        for idx, alq in enumerate(alqs):
            # Ya pagado
            ya_pagado = db.execute(
                "SELECT COUNT(*) FROM pagos WHERE alquiler_id=? AND anulado=0",
                (alq["id"],)
            ).fetchone()[0]
            if ya_pagado:
                continue

            canon = alq["monto"]
            medio = medios_rot[idx % 3]
            fecha = alq["fecha_vencimiento"]
            factura_seq[0] += 1

            if idx % 5 == 3:
                # Pago parcial primero (60% del canon)
                monto_parcial = round(canon * 0.6, 0)
                registrar_pago(alq["id"], monto_parcial, medio, tipo_parc, fecha,
                               canon - monto_parcial, factura_seq[0])
                db.execute("UPDATE alquileres SET saldo=?, estado_id=? WHERE id=?",
                           (canon - monto_parcial, estado_parcial, alq["id"]))
                db.commit()
                # Luego cancelar saldo
                factura_seq[0] += 1
                fecha2 = (date.fromisoformat(fecha) + timedelta(days=7)).isoformat()
                registrar_pago(alq["id"], canon - monto_parcial,
                               medio_tr, tipo_canc, fecha2, 0, factura_seq[0])
                db.execute("UPDATE alquileres SET saldo=0, estado_id=? WHERE id=?",
                           (estado_pagado, alq["id"]))
            else:
                # Pago total
                registrar_pago(alq["id"], canon, medio, tipo_total, fecha, 0, factura_seq[0])
                db.execute("UPDATE alquileres SET saldo=0, estado_id=? WHERE id=?",
                           (estado_pagado, alq["id"]))

            db.commit()

    print(f"✔ {len(contrato_ids)} contratos cargados.")
    print(f"✔ Datos de prueba insertados correctamente.")
    print()
    print("Credenciales de acceso:")
    print("  Admin     → usuario: admin      / contraseña: admin123")
    print("  Operador  → usuario: operador   / contraseña: oper123")

    db.close()

if __name__ == "__main__":
    seed()
