import os
import sqlite3
import random
import string
from urllib.parse import urlparse

# Tenta importar psycopg2 para suporte ao Postgres (Render)
try:
    import psycopg2
    import psycopg2.extras
    HAS_PG = True
except ImportError:
    HAS_PG = False

DATABASE_SQLITE = os.path.join(os.path.dirname(__file__), 'barbearia.db')
DATABASE_URL = os.environ.get('DATABASE_URL') or os.environ.get('EXTERNAL_DATABASE_URL')

if DATABASE_URL:
    # Correção para URLs antigas do heroku/render que usam postgres:// em vez de postgresql://
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    
    # Render e outros serviços Gerenciados EXIGEM SSL.
    # Se não houver sslmode na URL, nós forçamos.
    if "sslmode=" not in DATABASE_URL:
        if "?" in DATABASE_URL:
            DATABASE_URL += "&sslmode=require"
        else:
            DATABASE_URL += "?sslmode=require"
            
    print(f"DEBUG: DATABASE_URL configurada (SSL forçado).")
else:
    print("DEBUG: DATABASE_URL NÃO detectada. Usando SQLite local.")

class CursorWrapper:
    def __init__(self, cursor, is_pg):
        self.cursor = cursor
        self.is_pg = is_pg
        self._lastrowid = None

    def execute(self, sql, params=()):
        if self.is_pg:
            sql = sql.replace('?', '%s')
            if sql.strip().upper().startswith('INSERT') and 'RETURNING' not in sql.upper():
                sql += ' RETURNING id'
        
        try:
            self.cursor.execute(sql, params)
        except Exception as e:
            print(f"SQL ERROR: {e}\nQUERY: {sql}\nPARAMS: {params}")
            raise e
        
        if self.is_pg and sql.strip().upper().startswith('INSERT'):
            try:
                self._lastrowid = self.cursor.fetchone()[0]
            except:
                self._lastrowid = None
        else:
            try:
                self._lastrowid = self.cursor.lastrowid
            except:
                self._lastrowid = None
        return self

    @property
    def lastrowid(self):
        return self._lastrowid

    def fetchone(self):
        return self.cursor.fetchone()

    def fetchall(self):
        return self.cursor.fetchall()

    def __getattr__(self, name):
        return getattr(self.cursor, name)

class DBWrapper:
    def __init__(self, conn, is_pg):
        self.conn = conn
        self.is_pg = is_pg

    def cursor(self):
        return CursorWrapper(self.conn.cursor(), self.is_pg)

    def execute(self, sql, params=()):
        return self.cursor().execute(sql, params)

    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.close()

    def fetchone(self, sql, params=()):
        return self.execute(sql, params).fetchone()

    def fetchall(self, sql, params=()):
        return self.execute(sql, params).fetchall()

def get_db():
    # Prioridade para Postgres se a URL estiver presente
    if DATABASE_URL:
        if not HAS_PG:
            raise RuntimeError("ERRO: psycopg2 não instalado. Adicione 'psycopg2-binary' ao requirements.txt")
        
        try:
            conn = psycopg2.connect(DATABASE_URL)
            conn.cursor_factory = psycopg2.extras.DictCursor
            return DBWrapper(conn, True)
        except Exception as e:
            # Captura o erro exato para mostrar no painel de status
            error_msg = str(e)
            print(f"\n!!! ERRO DE CONEXÃO COM POSTGRES !!!\n{error_msg}\n")
            # Armazenamos o erro globalmente para a API de status ler
            os.environ['LAST_DB_ERROR'] = error_msg
            raise e
    
    # Se NÃO houver DATABASE_URL, assume-se modo desenvolvimento (SQLite)
    print("AVISO: Usando SQLite local (DADOS SERÃO PERDIDOS NO RENDER).")
    conn = sqlite3.connect(DATABASE_SQLITE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return DBWrapper(conn, False)

def init_db():
    conn = get_db()
    cur = conn.cursor()

    is_pg = (DATABASE_URL and HAS_PG)

    # Note: No Postgres usamos SERIAL em vez de AUTOINCREMENT
    # e CURRENT_TIMESTAMP em vez de datetime('now','localtime')
    
    if is_pg:
        # Funções de compatibilidade para PostgreSQL
        cur.execute("CREATE OR REPLACE FUNCTION julianday(t timestamp) RETURNS float AS $$ SELECT extract(julian from t); $$ LANGUAGE SQL;")
        cur.execute("CREATE OR REPLACE FUNCTION julianday(t date) RETURNS float AS $$ SELECT extract(julian from t); $$ LANGUAGE SQL;")
        cur.execute("""
            CREATE OR REPLACE FUNCTION julianday(t text) RETURNS float AS $$
                BEGIN
                    IF t = 'now' THEN RETURN extract(julian from current_timestamp);
                    ELSE RETURN extract(julian from t::timestamp);
                    END IF;
                END;
            $$ LANGUAGE plpgsql;
        """)

        # Schema para PostgreSQL (Executado um por um para evitar erros globais)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS barbearias (
                id          SERIAL PRIMARY KEY,
                nome        TEXT    NOT NULL,
                codigo      TEXT    NOT NULL UNIQUE,
                criado_em   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS config (
                chave TEXT PRIMARY KEY,
                valor TEXT NOT NULL
            )""")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id          SERIAL PRIMARY KEY,
                barbearia_id INTEGER REFERENCES barbearias(id),
                nome        TEXT    NOT NULL,
                email       TEXT    NOT NULL UNIQUE,
                senha_hash  TEXT    NOT NULL,
                is_admin    INTEGER NOT NULL DEFAULT 0,
                ativo       INTEGER NOT NULL DEFAULT 1,
                criado_em   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS clientes (
                id          SERIAL PRIMARY KEY,
                barbearia_id INTEGER REFERENCES barbearias(id),
                nome        TEXT    NOT NULL,
                telefone    TEXT,
                ultima_visita DATE,
                criado_em   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS atendimentos (
                id          SERIAL PRIMARY KEY,
                barbearia_id INTEGER REFERENCES barbearias(id),
                cliente_id  INTEGER NOT NULL REFERENCES clientes(id),
                usuario_id  INTEGER REFERENCES usuarios(id),
                servico     TEXT    NOT NULL,
                valor       NUMERIC NOT NULL,
                data        DATE    NOT NULL DEFAULT CURRENT_DATE,
                hora        TEXT,
                status      TEXT    DEFAULT 'agendado',
                criado_em   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")
    else:
        # Schema para SQLite (Legado)
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

    # Migrações e verificações de coluna (Simplificado para o novo setup)
    # Em produção (Postgres), as tabelas já serão criadas corretamente.
    
    conn.commit()
    conn.close()
