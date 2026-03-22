import os
import secrets
import random
import string
from datetime import date, timedelta, datetime
from functools import wraps

from flask import (Flask, render_template, request, jsonify,
                   redirect, url_for, flash, abort, send_from_directory)
from flask_login import (LoginManager, UserMixin, login_user,
                         logout_user, login_required, current_user)
from werkzeug.security import generate_password_hash, check_password_hash

from database import init_db, get_db, HAS_PG, DATABASE_URL

# ─────────────────────────────────────────────
# App setup
# ─────────────────────────────────────────────
BASE_DIR = os.path.dirname(__file__)

# No app.py
_KEY_FILE = os.path.join(BASE_DIR, '.secret_key')
_secret = os.environ.get('FLASK_SECRET_KEY')
if not _secret:
    if os.path.exists(_KEY_FILE):
        with open(_KEY_FILE) as f:
            _secret = f.read().strip()
    else:
        _secret = secrets.token_hex(32)
        with open(_KEY_FILE, 'w') as f:
            f.write(_secret)

app = Flask(__name__, template_folder='.')
app.secret_key = _secret

login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Faça login para acessar sua barbearia.'

@app.route('/style.css')
def serve_css():
    return send_from_directory('.', 'style.css')

@app.route('/main.js')
def serve_js():
    return send_from_directory('.', 'main.js')

try:
    with app.app_context():
        init_db()
except Exception as e:
    print(f"FALHA NA INICIALIZAÇÃO DO BANCO: {e}")
    # Não encerramos o processo aqui para permitir que o Render veja os logs, 
    # mas o app provavelmente vai falhar nas requisições.


# ─────────────────────────────────────────────
# User model for flask-login (Multi-Tenant)
# ─────────────────────────────────────────────
class Usuario(UserMixin):
    def __init__(self, row):
        self.id = row['id']
        self.barbearia_id = row['barbearia_id']
        self.nome = row['nome']
        self.email = row['email']
        self.is_admin = bool(row['is_admin'])
        
        # Dados da Barbearia injetados pelo JOIN
        self.barbearia_nome = row['barbearia_nome'] if 'barbearia_nome' in row.keys() else 'Barbearia'
        self.barbearia_codigo = row['barbearia_codigo'] if 'barbearia_codigo' in row.keys() else ''

    def get_id(self):
        return str(self.id)


@login_manager.user_loader
def load_user(user_id):
    db = get_db()
    row = db.execute(
        """SELECT u.*, b.nome AS barbearia_nome, b.codigo AS barbearia_codigo
           FROM usuarios u
           JOIN barbearias b ON b.id = u.barbearia_id
           WHERE u.id=? AND u.ativo=1""", (user_id,)
    ).fetchone()
    db.close()
    return Usuario(row) if row else None


@app.route('/api/status')
def api_status():
    error = os.environ.get('LAST_DB_ERROR', '')
    try:
        db = get_db()
        is_pg = db.is_pg
        db.close()
        return jsonify({
            'database': 'PostgreSQL' if is_pg else 'SQLite (DADOS TEMPORÁRIOS)',
            'has_pg_driver': HAS_PG,
            'has_db_url': bool(DATABASE_URL),
            'error': error
        })
    except Exception as e:
        return jsonify({
            'database': 'ERRO DE CONEXÃO',
            'has_pg_driver': HAS_PG,
            'has_db_url': bool(DATABASE_URL),
            'error': str(e)
        })

