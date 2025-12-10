"""
Módulo de Banco de Dados - Versão 2.0 (Auth + Obs)
Arquivo: src/database.py
"""
import sqlite3
from pathlib import Path
from datetime import datetime, timezone, timedelta
import sys
import os
from werkzeug.security import generate_password_hash, check_password_hash

# Configuração de Caminhos
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

# Configuração do Banco
BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "database.db"

# Fuso Horário BRT
BRT = timezone(timedelta(hours=-3))

def get_agora_br():
    return datetime.now(BRT).replace(microsecond=0).isoformat()

# Integração Sheets
try:
    import sheets_sync as sheets
    SHEETS_ENABLED = True
except ImportError:
    sheets = None
    SHEETS_ENABLED = False

def run_async_sync(target_func, *args):
    if SHEETS_ENABLED and sheets:
        try:
            sheets.agendar_tarefa(target_func, *args)
        except Exception as e:
            print(f"Erro ao agendar sync: {e}")

def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=30.0)
    conn.row_factory = sqlite3.Row
    return conn

def init_database():
    conn = get_connection()
    cursor = conn.cursor()

    # Tabela de Usuários (NOVO)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            nome_completo TEXT NOT NULL,
            role TEXT DEFAULT 'operador' -- 'admin' ou 'operador'
        )
    """)

    cursor.execute("CREATE TABLE IF NOT EXISTS manifestos (id INTEGER PRIMARY KEY AUTOINCREMENT, numero_manifesto TEXT UNIQUE NOT NULL, data_manifesto DATE, terminal_origem TEXT, terminal_destino TEXT, missao TEXT, aeronave TEXT, pdf_path TEXT, status TEXT DEFAULT 'NÃO RECEBIDO', data_registro DATETIME DEFAULT CURRENT_TIMESTAMP, data_conferencia_inicio DATETIME, data_conferencia_fim DATETIME, usuario_responsavel TEXT)")

    # Tabela Volumes (Com campo observacao NOVO)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS volumes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            manifesto_id INTEGER NOT NULL,
            remetente TEXT NOT NULL,
            destinatario TEXT NOT NULL,
            numero_volume TEXT NOT NULL,
            quantidade_expedida INTEGER NOT NULL DEFAULT 1,
            quantidade_recebida INTEGER DEFAULT 0,
            peso_total REAL,
            cubagem REAL,
            prioridade TEXT,
            tipo_material TEXT,
            embalagem TEXT,
            status TEXT DEFAULT 'NÃO RECEBIDO',
            data_hora_primeira_recepcao DATETIME,
            data_hora_ultima_recepcao DATETIME,
            usuario_recepcao TEXT,
            observacao TEXT, -- NOVO CAMPO
            FOREIGN KEY (manifesto_id) REFERENCES manifestos(id),
            UNIQUE(manifesto_id, numero_volume)
        )
    """)

    cursor.execute("CREATE TABLE IF NOT EXISTS caixas_individuais (id INTEGER PRIMARY KEY AUTOINCREMENT, volume_id INTEGER NOT NULL, numero_caixa INTEGER NOT NULL, status TEXT DEFAULT 'NÃO RECEBIDA', data_hora_recepcao DATETIME, usuario_conferente TEXT, FOREIGN KEY (volume_id) REFERENCES volumes(id), UNIQUE(volume_id, numero_caixa))")
    cursor.execute("CREATE TABLE IF NOT EXISTS logs (id INTEGER PRIMARY KEY AUTOINCREMENT, manifesto_id INTEGER, acao TEXT NOT NULL, detalhes TEXT, usuario TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (manifesto_id) REFERENCES manifestos(id))")

    conn.commit()
    conn.close()

# --- FUNÇÕES DE USUÁRIO (AUTH) ---

def criar_usuario(username, senha, nome, role='operador'):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        pw_hash = generate_password_hash(senha)
        cursor.execute("INSERT INTO users (username, password_hash, nome_completo, role) VALUES (?, ?, ?, ?)",
                      (username, pw_hash, nome, role))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False # Usuário já existe
    finally:
        conn.close()

def verificar_login(username, senha):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()

        if user and check_password_hash(user['password_hash'], senha):
            return dict(user)
        return None
    finally:
        conn.close()

def obter_usuario_por_id(user_id):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        user = cursor.fetchone()
        return dict(user) if user else None
    finally:
        conn.close()

# --- FUNÇÕES DE GESTÃO DE USUÁRIOS ---

def listar_todos_usuarios():
    """Retorna lista de todos os usuários para o painel admin"""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, username, nome_completo, role FROM users ORDER BY nome_completo")
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()

