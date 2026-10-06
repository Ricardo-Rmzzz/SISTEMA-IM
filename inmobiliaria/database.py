"""
database.py - Inicialización y esquema completo de la base de datos SQLite
Sistema de Gestión de Cobros de Alquiler - Inmobiliaria Margherita S.A.
"""

import sqlite3
import os
from werkzeug.security import generate_password_hash

DB_PATH = os.path.join(os.path.dirname(__file__), "inmobiliaria.db")


def get_db():
    """Retorna una conexión a la base de datos con row_factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Crea todas las tablas si no existen e inserta datos maestros."""
    conn = get_db()
    c = conn.cursor()

    # ─── Catálogos ────────────────────────────────────────────────────────────

    c.executescript("""
        CREATE TABLE IF NOT EXISTS tipos_propiedad (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre  TEXT NOT NULL UNIQUE
        );

        CREATE TABLE IF NOT EXISTS estados_propiedad (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre  TEXT NOT NULL UNIQUE
        );

        CREATE TABLE IF NOT EXISTS estados_alquiler (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre  TEXT NOT NULL UNIQUE
        );

        CREATE TABLE IF NOT EXISTS medios_pago (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre  TEXT NOT NULL UNIQUE
        );

        CREATE TABLE IF NOT EXISTS tipos_pago (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre  TEXT NOT NULL UNIQUE   -- Pago total / Pago parcial / Cancelación de saldo
        );

        CREATE TABLE IF NOT EXISTS roles (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre  TEXT NOT NULL UNIQUE   -- Administrador / Operador de Cobranzas
        );
    """)

    # ─── Entidades principales ────────────────────────────────────────────────

    c.executescript("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre          TEXT    NOT NULL,
            usuario         TEXT    NOT NULL UNIQUE,
            password_hash   TEXT    NOT NULL,
            email           TEXT,
            rol_id          INTEGER NOT NULL REFERENCES roles(id),
            activo          INTEGER NOT NULL DEFAULT 1,
            creado_en       TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS propiedades (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            cta_cte_central     TEXT,
            direccion           TEXT    NOT NULL,
            ciudad              TEXT,
            tipo_id             INTEGER REFERENCES tipos_propiedad(id),
            estado_id           INTEGER REFERENCES estados_propiedad(id),
            descripcion         TEXT,
            creado_en           TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS inquilinos (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre          TEXT    NOT NULL,
            apellido        TEXT    NOT NULL,
            cotitular       TEXT,
            ruc_ci          TEXT,
            telefono        TEXT,
            email           TEXT,
            direccion       TEXT,
            creado_en       TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS contratos (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            propiedad_id        INTEGER NOT NULL REFERENCES propiedades(id),
            inquilino_id        INTEGER NOT NULL REFERENCES inquilinos(id),
            fecha_inicio        TEXT    NOT NULL,
            fecha_fin           TEXT    NOT NULL,
            canon_mensual       REAL    NOT NULL,
            dias_periodo_pago   INTEGER NOT NULL DEFAULT 6,    -- RN02: días para pagar desde inicio del período
            recargo_mora_diario REAL    NOT NULL DEFAULT 5000, -- RN04: Gs. por día de atraso
            activo              INTEGER NOT NULL DEFAULT 1,
            observaciones       TEXT,
            creado_en           TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
        );

        -- Un registro por cada cuota/período generado desde el contrato
        CREATE TABLE IF NOT EXISTS alquileres (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            contrato_id     INTEGER NOT NULL REFERENCES contratos(id),
            periodo         TEXT    NOT NULL,   -- 'YYYY-MM' p.ej. '2026-07'
            nro_cuota       INTEGER NOT NULL,   -- p.ej. 11
            total_cuotas    INTEGER NOT NULL,   -- p.ej. 12
            monto           REAL    NOT NULL,
            saldo           REAL    NOT NULL,
            estado_id       INTEGER NOT NULL REFERENCES estados_alquiler(id),
            fecha_vencimiento TEXT  NOT NULL,
            creado_en       TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
            UNIQUE(contrato_id, periodo)
        );

        -- Cada pago parcial o total de un alquiler
        CREATE TABLE IF NOT EXISTS pagos (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            alquiler_id     INTEGER NOT NULL REFERENCES alquileres(id),
            usuario_id      INTEGER NOT NULL REFERENCES usuarios(id),
            tipo_pago_id    INTEGER NOT NULL REFERENCES tipos_pago(id),
            medio_pago_id   INTEGER NOT NULL REFERENCES medios_pago(id),
            monto_pagado    REAL    NOT NULL,
            recargo_mora    REAL    NOT NULL DEFAULT 0.0,
            fecha_pago      TEXT    NOT NULL DEFAULT (date('now','localtime')),
            nro_cheque      TEXT,
            nro_deposito    TEXT,
            nro_transferencia TEXT,
            observaciones   TEXT,
            anulado         INTEGER NOT NULL DEFAULT 0,
            creado_en       TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
        );

        -- Un recibo correlativo por cada pago
        CREATE TABLE IF NOT EXISTS recibos (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            nro_recibo      INTEGER NOT NULL UNIQUE,  -- correlativo global
            pago_id         INTEGER NOT NULL UNIQUE REFERENCES pagos(id),
            nro_factura     TEXT,
            anulado         INTEGER NOT NULL DEFAULT 0,
            motivo_anulacion TEXT,
            anulado_por_id  INTEGER REFERENCES usuarios(id),
            anulado_en      TEXT,
            creado_en       TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
        );
    """)

    # ─── Datos maestros ───────────────────────────────────────────────────────

    c.executescript("""
        INSERT OR IGNORE INTO tipos_propiedad(nombre) VALUES
            ('Departamento'),('Casa'),('Local Comercial'),('Oficina'),('Galpon');

        INSERT OR IGNORE INTO estados_propiedad(nombre) VALUES
            ('Disponible'),('Alquilada'),('En mantenimiento');

        INSERT OR IGNORE INTO estados_alquiler(nombre) VALUES
            ('Pendiente'),('Pagado parcial'),('Pagado'),('Vencido'),('En mora');

        INSERT OR IGNORE INTO medios_pago(nombre) VALUES
            ('Efectivo'),('Depósito bancario'),('Transferencia bancaria');

        INSERT OR IGNORE INTO tipos_pago(nombre) VALUES
            ('Pago total'),('Pago parcial'),('Cancelación de saldo');

        INSERT OR IGNORE INTO roles(nombre) VALUES
            ('Administrador'),('Operador de Cobranzas');
    """)

    # ─── Usuario administrador por defecto ────────────────────────────────────
    admin_hash = generate_password_hash("admin123", method="pbkdf2:sha256")
    c.execute("""
        INSERT OR IGNORE INTO usuarios(nombre, usuario, password_hash, email, rol_id)
        VALUES ('Administrador', 'admin', ?, 'admin@margherita.com', 1)
    """, (admin_hash,))

    conn.commit()
    conn.close()
    print("Base de datos inicializada correctamente.")


if __name__ == "__main__":
    init_db()