# Decorador para logar erros no Render
def log_errors(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as e:
            print(f"ERRO NA ROTA {request.path}: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({'erro': str(e)}), 500
    return decorated

# Decorator para exigir admin
def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated


# ─────────────────────────────────────────────
# Cadastro SaaS: Barbearia (Tenant) e Barbeiro
# ─────────────────────────────────────────────
@app.route('/cadastro-barbearia', methods=['GET', 'POST'])
def cadastro_barbearia():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        nome_barb = request.form.get('nome_barbearia', '').strip()
        nome      = request.form.get('nome', '').strip()
        email     = request.form.get('email', '').strip().lower()
        senha     = request.form.get('senha', '')
        
        erros = []
        if not nome_barb: erros.append('Nome da barbearia é obrigatório.')
        if not nome:      erros.append('Seu nome é obrigatório.')
        if not email:     erros.append('E-mail é obrigatório.')
        if len(senha) < 6: erros.append('A senha deve ter pelo menos 6 caracteres.')

        if erros:
            return render_template('cadastro_barbearia.html', erros=erros, form=request.form)

        db = get_db()
        if db.execute("SELECT id FROM usuarios WHERE email=?", (email,)).fetchone():
            db.close()
            return render_template('cadastro_barbearia.html', erros=['E-mail já está em uso.'], form=request.form)

        # Gera código único de 6 letras/números
        codigo = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        
        # Cria a Barbearia
        cur = db.execute("INSERT INTO barbearias(nome, codigo) VALUES(?,?)", (nome_barb, codigo))
        b_id = cur.lastrowid
        
        # Cria o Admin
        db.execute(
            "INSERT INTO usuarios(barbearia_id, nome, email, senha_hash, is_admin) VALUES(?,?,?,?,1)",
            (b_id, nome, email, generate_password_hash(senha))
        )
        db.commit()
        
        # Auto-login
        row = db.execute(
            """SELECT u.*, b.nome AS barbearia_nome, b.codigo AS barbearia_codigo
               FROM usuarios u JOIN barbearias b ON b.id=u.barbearia_id WHERE u.email=?""", 
            (email,)
        ).fetchone()
        db.close()
        
        flash('Sua barbearia foi criada com sucesso! 🎉', 'success')
        login_user(Usuario(row), remember=True)
        return redirect(url_for('index'))

    return render_template('cadastro_barbearia.html', erros=[], form={})


@app.route('/cadastro-barbeiro', methods=['GET', 'POST'])
def cadastro_barbeiro():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        codigo = request.form.get('codigo', '').strip().upper()
        nome   = request.form.get('nome', '').strip()
        email  = request.form.get('email', '').strip().lower()
        senha  = request.form.get('senha', '')
        
        erros = []
        if not codigo: erros.append('Código da barbearia é obrigatório.')
        if not nome:   erros.append('Seu nome é obrigatório.')
        if not email:  erros.append('E-mail é obrigatório.')
        if len(senha) < 6: erros.append('A senha deve ter pelo menos 6 caracteres.')

        if erros:
            return render_template('cadastro_barbeiro.html', erros=erros, form=request.form)

        db = get_db()
        barbearia = db.execute("SELECT id, nome FROM barbearias WHERE codigo=?", (codigo,)).fetchone()
        
        if not barbearia:
            db.close()
            return render_template('cadastro_barbeiro.html', erros=['Código da barbearia inválido ou não encontrado.'], form=request.form)
            
        if db.execute("SELECT id FROM usuarios WHERE email=?", (email,)).fetchone():
            db.close()
            return render_template('cadastro_barbeiro.html', erros=['E-mail já está em uso.'], form=request.form)

        # Cria o Barbeiro
        db.execute(
            "INSERT INTO usuarios(barbearia_id, nome, email, senha_hash, is_admin) VALUES(?,?,?,?,0)",
            (barbearia['id'], nome, email, generate_password_hash(senha))
        )
        db.commit()
        
        # Auto-login
        row = db.execute(
            """SELECT u.*, b.nome AS barbearia_nome, b.codigo AS barbearia_codigo
               FROM usuarios u JOIN barbearias b ON b.id=u.barbearia_id WHERE u.email=?""", 
            (email,)
        ).fetchone()
        db.close()
        
        flash(f'Você entrou na equipe da {barbearia["nome"]}! ✂️', 'success')
        login_user(Usuario(row), remember=True)
        return redirect(url_for('index'))

    return render_template('cadastro_barbeiro.html', erros=[], form={})


# Retirado o redirecionamento global /setup
# ─────────────────────────────────────────────
# LOGIN / LOGOUT
# ─────────────────────────────────────────────
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        senha = request.form.get('senha', '')
        db = get_db()
        row = db.execute(
            """SELECT u.*, b.nome AS barbearia_nome, b.codigo AS barbearia_codigo
               FROM usuarios u 
               JOIN barbearias b ON b.id = u.barbearia_id
               WHERE u.email=? AND u.ativo=1""", (email,)
        ).fetchone()
        db.close()

        if row and check_password_hash(row['senha_hash'], senha):
            login_user(Usuario(row), remember=True)
            next_page = request.args.get('next') or url_for('index')
            return redirect(next_page)

        flash('E-mail ou senha incorretos.', 'error')

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


# ─────────────────────────────────────────────
# VIEWS (páginas protegidas)
# ─────────────────────────────────────────────
@app.route('/')
@login_required
def index():
    return render_template('index.html')


@app.route('/clientes')
@login_required
def clientes():
    return render_template('clientes.html')


@app.route('/agenda')
@login_required
def agenda():
    return render_template('agenda.html')

# ─────────────────────────────────────────────
# VIEW — Agendamento Público (Vitrine)
# ─────────────────────────────────────────────
@app.route('/b/<codigo>')
def agendamento_publico(codigo):
    db = get_db()
    barbearia = db.execute("SELECT id, nome, codigo FROM barbearias WHERE codigo=?", (codigo,)).fetchone()
    if not barbearia:
        db.close()
        abort(404)
    barbeiros = db.execute("SELECT id, nome FROM usuarios WHERE barbearia_id=?", (barbearia['id'],)).fetchall()
    db.close()
    return render_template('agendamento_publico.html', barbearia=barbearia, barbeiros=barbeiros)

# ─────────────────────────────────────────────

@app.route('/novo-atendimento')
@login_required
def novo_atendimento():
    return render_template('novo_atendimento.html')


@app.route('/historico')
@login_required
def historico():
    return render_template('historico.html')


@app.route('/admin/barbeiros')
@login_required
@admin_required
def admin_barbeiros():
    return render_template('admin_barbeiros.html')


# ─────────────────────────────────────────────
# API — Dashboard
# ─────────────────────────────────────────────
@app.route('/api/dashboard')
@login_required
@log_errors
def api_dashboard():
    db = get_db()
    b_id = current_user.barbearia_id
    hoje = date.today()
    inicio_mes = hoje.replace(day=1).isoformat()
    limite_inativo = (hoje - timedelta(days=30)).isoformat()

    row = db.execute(
        "SELECT COALESCE(SUM(valor),0) AS fat, COUNT(*) AS qtd "
        "FROM atendimentos WHERE data >= ? AND barbearia_id=? AND status='concluido'",
        (inicio_mes, b_id)
    ).fetchone()
    faturamento_mes = row['fat']
    atendimentos_mes = row['qtd']

    ativos = db.execute(
        "SELECT COUNT(*) AS c FROM clientes WHERE CAST(ultima_visita AS DATE) >= CAST(? AS DATE) AND barbearia_id=CAST(? AS INTEGER)",
        (limite_inativo, b_id)
    ).fetchone()['c']

    inativos = db.execute(
        "SELECT COUNT(*) AS c FROM clientes "
        "WHERE (CAST(ultima_visita AS DATE) < CAST(? AS DATE) AND ultima_visita IS NOT NULL) AND barbearia_id=CAST(? AS INTEGER)",
        (limite_inativo, b_id)
    ).fetchone()['c']

    lista_inativos = db.execute(
        """SELECT c.id, c.nome, c.telefone, c.ultima_visita,
                  CAST(julianday('now') - julianday(CAST(c.ultima_visita AS TEXT)) AS INTEGER) AS dias_ausente
           FROM clientes c
           WHERE (CAST(c.ultima_visita AS DATE) < CAST(? AS DATE) AND c.ultima_visita IS NOT NULL) AND c.barbearia_id=CAST(? AS INTEGER)
           ORDER BY dias_ausente DESC NULLS LAST
           LIMIT 20""",
        (limite_inativo, b_id)
    ).fetchall()

    db.close()
    return jsonify({
        'faturamento_mes': faturamento_mes,
        'atendimentos_mes': atendimentos_mes,
        'clientes_ativos': ativos,
        'clientes_inativos': inativos,
        'lista_inativos': [dict(r) for r in lista_inativos]
    })


# ─────────────────────────────────────────────
# API — Clientes
# ─────────────────────────────────────────────
@app.route('/api/clientes', methods=['GET', 'POST'])
@login_required
@log_errors
def api_clientes():
    db = get_db()
    b_id = current_user.barbearia_id

    if request.method == 'POST':
        data = request.get_json()
        nome     = (data.get('nome') or '').strip()
        telefone = (data.get('telefone') or '').strip()
        if not nome:
            return jsonify({'erro': 'Nome é obrigatório'}), 400
            
        cur = db.execute(
            "INSERT INTO clientes(barbearia_id, nome, telefone) VALUES(?,?,?)", 
            (b_id, nome, telefone)
        )
        db.commit()
        novo_id = cur.lastrowid
        db.close()
        return jsonify({'id': novo_id, 'nome': nome, 'telefone': telefone}), 201

    limite_inativo = (date.today() - timedelta(days=30)).isoformat()
    rows = db.execute(
        """SELECT id, nome, telefone, ultima_visita,
                  CASE WHEN CAST(ultima_visita AS DATE) >= CAST(? AS DATE) THEN 'ativo' ELSE 'inativo' END AS status
           FROM clientes WHERE barbearia_id=CAST(? AS INTEGER) ORDER BY LOWER(nome)""",
        (limite_inativo, b_id)
    ).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/clientes/<int:cid>', methods=['GET', 'PUT', 'DELETE'])
@login_required
@log_errors
def api_cliente_detalhe(cid):
    db = get_db()
    b_id = current_user.barbearia_id
    cliente = db.execute("SELECT * FROM clientes WHERE id=? AND barbearia_id=?", (cid, b_id)).fetchone()
    if not cliente:
        db.close()
        return jsonify({'erro': 'Cliente não encontrado'}), 404

    if request.method == 'GET':
        db.close()
        return jsonify(dict(cliente))

    if request.method == 'PUT':
        data = request.get_json()
        nome     = (data.get('nome') or '').strip()
        telefone = (data.get('telefone') or '').strip()
        if not nome:
            return jsonify({'erro': 'Nome é obrigatório'}), 400
        db.execute("UPDATE clientes SET nome=?, telefone=? WHERE id=? AND barbearia_id=?", (nome, telefone, cid, b_id))
        db.commit()
        db.close()
        return jsonify({'ok': True})

    if request.method == 'DELETE':
        if not current_user.is_admin:
            return jsonify({'erro': 'Apenas admins podem excluir clientes'}), 403
        db.execute("DELETE FROM atendimentos WHERE cliente_id=? AND barbearia_id=?", (cid, b_id))
        db.execute("DELETE FROM clientes WHERE id=? AND barbearia_id=?", (cid, b_id))
        db.commit()
        db.close()
        return jsonify({'ok': True})


# ─────────────────────────────────────────────
# API — Atendimentos
# ─────────────────────────────────────────────
@app.route('/api/atendimentos', methods=['GET', 'POST'])
@login_required
@log_errors
def api_atendimentos():
    db = get_db()
    b_id = current_user.barbearia_id

    if request.method == 'POST':
        data       = request.get_json()
        cliente_id = data.get('cliente_id')
        servico    = (data.get('servico') or '').strip()
        valor      = data.get('valor')
        data_atend = data.get('data') or date.today().isoformat()
        hora_atend = data.get('hora') or datetime.now().strftime("%H:%M")

        if not cliente_id or not servico or valor is None:
            return jsonify({'erro': 'cliente_id, servico e valor são obrigatórios'}), 400
        try:
            valor = float(valor)
        except (ValueError, TypeError):
            return jsonify({'erro': 'Valor inválido'}), 400

        # Verifica se o cliente pertence à barbearia
        if not db.execute("SELECT id FROM clientes WHERE id=? AND barbearia_id=?", (cliente_id, b_id)).fetchone():
            return jsonify({'erro': 'Cliente inválido'}), 400

        db.execute(
            "INSERT INTO atendimentos(barbearia_id, cliente_id, usuario_id, servico, valor, data, hora, status) VALUES(?,?,?,?,?,?,?,?)",
            (b_id, cliente_id, current_user.id, servico, valor, data_atend, hora_atend, 'agendado')
        )
        db.commit()
        db.close()
        return jsonify({'ok': True}), 201

    rows = db.execute(
        """SELECT a.id, a.servico, a.valor, a.data, a.hora,
                  c.nome AS cliente_nome, u.nome AS barbeiro_nome
           FROM atendimentos a
           JOIN clientes c ON c.id = a.cliente_id
           LEFT JOIN usuarios u ON u.id = a.usuario_id
           WHERE a.barbearia_id=?
           ORDER BY a.data DESC, a.hora DESC, a.id DESC LIMIT 100""", (b_id,)
    ).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

# ─────────────────────────────────────────────
# API — Agendamento Público (Self-Service)
# ─────────────────────────────────────────────
@app.route('/api/public/horarios')
def api_public_horarios():
    codigo = request.args.get('codigo')
    data_str = request.args.get('data')
    barbeiro_id = request.args.get('barbeiro_id')
    if not codigo or not data_str or not barbeiro_id: return jsonify([])

    db = get_db()
    b = db.execute("SELECT id FROM barbearias WHERE codigo=?", (codigo,)).fetchone()
    if not b: return jsonify([])

    # Gerar slots de 30 em 30 min (09:00 até 19:30)
    base_slots = []
    for h in range(9, 20):
        base_slots.append(f"{h:02d}:00")
        base_slots.append(f"{h:02d}:30")

    # Buscar ocupados desse barbeiro específico
    occupied = db.execute(
        "SELECT hora FROM atendimentos WHERE barbearia_id=? AND data=? AND usuario_id=? AND status!='cancelado'",
        (b['id'], data_str, int(barbeiro_id))
    ).fetchall()
    
    occ_times = [r['hora'][:5] for r in occupied if r['hora']]
    free_slots = [s for s in base_slots if s not in occ_times]
    db.close()
    return jsonify(free_slots)

@app.route('/api/public/agendar', methods=['POST'])
def api_public_agendar():
    data = request.json
    codigo = data.get('codigo')
    barbeiro_id = data.get('barbeiro_id')
    nome = (data.get('nome') or '').strip()
    telefone = (data.get('telefone') or '').strip()
    servico = data.get('servico')
    data_atend = data.get('data')
    hora = data.get('hora')

    if not all([codigo, barbeiro_id, nome, telefone, servico, data_atend, hora]):
        return jsonify({'erro': 'Preencha todos os campos.'}), 400

    db = get_db()
    b = db.execute("SELECT id FROM barbearias WHERE codigo=?", (codigo,)).fetchone()
    if not b: return jsonify({'erro': 'Barbearia inválida.'}), 404
    b_id = b['id']

    # Criar ou achar cliente
    row_c = db.execute("SELECT id FROM clientes WHERE telefone=? AND barbearia_id=?", (telefone, b_id)).fetchone()
    if row_c:
        cliente_id = row_c['id']
    else:
        cur_c = db.execute("INSERT INTO clientes (nome, telefone, barbearia_id) VALUES (?,?,?)", (nome, telefone, b_id))
        cliente_id = cur_c.lastrowid

    # Agendar
    db.execute(
        "INSERT INTO atendimentos(barbearia_id, cliente_id, usuario_id, servico, valor, data, hora, status) VALUES(?,?,?,?,?,?,?,?)",
        (b_id, cliente_id, int(barbeiro_id), servico, 0.0, data_atend, hora, 'agendado')
    )
    db.commit()
    db.close()
    return jsonify({'ok': True})


# ─────────────────────────────────────────────
# API — Concluir Atendimento
# ─────────────────────────────────────────────
@app.route('/api/atendimentos/<int:atend_id>/concluir', methods=['POST'])
@login_required
@log_errors
def api_atendimento_concluir(atend_id):
    data = request.json or {}
    valor = data.get('valor')
    db = get_db()
    b_id = current_user.barbearia_id
    
    if valor is not None:
        db.execute("UPDATE atendimentos SET status='concluido', valor=?, usuario_id=COALESCE(usuario_id, ?) WHERE id=? AND barbearia_id=?", (valor, current_user.id, atend_id, b_id))
    else:
        db.execute("UPDATE atendimentos SET status='concluido', usuario_id=COALESCE(usuario_id, ?) WHERE id=? AND barbearia_id=?", (current_user.id, atend_id, b_id))
        
    # Updates the last visit
    atend = db.execute("SELECT cliente_id, data FROM atendimentos WHERE id=?", (atend_id,)).fetchone()
    if atend:
        db.execute("UPDATE clientes SET ultima_visita=? WHERE id=? AND barbearia_id=? AND (ultima_visita IS NULL OR ultima_visita < ?)",
                   (atend['data'], atend['cliente_id'], b_id, atend['data']))
                   
    db.commit()
    db.close()
    return jsonify({'ok': True})


# ─────────────────────────────────────────────
# API — Agenda do Dia
# ─────────────────────────────────────────────
@app.route('/api/atendimentos/dia')
@login_required
@log_errors
def api_atendimentos_dia():
    db = get_db()
    b_id = current_user.barbearia_id
    dia = request.args.get('data') or date.today().isoformat()

    rows = db.execute(
        """SELECT a.id, a.servico, a.valor, a.data, a.hora, a.status,
                  c.nome AS cliente_nome, c.telefone AS cliente_telefone, u.nome AS barbeiro_nome
           FROM atendimentos a
           JOIN clientes c ON c.id = a.cliente_id
           LEFT JOIN usuarios u ON u.id = a.usuario_id
           WHERE a.barbearia_id=? AND a.data=?
           ORDER BY a.hora ASC, a.id ASC""", (b_id, dia)
    ).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])