def atualizar_senha(user_id, nova_senha):
    """Atualiza a senha de um usuário específico"""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        pw_hash = generate_password_hash(nova_senha)
        cursor.execute("UPDATE users SET password_hash = ? WHERE id = ?", (pw_hash, user_id))
        conn.commit()
        return True
    finally:
        conn.close()

def excluir_usuario_db(user_id):
    """Remove um usuário do sistema"""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
        return True
    finally:
        conn.close()

def verificar_senha_atual_db(user_id, senha_texto):
    """Verifica se a senha atual confere (para troca de senha)"""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT password_hash FROM users WHERE id = ?", (user_id,))
        res = cursor.fetchone()
        if res and check_password_hash(res['password_hash'], senha_texto):
            return True
        return False
    finally:
        conn.close()


# --- FUNÇÕES DE OBSERVAÇÃO ---

def salvar_observacao(volume_id, texto):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE volumes SET observacao = ? WHERE id = ?", (texto, volume_id))
        conn.commit()
        return True
    finally:
        conn.close()

# --- FUNÇÕES EXISTENTES ---

def listar_manifestos(filtro_num=None, filtro_status=None, data_ini=None, data_fim=None):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        query = """
            SELECT m.*,
                   COUNT(DISTINCT v.id) as total_volumes,
                   SUM(v.quantidade_expedida) as total_caixas_expedidas,
                   SUM(v.quantidade_recebida) as total_caixas_recebidas
            FROM manifestos m
            LEFT JOIN volumes v ON m.id = v.manifesto_id
            WHERE 1=1
        """
        params = []
        if filtro_num:
            query += " AND m.numero_manifesto LIKE ?"
            params.append(f"%{filtro_num}%")
        if filtro_status and filtro_status != "TODOS":
            query += " AND m.status = ?"
            params.append(filtro_status)
        query += " GROUP BY m.id ORDER BY m.id DESC"
        cursor.execute(query, params)
        resultados = [dict(row) for row in cursor.fetchall()]

        if data_ini or data_fim:
            filtrados = []
            dt_ini = datetime.strptime(data_ini, '%Y-%m-%d') if data_ini else datetime.min
            dt_fim = datetime.strptime(data_fim, '%Y-%m-%d') if data_fim else datetime.max
            dt_fim = dt_fim.replace(hour=23, minute=59, second=59)
            for r in resultados:
                try:
                    d_man_str = r['data_manifesto']
                    if d_man_str:
                        d_man = datetime.strptime(d_man_str, '%d/%m/%Y')
                        if dt_ini <= d_man <= dt_fim:
                            filtrados.append(r)
                    else: pass
                except: filtrados.append(r)
            return filtrados
        return resultados
    finally:
        conn.close()

def buscar_volumes_geral(filtro_vol):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        query = "SELECT v.*, m.numero_manifesto FROM volumes v JOIN manifestos m ON v.manifesto_id = m.id WHERE v.numero_volume LIKE ? ORDER BY v.id DESC LIMIT 50"
        cursor.execute(query, (f"%{filtro_vol}%",))
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()

def obter_manifesto(id):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM manifestos WHERE id=?",(id,))
        r = cur.fetchone()
        return dict(r) if r else None
    finally:
        conn.close()

def listar_volumes_detalhado(manifesto_id):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM volumes WHERE manifesto_id=? ORDER BY remetente, numero_volume", (manifesto_id,))
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

def criar_manifesto(numero, data, origem, destino, missao, aeronave, pdf_path):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO manifestos (numero_manifesto, data_manifesto, terminal_origem, terminal_destino, missao, aeronave, pdf_path) VALUES (?,?,?,?,?,?,?)",
                      (numero, data, origem, destino, missao, aeronave, pdf_path))
        mid = cursor.lastrowid
        conn.commit()
        run_async_sync(sheets.sincronizar_manifesto, {'numero_manifesto': numero, 'status': 'NÃO RECEBIDO', 'terminal_origem': origem, 'terminal_destino': destino})
        return mid
    finally:
        conn.close()

