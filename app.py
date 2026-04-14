from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
import os
import psycopg2
from psycopg2.extras import RealDictCursor

# Pega a URL do banco da variável de ambiente
DATABASE_URL = os.environ.get('DATABASE_URL', "postgresql://neondb_owner:npg_XmVC9dunT7Rg@ep-morning-lab-ace8f7vt.sa-east-1.aws.neon.tech/neondb?sslmode=require")

app = Flask(__name__)
CORS(app)


def get_db():
    if not DATABASE_URL:
        raise Exception("DATABASE_URL não configurada!")
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        nome TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        senha_hash TEXT NOT NULL,
        frase TEXT DEFAULT '',
        cor TEXT DEFAULT 'Neon azul',
        avatar TEXT DEFAULT '',
        pontos INTEGER DEFAULT 0
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS reactions (
        id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL,
        reaction TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS votes (
        id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL,
        categoria TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS recados (
        id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL,
        texto TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
    """)

    conn.commit()
    conn.close()


init_db()


@app.route("/")
def home():
    return jsonify({
        "message": "Backend funcionando!",
        "rotas": [
            "/api/register",
            "/api/login",
            "/api/users",
            "/api/users/<id>",
            "/api/users/<id>/react",
            "/api/users/<id>/vote",
            "/api/users/<id>/recado",
            "/api/admin/check",
            "/api/admin/stats",
            "/api/admin/usuarios",
            "/api/admin/votos",
            "/api/admin/recados",
            "/api/admin/reacoes"
        ]
    })


# ⚠️ MODIFICADO: Agora armazena senha em TEXTO PURO (sem hash)
@app.route("/api/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}

    nome = data.get("nome", "").strip()
    email = data.get("email", "").strip().lower()
    senha = data.get("senha", "").strip()

    if not nome or not email or not senha:
        return jsonify({"error": "Preencha nome, email e senha."}), 400

    conn = get_db()
    cur = conn.cursor()

    try:
        # ⚠️ ARMazenando senha em TEXTO PURO (INSEGURO - apenas para admin ver)
        cur.execute(
            "INSERT INTO users (nome, email, senha_hash) VALUES (%s, %s, %s)",
            (nome, email, senha)  # Agora salva o texto puro diretamente
        )
        conn.commit()
        user_id = cur.lastrowid
    except psycopg2.IntegrityError:
        conn.close()
        return jsonify({"error": "Este email já está cadastrado."}), 400

    cur.execute(
        "SELECT id, nome, email, frase, cor, avatar, pontos FROM users WHERE id = %s",
        (user_id,)
    )
    user = dict(cur.fetchone())
    conn.close()

    return jsonify({
        "message": "Conta criada com sucesso.",
        "user": user
    }), 201


# ⚠️ MODIFICADO: Login agora compara texto puro
@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}

    email = data.get("email", "").strip().lower()
    senha = data.get("senha", "").strip()

    if not email or not senha:
        return jsonify({"error": "Preencha email e senha."}), 400

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE email = %s", (email,))
    user = cur.fetchone()
    conn.close()

    if not user:
        return jsonify({"error": "Email ou senha inválidos."}), 401

    # ⚠️ Comparação direta de texto puro (sem hash)
    if user["senha_hash"] != senha:
        return jsonify({"error": "Email ou senha inválidos."}), 401

    return jsonify({
        "message": "Login realizado com sucesso.",
        "user": {
            "id": user["id"],
            "nome": user["nome"],
            "email": user["email"],
            "frase": user["frase"],
            "cor": user["cor"],
            "avatar": user["avatar"],
            "pontos": user["pontos"]
        }
    })


@app.route("/api/users", methods=["GET"])
def list_users():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, nome, email, frase, cor, avatar, pontos
        FROM users
        ORDER BY pontos DESC, nome ASC
    """)
    users = [dict(row) for row in cur.fetchall()]
    conn.close()
    return jsonify(users)


@app.route("/api/users/<int:user_id>", methods=["GET"])
def get_user(user_id):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT id, nome, email, frase, cor, avatar, pontos
        FROM users
        WHERE id = %s
    """, (user_id,))
    user = cur.fetchone()

    if not user:
        conn.close()
        return jsonify({"error": "Usuário não encontrado."}), 404

    cur.execute("SELECT reaction FROM reactions WHERE user_id = %s", (user_id,))
    reactions = [row["reaction"] for row in cur.fetchall()]

    cur.execute("SELECT categoria FROM votes WHERE user_id = %s", (user_id,))
    votes = [row["categoria"] for row in cur.fetchall()]

    cur.execute("SELECT texto FROM recados WHERE user_id = %s", (user_id,))
    recados = [row["texto"] for row in cur.fetchall()]

    conn.close()

    return jsonify({
        "user": dict(user),
        "reactions": reactions,
        "votes": votes,
        "recados": recados
    })


@app.route("/api/users/<int:user_id>", methods=["PUT"])
def update_user(user_id):
    data = request.get_json(silent=True) or {}

    nome = data.get("nome", "").strip()
    frase = data.get("frase", "").strip()
    cor = data.get("cor", "").strip()
    avatar = data.get("avatar", "").strip()

    if not nome:
        return jsonify({"error": "O nome não pode ficar vazio."}), 400

    conn = get_db()
    cur = conn.cursor()

    # Check if user exists first
    cur.execute("SELECT id FROM users WHERE id = %s", (user_id,))
    if not cur.fetchone():
        conn.close()
        return jsonify({"error": "Usuário não encontrado."}), 404

    cur.execute("""
        UPDATE users
        SET nome = %s, frase = %s, cor = %s, avatar = %s
        WHERE id = %s
    """, (nome, frase, cor, avatar, user_id))
    conn.commit()

    cur.execute("""
        SELECT id, nome, email, frase, cor, avatar, pontos
        FROM users
        WHERE id = %s
    """, (user_id,))
    user = cur.fetchone()
    conn.close()

    return jsonify({
        "message": "Perfil atualizado com sucesso.",
        "user": dict(user)
    })


@app.route("/api/users/<int:user_id>/react", methods=["POST"])
def add_reaction(user_id):
    data = request.get_json(silent=True) or {}
    reaction = data.get("reaction", "").strip()

    if not reaction:
        return jsonify({"error": "Reação inválida."}), 400

    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT id FROM users WHERE id = %s", (user_id,))
    if not cur.fetchone():
        conn.close()
        return jsonify({"error": "Usuário não encontrado."}), 404

    cur.execute(
        "INSERT INTO reactions (user_id, reaction) VALUES (%s, %s)",
        (user_id, reaction)
    )
    conn.commit()
    conn.close()

    return jsonify({"message": "Reação adicionada com sucesso."})


@app.route("/api/users/<int:user_id>/vote", methods=["POST"])
def add_vote(user_id):
    data = request.get_json(silent=True) or {}
    categoria = data.get("categoria", "").strip()

    if not categoria:
        return jsonify({"error": "Categoria inválida."}), 400

    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT id FROM users WHERE id = %s", (user_id,))
    if not cur.fetchone():
        conn.close()
        return jsonify({"error": "Usuário não encontrado."}), 404

    # Check if user already voted in this category
    cur.execute(
        "SELECT id FROM votes WHERE user_id = %s AND categoria = %s",
        (user_id, categoria)
    )
    if cur.fetchone():
        conn.close()
        return jsonify({"error": "Você já votou nesta categoria."}), 400

    cur.execute(
        "INSERT INTO votes (user_id, categoria) VALUES (%s, %s)",
        (user_id, categoria)
    )
    cur.execute(
        "UPDATE users SET pontos = pontos + 3 WHERE id = %s",
        (user_id,)
    )
    conn.commit()
    conn.close()

    return jsonify({"message": "Voto registrado com sucesso."})


@app.route("/api/users/<int:user_id>/recado", methods=["POST"])
def add_recado(user_id):
    data = request.get_json(silent=True) or {}
    texto = data.get("texto", "").strip()

    if not texto:
        return jsonify({"error": "Recado vazio."}), 400

    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT id FROM users WHERE id = %s", (user_id,))
    if not cur.fetchone():
        conn.close()
        return jsonify({"error": "Usuário não encontrado."}), 404

    cur.execute(
        "INSERT INTO recados (user_id, texto) VALUES (%s, %s)",
        (user_id, texto)
    )
    conn.commit()
    conn.close()

    return jsonify({"message": "Recado enviado com sucesso."})


# ==================== ADMIN PANEL ROTAS ====================

# Configuração do admin (use variável de ambiente em produção)
ADMIN_PASSWORD = "admin123"  # Mude para uma senha forte


@app.route("/api/admin/check", methods=["POST"])
def admin_check():
    """Verifica a senha do administrador"""
    data = request.get_json(silent=True) or {}
    senha = data.get("senha", "").strip()
    
    if senha == ADMIN_PASSWORD:
        return jsonify({"success": True, "message": "Acesso autorizado"})
    else:
        return jsonify({"success": False, "error": "Senha incorreta"}), 401


@app.route("/api/admin/stats", methods=["GET"])
def admin_stats():
    """Retorna estatísticas gerais do sistema"""
    conn = get_db()
    cur = conn.cursor()
    
    # Total de usuários
    cur.execute("SELECT COUNT(*) FROM users")
    total_users = cur.fetchone()[0]
    
    # Total de rankings (se existir tabela, senão retorna 0)
    try:
        cur.execute("SELECT COUNT(*) FROM rankings")
        total_rankings = cur.fetchone()[0]
    except Exception:
        total_rankings = 0
    
    # Total de votos
    cur.execute("SELECT COUNT(*) FROM votes")
    total_votes = cur.fetchone()[0]
    
    # Total de reações
    cur.execute("SELECT COUNT(*) FROM reactions")
    total_reactions = cur.fetchone()[0]
    
    # Total de recados
    cur.execute("SELECT COUNT(*) FROM recados")
    total_recados = cur.fetchone()[0]
    
    conn.close()
    
    return jsonify({
        "total_users": total_users,
        "total_rankings": total_rankings,
        "total_votes": total_votes,
        "total_reactions": total_reactions,
        "total_recados": total_recados
    })


# ⚠️ MODIFICADO: Agora retorna a senha em TEXTO PURO para o admin ver
@app.route("/api/admin/usuarios", methods=["GET"])
def admin_usuarios():
    """Retorna lista de todos os usuários com SENHAS EM TEXTO PURO (apenas admin)"""
    conn = get_db()
    cur = conn.cursor()
    
    # ⚠️ Retornando a senha em texto puro (campo senha_hash agora contém o texto)
    cur.execute("""
        SELECT id, nome, email, senha_hash as senha, frase, cor, avatar, pontos
        FROM users
        ORDER BY id DESC
    """)
    users = cur.fetchall()
    conn.close()
    
    # Retorna os usuários com a senha em texto puro
    usuarios_list = []
    for user in users:
        usuarios_list.append({
            "id": user["id"],
            "nome": user["nome"],
            "email": user["email"],
            "senha": user["senha"],  # ⚠️ SENHA EM TEXTO PURO!
            "frase": user["frase"] or "",
            "cor": user["cor"],
            "avatar": user["avatar"] or "",
            "pontos": user["pontos"],
            "data_criacao": "Sistema registra automaticamente"
        })
    
    return jsonify(usuarios_list)


@app.route("/api/admin/usuarios/<int:user_id>", methods=["DELETE"])
def admin_delete_user(user_id):
    """Deleta um usuário (apenas admin)"""
    conn = get_db()
    cur = conn.cursor()
    
    # Verifica se usuário existe
    cur.execute("SELECT id FROM users WHERE id = %s", (user_id,))
    if not cur.fetchone():
        conn.close()
        return jsonify({"error": "Usuário não encontrado"}), 404
    
    # Deleta recados, reações, votos primeiro (por causa das FKs)
    cur.execute("DELETE FROM recados WHERE user_id = %s", (user_id,))
    cur.execute("DELETE FROM reactions WHERE user_id = %s", (user_id,))
    cur.execute("DELETE FROM votes WHERE user_id = %s", (user_id,))
    cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
    
    conn.commit()
    conn.close()
    
    return jsonify({"message": "Usuário deletado com sucesso"})


@app.route("/api/admin/votos", methods=["GET"])
def admin_votos():
    """Retorna todos os votos do sistema"""
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT v.id, v.user_id, u.nome as usuario_nome, u.email as usuario_email,
               v.categoria
        FROM votes v
        JOIN users u ON v.user_id = u.id
        ORDER BY v.id DESC
        LIMIT 100
    """)
    
    votes = cur.fetchall()
    conn.close()
    
    votos_list = []
    for voto in votes:
        votos_list.append({
            "id": voto["id"],
            "usuario_id": voto["user_id"],
            "usuario_nome": voto["usuario_nome"],
            "usuario_email": voto["usuario_email"],
            "categoria": voto["categoria"],
            "data_voto": f"Voto #{voto['id']}"
        })
    
    return jsonify(votos_list)


@app.route("/api/admin/recados", methods=["GET"])
def admin_recados():
    """Retorna todos os recados do sistema"""
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT r.id, r.user_id, u.nome as usuario_nome, u.email as usuario_email,
               r.texto
        FROM recados r
        JOIN users u ON r.user_id = u.id
        ORDER BY r.id DESC
        LIMIT 100
    """)
    
    recados = cur.fetchall()
    conn.close()
    
    recados_list = []
    for recado in recados:
        recados_list.append({
            "id": recado["id"],
            "usuario_id": recado["user_id"],
            "usuario_nome": recado["usuario_nome"],
            "usuario_email": recado["usuario_email"],
            "texto": recado["texto"],
            "data": f"Recado #{recado['id']}"
        })
    
    return jsonify(recados_list)


@app.route("/api/admin/reacoes", methods=["GET"])
def admin_reacoes():
    """Retorna todas as reações do sistema"""
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT r.id, r.user_id, u.nome as usuario_nome, u.email as usuario_email,
               r.reaction
        FROM reactions r
        JOIN users u ON r.user_id = u.id
        ORDER BY r.id DESC
        LIMIT 100
    """)
    
    reacoes = cur.fetchall()
    conn.close()
    
    reacoes_list = []
    for reacao in reacoes:
        reacoes_list.append({
            "id": reacao["id"],
            "usuario_id": reacao["user_id"],
            "usuario_nome": reacao["usuario_nome"],
            "usuario_email": reacao["usuario_email"],
            "reaction": reacao["reaction"]
        })
    
    return jsonify(reacoes_list)


@app.route("/api/admin/change-password", methods=["POST"])
def admin_change_password():
    """Altera a senha do administrador (armazenada em arquivo)"""
    data = request.get_json(silent=True) or {}
    old_password = data.get("old_password", "").strip()
    new_password = data.get("new_password", "").strip()
    
    global ADMIN_PASSWORD
    
    if old_password != ADMIN_PASSWORD:
        return jsonify({"error": "Senha atual incorreta"}), 401
    
    if len(new_password) < 4:
        return jsonify({"error": "A nova senha deve ter pelo menos 4 caracteres"}), 400
    
    ADMIN_PASSWORD = new_password
    
    # Opcional: salvar em arquivo para persistência
    try:
        with open(".admin_password", "w") as f:
            f.write(new_password)
    except Exception:
        pass
    
    return jsonify({"message": "Senha do administrador alterada com sucesso"})


if __name__ == "__main__":
    app.run(debug=True, port=5000)