# ─────────────────────────────────────────────
# API — Histórico
# ─────────────────────────────────────────────
@app.route('/api/historico')
@login_required
@log_errors
def api_historico():
    db = get_db()
    b_id = current_user.barbearia_id
    inicio = request.args.get('inicio') or date.today().replace(day=1).isoformat()
    fim    = request.args.get('fim')    or date.today().isoformat()

    rows = db.execute(
        """SELECT a.id, a.servico, a.valor, a.data, a.hora, a.status,
                  c.nome AS cliente_nome, u.nome AS barbeiro_nome
           FROM atendimentos a
           JOIN clientes c ON c.id = a.cliente_id
           LEFT JOIN usuarios u ON u.id = a.usuario_id
           WHERE a.data BETWEEN ? AND ? AND a.barbearia_id=? AND a.status='concluido'
           ORDER BY a.data DESC, a.hora DESC, a.id DESC""",
        (inicio, fim, b_id)
    ).fetchall()

    total = sum(r['valor'] for r in rows)
    db.close()
    return jsonify({
        'atendimentos': [dict(r) for r in rows],
        'total': total,
        'quantidade': len(rows)
    })



# ─────────────────────────────────────────────
# API — Admin: Barbeiros
# ─────────────────────────────────────────────
@app.route('/api/admin/barbeiros', methods=['GET', 'POST'])
@login_required
@admin_required
def api_barbeiros():
    db = get_db()
    b_id = current_user.barbearia_id

    if request.method == 'POST':
        data   = request.get_json()
        nome   = (data.get('nome') or '').strip()
        email  = (data.get('email') or '').strip().lower()
        senha  = data.get('senha') or ''
        is_adm = bool(data.get('is_admin', False))

        erros = []
        if not nome:  erros.append('Nome obrigatório')
        if not email: erros.append('E-mail obrigatório')
        if len(senha) < 6: erros.append('Senha deve ter ao menos 6 caracteres')
        if erros:
            return jsonify({'erro': ', '.join(erros)}), 400

        existe = db.execute("SELECT id FROM usuarios WHERE email=?", (email,)).fetchone()
        if existe:
            db.close()
            return jsonify({'erro': 'E-mail já cadastrado'}), 409

        cur = db.execute(
            "INSERT INTO usuarios(barbearia_id, nome, email, senha_hash, is_admin) VALUES(?,?,?,?,?)",
            (b_id, nome, email, generate_password_hash(senha), int(is_adm))
        )
        db.commit()
        novo_id = cur.lastrowid
        db.close()
        return jsonify({'id': novo_id, 'nome': nome, 'email': email}), 201

    rows = db.execute(
        "SELECT id,nome,email,is_admin,ativo,criado_em FROM usuarios WHERE barbearia_id=? ORDER BY criado_em",
        (b_id,)
    ).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/admin/barbeiros/<int:uid>', methods=['DELETE'])
@login_required
@admin_required
def api_barbeiro_delete(uid):
    if uid == current_user.id:
        return jsonify({'erro': 'Você não pode remover a si mesmo'}), 400
    db = get_db()
    db.execute("UPDATE usuarios SET ativo=0 WHERE id=? AND barbearia_id=?", (uid, current_user.barbearia_id))
    db.commit()
    db.close()
    return jsonify({'ok': True})


# ─────────────────────────────────────────────
# Error pages
# ─────────────────────────────────────────────
@app.errorhandler(403)
def err_403(e):
    return render_template('403.html'), 403


# ─────────────────────────────────────────────
# Run
# ─────────────────────────────────────────────
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