def adicionar_volume(manifesto_id, remetente, destinatario, numero_volume, quantidade_exp, **kwargs):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        # Se prioridade for 'EXTRA', status será 'VOLUME EXTRA' se suportado, senão padrão
        # No sheets_sync, 'VOLUME EXTRA' tem cor especial.
        status_init = 'NÃO RECEBIDO'
        prioridade = kwargs.get('prioridade')
        
        cursor.execute("INSERT INTO volumes (manifesto_id, remetente, destinatario, numero_volume, quantidade_expedida, peso_total, cubagem, prioridade, tipo_material, embalagem, status) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                      (manifesto_id, remetente, destinatario, numero_volume, quantidade_exp, kwargs.get('peso'), kwargs.get('cubagem'), prioridade, kwargs.get('tipo_material'), kwargs.get('embalagem'), status_init))
        vid = cursor.lastrowid
        for i in range(1, quantidade_exp + 1):
            cursor.execute("INSERT INTO caixas_individuais (volume_id, numero_caixa) VALUES (?,?)", (vid, i))
        conn.commit()

        # Sync Imediato (Mesmo status não recebido, para aparecer na planilha)
        cursor.execute("SELECT numero_manifesto FROM manifestos WHERE id=?", (manifesto_id,))
        man = cursor.fetchone()
        if man:
             # Se for extra, passamos um status "virtual" para o sync colorir, 
             # ou mantemos o status real. Vamos passar 'VOLUME EXTRA' no sync se a prioridade for essa.
             status_sync = 'VOLUME EXTRA' if prioridade == 'EXTRA' else 'NÃO RECEBIDO'
             
             run_async_sync(sheets.sincronizar_volume, man['numero_manifesto'], {
                 'remetente': remetente, 'destinatario': destinatario, 'numero_volume': numero_volume,
                 'quantidade_expedida': quantidade_exp, 'quantidade_recebida': 0, 'status': status_sync
             })
        return vid
    finally:
        conn.close()

def excluir_manifesto(manifesto_id):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM logs WHERE manifesto_id=?", (manifesto_id,))
        cursor.execute("DELETE FROM caixas_individuais WHERE volume_id IN (SELECT id FROM volumes WHERE manifesto_id=?)", (manifesto_id,))
        cursor.execute("DELETE FROM volumes WHERE manifesto_id=?", (manifesto_id,))
        cursor.execute("DELETE FROM manifestos WHERE id=?", (manifesto_id,))
        conn.commit()
        return True
    finally:
        conn.close()

def marcar_recebido_web(volume_id, usuario):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        agora = get_agora_br()

        cursor.execute("UPDATE caixas_individuais SET status='RECEBIDA', data_hora_recepcao=?, usuario_conferente=? WHERE volume_id=?", (agora, usuario, volume_id))
        cursor.execute("UPDATE volumes SET quantidade_recebida=quantidade_expedida, status='COMPLETO', data_hora_ultima_recepcao=?, usuario_recepcao=? WHERE id=?", (agora, usuario, volume_id))
        cursor.execute("UPDATE volumes SET data_hora_primeira_recepcao=? WHERE id=? AND data_hora_primeira_recepcao IS NULL", (agora, volume_id))

        _atualizar_status_manifesto(cursor, volume_id)
        conn.commit()
        _sincronizar_sheets(cursor, volume_id)
        return True
    finally:
        conn.close()

def receber_todos_volumes_web(manifesto_id, usuario):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        agora = get_agora_br()

        cursor.execute("SELECT id FROM volumes WHERE manifesto_id=?", (manifesto_id,))
        volumes = [r['id'] for r in cursor.fetchall()]

        if not volumes: return False

        cursor.execute(f"UPDATE caixas_individuais SET status='RECEBIDA', data_hora_recepcao=?, usuario_conferente=? WHERE volume_id IN ({','.join(['?']*len(volumes))})", (agora, usuario, *volumes))
        cursor.execute("UPDATE volumes SET quantidade_recebida=quantidade_expedida, status='COMPLETO', data_hora_ultima_recepcao=?, usuario_recepcao=? WHERE manifesto_id=?", (agora, usuario, manifesto_id))
        cursor.execute("UPDATE manifestos SET status='TOTALMENTE RECEBIDO' WHERE id=?", (manifesto_id,))
        conn.commit()

        for vid in volumes:
            _sincronizar_sheets(cursor, vid)
        return True
    finally:
        conn.close()

def desfazer_recebimento_web(volume_id):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE caixas_individuais SET status='NÃO RECEBIDA', data_hora_recepcao=NULL, usuario_conferente=NULL WHERE volume_id=?", (volume_id,))
        cursor.execute("UPDATE volumes SET quantidade_recebida=0, status='NÃO RECEBIDO', data_hora_ultima_recepcao=NULL, usuario_recepcao=NULL WHERE id=?", (volume_id,))
        _atualizar_status_manifesto(cursor, volume_id)
        conn.commit()
        _sincronizar_sheets(cursor, volume_id)
        return True
    finally:
        conn.close()

def marcar_caixa_recebida_web(volume_id, numero_caixa, usuario):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        agora = get_agora_br()
        cursor.execute("UPDATE caixas_individuais SET status='RECEBIDA', data_hora_recepcao=?, usuario_conferente=? WHERE volume_id=? AND numero_caixa=?", (agora, usuario, volume_id, numero_caixa))
        _recalcular_volume(cursor, volume_id, agora, usuario)
        _atualizar_status_manifesto(cursor, volume_id)
        conn.commit()
        _sincronizar_sheets(cursor, volume_id)
        return True
    finally:
        conn.close()

def desfazer_caixa_web(volume_id, numero_caixa):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE caixas_individuais SET status='NÃO RECEBIDA', data_hora_recepcao=NULL, usuario_conferente=NULL WHERE volume_id=? AND numero_caixa=?", (volume_id, numero_caixa))
        _recalcular_volume(cursor, volume_id, None, None)
        _atualizar_status_manifesto(cursor, volume_id)
        conn.commit()
        _sincronizar_sheets(cursor, volume_id)
        return True
    finally:
        conn.close()

def _recalcular_volume(cursor, volume_id, agora, usuario):
    cursor.execute("SELECT COUNT(*) as qtd FROM caixas_individuais WHERE volume_id=? AND status='RECEBIDA'", (volume_id,))
    recebidas = cursor.fetchone()['qtd']
    cursor.execute("SELECT quantidade_expedida FROM volumes WHERE id=?", (volume_id,))
    expedidas = cursor.fetchone()['quantidade_expedida']

    novo_status = 'NÃO RECEBIDO'
    if recebidas == 0:
        novo_status = 'NÃO RECEBIDO'
        cursor.execute("UPDATE volumes SET quantidade_recebida=0, status=?, data_hora_ultima_recepcao=NULL, usuario_recepcao=NULL WHERE id=?", (novo_status, volume_id))
    else:
        if recebidas >= expedidas: novo_status = 'COMPLETO'
        else: novo_status = 'PARCIAL'

        if agora and usuario:
            cursor.execute("UPDATE volumes SET quantidade_recebida=?, status=?, data_hora_ultima_recepcao=?, usuario_recepcao=? WHERE id=?", (recebidas, novo_status, agora, usuario, volume_id))
        else:
            cursor.execute("UPDATE volumes SET quantidade_recebida=?, status=? WHERE id=?", (recebidas, novo_status, volume_id))

def _atualizar_status_manifesto(cursor, volume_id):
    cursor.execute("SELECT manifesto_id FROM volumes WHERE id=?", (volume_id,))
    res = cursor.fetchone()
    if not res: return
    mid = res['manifesto_id']
    cursor.execute("SELECT SUM(quantidade_expedida) as t, SUM(quantidade_recebida) as r FROM volumes WHERE manifesto_id=?", (mid,))
    st = cursor.fetchone()
    total = st['t'] or 1
    recebido = st['r'] or 0
    if recebido == 0: novo_st = 'NÃO RECEBIDO'
    elif recebido >= total: novo_st = 'TOTALMENTE RECEBIDO'
    else: novo_st = 'PARCIALMENTE RECEBIDO'
    cursor.execute("UPDATE manifestos SET status=? WHERE id=?", (novo_st, mid))
    return mid

def _sincronizar_sheets(cursor, volume_id):
    cursor.execute("SELECT v.*, m.numero_manifesto, m.status as status_man FROM volumes v JOIN manifestos m ON v.manifesto_id = m.id WHERE v.id=?", (volume_id,))
    dados = dict(cursor.fetchone())
    num_man = dados.pop('numero_manifesto')
    status_man = dados.pop('status_man')
    run_async_sync(sheets.sincronizar_volume, num_man, dados)
    run_async_sync(sheets.atualizar_status_cabecalho, num_man, status_man)

def obter_caixas_por_volume(volume_id):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM caixas_individuais WHERE volume_id=? ORDER BY numero_caixa", (volume_id,))
        return [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()

def obter_estatisticas_manifesto(manifesto_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(DISTINCT id) as total_volumes, SUM(quantidade_expedida) as total_caixas_expedidas, SUM(quantidade_recebida) as total_caixas_recebidas FROM volumes WHERE manifesto_id=?", (manifesto_id,))
    row = dict(c.fetchone())
    conn.close()
    total = row['total_caixas_expedidas'] or 1
    rec = row['total_caixas_recebidas'] or 0
    row['percentual'] = round((rec/total)*100)
    return row

def listar_remetentes_manifesto(manifesto_id):
    return []