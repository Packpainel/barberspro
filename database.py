import sqlite3
import os
import random
import string

DATABASE = os.path.join(os.path.dirname(__file__), 'barbearia.db')


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.executescript("""
        CREATE TABLE IF NOT EXISTS barbearias (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            nome        TEXT    NOT NULL,
            codigo      TEXT    NOT NULL UNIQUE,
            criado_em   DATETIME DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS config (
            chave TEXT PRIMARY KEY,
            valor TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS usuarios (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            barbearia_id INTEGER REFERENCES barbearias(id),
            nome        TEXT    NOT NULL,
            email       TEXT    NOT NULL UNIQUE,
            senha_hash  TEXT    NOT NULL,
            is_admin    INTEGER NOT NULL DEFAULT 0,
            ativo       INTEGER NOT NULL DEFAULT 1,
            criado_em   DATETIME DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS clientes (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            barbearia_id INTEGER REFERENCES barbearias(id),
            nome        TEXT    NOT NULL,
            telefone    TEXT,
            ultima_visita DATE,
            criado_em   DATETIME DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS atendimentos (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            barbearia_id INTEGER REFERENCES barbearias(id),
            cliente_id  INTEGER NOT NULL REFERENCES clientes(id),
            usuario_id  INTEGER REFERENCES usuarios(id),
            servico     TEXT    NOT NULL,
            valor       REAL    NOT NULL,
            data        DATE    NOT NULL DEFAULT (date('now','localtime')),
            hora        TEXT    DEFAULT (time('now','localtime')),
            status      TEXT    DEFAULT 'agendado',
            criado_em   DATETIME DEFAULT (datetime('now','localtime'))
        );
    """)

    # Migração para Multi-Tenant SaaS
    colunas_u = [r[1] for r in cur.execute("PRAGMA table_info(usuarios)").fetchall()]
    colunas_c = [r[1] for r in cur.execute("PRAGMA table_info(clientes)").fetchall()]
    colunas_a = [r[1] for r in cur.execute("PRAGMA table_info(atendimentos)").fetchall()]
    
    if 'hora' not in colunas_a:
        try:
            cur.executescript("""
                ALTER TABLE atendimentos ADD COLUMN hora TEXT;
                UPDATE atendimentos SET hora = time('now','localtime') WHERE hora IS NULL;
            """)
        except Exception as e:
            print("Migration DB Error (hora):", e)

    if 'status' not in colunas_a:
        try:
            cur.executescript("""
                ALTER TABLE atendimentos ADD COLUMN status TEXT DEFAULT 'agendado';
                UPDATE atendimentos SET status = 'concluido' WHERE status IS NULL;
            """)
        except Exception as e:
            print("Migration DB Error (status):", e)

    
    if 'barbearia_id' not in colunas_u or 'barbearia_id' not in colunas_c or 'barbearia_id' not in colunas_a:
        # Tenta pegar da config
        row = cur.execute("SELECT valor FROM config WHERE chave='nome_barbearia'").fetchone() if 'config' in [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()] else None
        nome_b = row[0] if row else "Minha Barbearia"
        
        # Pega a barbearia default (id 1) ou cria se nao existir
        b_ref = cur.execute("SELECT id FROM barbearias LIMIT 1").fetchone()
        if not b_ref:
            codigo = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            cur.execute("INSERT INTO barbearias(nome, codigo) VALUES(?, ?)", (nome_b, codigo))
            b_id = cur.lastrowid
        else:
            b_id = b_ref[0]
            
        try:
            if 'barbearia_id' not in colunas_u:
                cur.executescript(f"ALTER TABLE usuarios ADD COLUMN barbearia_id INTEGER; UPDATE usuarios SET barbearia_id = {b_id};")
            if 'barbearia_id' not in colunas_c:
                cur.executescript(f"ALTER TABLE clientes ADD COLUMN barbearia_id INTEGER; UPDATE clientes SET barbearia_id = {b_id};")
            if 'barbearia_id' not in colunas_a:
                cur.executescript(f"ALTER TABLE atendimentos ADD COLUMN barbearia_id INTEGER; UPDATE atendimentos SET barbearia_id = {b_id};")
        except Exception as e:
            print("Migration DB Error:", e)



    # Migração para usuario_id no caso de bancos bem antigos
    colunas_a = [r[1] for r in cur.execute("PRAGMA table_info(atendimentos)").fetchall()]
    if 'usuario_id' not in colunas_a:
        try:
            cur.execute("ALTER TABLE atendimentos ADD COLUMN usuario_id INTEGER REFERENCES usuarios(id)")
        except:
            pass

    conn.commit()
    conn.close()
