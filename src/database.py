"""
Módulo de Banco de Dados - Versão 4.0 (REQ-01, REQ-02, REQ-03) + Histórico Edições
Arquivo: src/database.py

Mudanças v4:
- REQ-01: Status especial (Retirado / Não Recebido) com campos adicionais no modal.
  Exige obrigatoriamente digitação para "retirado_por" e "motivo_nao_recebido".
- Status especial conta no progresso do manifesto como tratado.
- Rastreabilidade granular por caixa no modal de observações.
- Histórico de comentários manuais com autoria e exclusão restrita (autor/admin).
- Informações fixas no modal de observações que requerem senha de admin para alterar.
"""
import sqlite3
import json
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
    """Retorna timestamp atual em BRT, sem microssegundos, ISO format."""
    return datetime.now(BRT).replace(microsecond=0).isoformat()


def get_agora_utc():
    """Retorna timestamp atual em UTC, sem microssegundos, ISO format."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


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

    # Migração: Adiciona a coluna origem caso ela não exista no banco legado
    try:
        cursor.execute("ALTER TABLE manifestos ADD COLUMN origem TEXT DEFAULT 'PDF_DIGITAL'")
    except sqlite3.OperationalError:
        pass # A coluna já existe no banco

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
            retirado_por TEXT,
            motivo_nao_recebido TEXT,
            FOREIGN KEY (manifesto_id) REFERENCES manifestos(id),
            UNIQUE(manifesto_id, numero_volume)
        )
    """)

    # Tabela Caixas Individuais (v4: com retirado_por e motivo_nao_recebido)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS caixas_individuais (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            volume_id INTEGER NOT NULL, 
            numero_caixa INTEGER NOT NULL, 
            status TEXT DEFAULT 'NÃO RECEBIDA', 
            data_hora_recepcao DATETIME, 
            usuario_conferente TEXT, 
            retirado_por TEXT,
            retirado_por_tipo TEXT,
            motivo_nao_recebido TEXT,
            FOREIGN KEY (volume_id) REFERENCES volumes(id), 
            UNIQUE(volume_id, numero_caixa)
        )
    """)

    # Tabela Logs (v3: auditoria completa)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            manifesto_id INTEGER, 
            volume_id INTEGER,
            caixa_numero INTEGER,
            acao TEXT NOT NULL, 
            detalhes TEXT, 
            estado_anterior TEXT,
            estado_posterior TEXT,
            usuario TEXT, 
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            timestamp_utc DATETIME,
            timestamp_brt DATETIME,
            FOREIGN KEY (manifesto_id) REFERENCES manifestos(id)
        )
    """)
    
    # Tabela Histórico de Edições Extramanifesto
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS historico_edicoes_extra (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            volume_id INTEGER NOT NULL,
            usuario TEXT NOT NULL,
            campo_alterado TEXT NOT NULL,
            valor_anterior TEXT,
            valor_novo TEXT,
            data_hora DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (volume_id) REFERENCES volumes(id)
        )
    """)

    # Tabela volume_observacoes (v4)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS volume_observacoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            volume_id INTEGER NOT NULL,
            texto TEXT NOT NULL,
            usuario TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (volume_id) REFERENCES volumes(id)
        )
    """)

    conn.commit()
    conn.close()


# ═══════════════════════════════════════════════════
# FUNÇÕES DE AUDITORIA (v3)
# ═══════════════════════════════════════════════════

def _obter_manifesto_id_por_volume(cursor, volume_id):
    """Obtém o manifesto_id a partir de um volume_id."""
    cursor.execute("SELECT manifesto_id FROM volumes WHERE id = ?", (volume_id,))
    res = cursor.fetchone()
    return res['manifesto_id'] if res else None


def _snapshot_caixa(cursor, volume_id, numero_caixa):
    """Captura estado atual de uma caixa para auditoria."""
    cursor.execute(
        "SELECT status, usuario_conferente, data_hora_recepcao, retirado_por, retirado_por_tipo, motivo_nao_recebido "
        "FROM caixas_individuais WHERE volume_id = ? AND numero_caixa = ?",
        (volume_id, numero_caixa)
    )
    row = cursor.fetchone()
    return dict(row) if row else None


def _snapshot_volume(cursor, volume_id):
    """Captura estado atual de um volume para auditoria."""
    cursor.execute(
        "SELECT status, quantidade_recebida, usuario_recepcao, data_hora_ultima_recepcao, retirado_por, motivo_nao_recebido "
        "FROM volumes WHERE id = ?",
        (volume_id,)
    )
    row = cursor.fetchone()
    return dict(row) if row else None


def registrar_log(cursor, manifesto_id, volume_id, caixa_numero,
                  acao, usuario, estado_anterior=None, estado_posterior=None):
    """Registra ação na trilha de auditoria imutável."""
    agora_utc = get_agora_utc()
    agora_brt = get_agora_br()
    cursor.execute("""
        INSERT INTO logs (manifesto_id, volume_id, caixa_numero, acao,
                         estado_anterior, estado_posterior,
                         usuario, timestamp_utc, timestamp_brt)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        manifesto_id, volume_id, caixa_numero, acao,
        json.dumps(estado_anterior, ensure_ascii=False) if estado_anterior else None,
        json.dumps(estado_posterior, ensure_ascii=False) if estado_posterior else None,
        usuario, agora_utc, agora_brt
    ))


# ═══════════════════════════════════════════════════
# FUNÇÕES DE USUÁRIO (AUTH)
# ═══════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════
# FUNÇÕES DE GESTÃO DE USUÁRIOS
# ═══════════════════════════════════════════════════

def listar_todos_usuarios():
    """Retorna lista de todos os usuários para o painel admin"""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, username, nome_completo, role FROM users ORDER BY nome_completo")
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def listar_usuarios_ativos():
    """Retorna lista simplificada de usuários para dropdowns (ex: 'Retirado por')."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, nome_completo FROM users ORDER BY nome_completo")
        return [dict(r) for r in cursor.fetchall()]
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


# ═══════════════════════════════════════════════════
# FUNÇÕES DE OBSERVAÇÃO
# ═══════════════════════════════════════════════════

def salvar_observacao(volume_id, texto):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE volumes SET observacao = ? WHERE id = ?", (texto, volume_id))
        conn.commit()
        return True
    finally:
        conn.close()


# ═══════════════════════════════════════════════════
# FUNÇÕES DE OBSERVAÇÕES MANUAIS (v4)
# ═══════════════════════════════════════════════════

def adicionar_observacao_manual(volume_id, texto, usuario):
    """Adiciona um comentário manual ao histórico de observações do volume e sincroniza."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        agora = get_agora_br()
        
        # 1. Inserir na tabela de histórico
        cursor.execute("""
            INSERT INTO volume_observacoes (volume_id, texto, usuario, timestamp)
            VALUES (?, ?, ?, ?)
        """, (volume_id, texto, usuario, agora))
        
        # 2. Atualizar a coluna observacao consolidada no volume
        cursor.execute("UPDATE volumes SET observacao = ? WHERE id = ?", (texto, volume_id))
        
        conn.commit()
        
        # 3. Sincronizar com Sheets
        run_async_sync(sheets.sincronizar_volume, volume_id)
        
        return True
    except Exception as e:
        print(f"Erro ao adicionar observacao: {e}")
        return False
    finally:
        conn.close()


def excluir_observacao_manual(observacao_id, usuario, role):
    """Exclui um comentário manual. Apenas o autor ou admin podem excluir. Atualiza volumes.observacao."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        
        # Buscar autor do comentário e volume_id
        cursor.execute("SELECT usuario, volume_id FROM volume_observacoes WHERE id = ?", (observacao_id,))
        res = cursor.fetchone()
        if not res:
            return False, "Comentário não encontrado."
            
        autor = res['usuario']
        volume_id = res['volume_id']
        
        if usuario == autor or role == 'admin':
            # 1. Excluir o comentário
            cursor.execute("DELETE FROM volume_observacoes WHERE id = ?", (observacao_id,))
            
            # 2. Buscar o comentário mais recente restante para esse volume
            cursor.execute("""
                SELECT texto FROM volume_observacoes 
                WHERE volume_id = ? 
                ORDER BY timestamp DESC, id DESC LIMIT 1
            """, (volume_id,))
            restante = cursor.fetchone()
            
            nova_obs = restante['texto'] if restante else None
            
            # 3. Atualizar a coluna observacao consolidada no volume
            cursor.execute("UPDATE volumes SET observacao = ? WHERE id = ?", (nova_obs, volume_id))
            
            conn.commit()
            
            # 4. Sincronizar com Sheets
            run_async_sync(sheets.sincronizar_volume, volume_id)
            
            return True, "Comentário excluído."
        else:
            return False, "Apenas o autor do comentário ou um administrador podem excluí-lo."
    except Exception as e:
        print(f"Erro ao excluir observacao: {e}")
        return False, str(e)
    finally:
        conn.close()


def listar_observacoes_manuais(volume_id):
    """Retorna lista de observações manuais do volume."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM volume_observacoes 
            WHERE volume_id = ? 
            ORDER BY timestamp DESC
        """, (volume_id,))
        return [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()


def obter_info_fixas_volume(volume_id):
    """Retorna informações de controle fixas (retirado_por, motivo_nao_recebido)."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT status, retirado_por, motivo_nao_recebido 
            FROM volumes WHERE id = ?
        """, (volume_id,))
        res = cursor.fetchone()
        return dict(res) if res else None
    finally:
        conn.close()


def atualizar_info_fixas_volume(volume_id, retirado_por, motivo_nao_recebido, usuario_executor):
    """Atualiza as informações fixas (requer senha de administrador no frontend)."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        agora = get_agora_br()
        manifesto_id = _obter_manifesto_id_por_volume(cursor, volume_id)
        
        estado_ant = _snapshot_volume(cursor, volume_id)
        
        cursor.execute("""
            UPDATE volumes SET 
                retirado_por = ?,
                motivo_nao_recebido = ?
            WHERE id = ?
        """, (retirado_por, motivo_nao_recebido, volume_id))
        
        cursor.execute("""
            UPDATE caixas_individuais SET
                retirado_por = ?,
                motivo_nao_recebido = ?
            WHERE volume_id = ?
        """, (retirado_por, motivo_nao_recebido, volume_id))
        
        _recalcular_volume(cursor, volume_id, agora, usuario_executor)
        _atualizar_status_manifesto(cursor, volume_id)
        
        estado_pos = _snapshot_volume(cursor, volume_id)
        registrar_log(
            cursor, manifesto_id, volume_id, None,
            'ATUALIZAR_INFO_FIXAS', usuario_executor,
            estado_ant, estado_pos
        )
        
        conn.commit()
        _sincronizar_sheets(cursor, volume_id)
        return True
    except Exception as e:
        conn.rollback()
        print(f"Erro ao atualizar info fixas: {e}")
        return False
    finally:
        conn.close()


# ═══════════════════════════════════════════════════
# FUNÇÕES EXISTENTES / CONSULTAS
# ═══════════════════════════════════════════════════

def listar_manifestos(filtro_num=None, filtro_status=None, data_ini=None, data_fim=None):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        
        # REQ-01: O progresso do manifesto (total_caixas_recebidas) conta caixas recebidas,
        # retiradas por terceiros e não recebidas com motivo (definidas como tratadas).
        query = """
            SELECT m.*,
                   COUNT(DISTINCT v.id) as total_volumes,
                   SUM(v.quantidade_expedida) as total_caixas_expedidas,
                   (SELECT COUNT(*) FROM caixas_individuais ci 
                    JOIN volumes vol ON ci.volume_id = vol.id 
                    WHERE vol.manifesto_id = m.id 
                      AND (ci.status = 'RECEBIDA' 
                           OR ci.status = 'RETIRADO POR OUTRA PESSOA' 
                           OR (ci.status = 'NÃO RECEBIDA' AND ci.motivo_nao_recebido IS NOT NULL AND ci.motivo_nao_recebido != ''))) as total_caixas_recebidas
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
    """
    Retorna volumes encontrados na pesquisa geral.
    v4: Lista de conferentes múltiplos na coluna 'POR'.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        query = "SELECT v.*, m.numero_manifesto FROM volumes v JOIN manifestos m ON v.manifesto_id = m.id WHERE v.numero_volume LIKE ? ORDER BY v.id DESC LIMIT 50"
        cursor.execute(query, (f"%{filtro_vol}%",))
        volumes = [dict(row) for row in cursor.fetchall()]
        
        for v in volumes:
            # Obter conferentes individuais distintos
            cursor.execute("""
                SELECT DISTINCT usuario_conferente FROM caixas_individuais 
                WHERE volume_id = ? AND usuario_conferente IS NOT NULL AND usuario_conferente != ''
            """, (v['id'],))
            conferentes = [r['usuario_conferente'] for r in cursor.fetchall()]
            
            if v['status'] == 'RETIRADO POR OUTRA PESSOA' and v['retirado_por']:
                v['usuario_recepcao'] = f"RET: {v['retirado_por']}"
            elif v['status'] == 'NÃO RECEBIDO' and v['motivo_nao_recebido']:
                v['usuario_recepcao'] = f"NÃO REC: {v['motivo_nao_recebido']}"
            elif conferentes:
                v['usuario_recepcao'] = ", ".join(conferentes)
            else:
                v['usuario_recepcao'] = "-"
        return volumes
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


def obter_imagens_manifesto_ocr(manifesto_id: int) -> list:
    """Retorna a lista de nomes de arquivos das imagens arquivadas para um manifesto de origem OCR."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT origem, pdf_path FROM manifestos WHERE id = ?", (manifesto_id,))
        r = cur.fetchone()
        if not r or r['origem'] != 'OCR_MOBILE':
            return []
        
        pdf_path = r['pdf_path']
        if not pdf_path or not os.path.exists(pdf_path):
            return []
            
        try:
            arquivos = sorted([f for f in os.listdir(pdf_path) if f.lower().endswith(('.png', '.jpg', '.jpeg'))])
            return arquivos
        except Exception:
            return []
    finally:
        conn.close()


def listar_volumes_detalhado(manifesto_id):
    """
    Retorna a listagem detalhada de volumes de um manifesto.
    v4: Concatenar recebedores se houver mais de um conferente nas caixas.
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM volumes WHERE manifesto_id=? ORDER BY remetente, numero_volume", (manifesto_id,))
        volumes = [dict(r) for r in cur.fetchall()]
        
        for v in volumes:
            cur.execute("""
                SELECT DISTINCT usuario_conferente FROM caixas_individuais 
                WHERE volume_id = ? AND usuario_conferente IS NOT NULL AND usuario_conferente != ''
            """, (v['id'],))
            conferentes = [r['usuario_conferente'] for r in cur.fetchall()]
            
            if v['status'] == 'RETIRADO POR OUTRA PESSOA' and v['retirado_por']:
                v['usuario_recepcao'] = f"RET: {v['retirado_por']}"
            elif v['status'] == 'NÃO RECEBIDO' and v['motivo_nao_recebido']:
                v['usuario_recepcao'] = f"NÃO REC: {v['motivo_nao_recebido']}"
            elif conferentes:
                v['usuario_recepcao'] = ", ".join(conferentes)
            else:
                v['usuario_recepcao'] = "-"
        return volumes
    finally:
        conn.close()


def obter_caixas_por_volume(volume_id):
    """Retorna caixas com dados completos de conferente individual."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM caixas_individuais WHERE volume_id=? ORDER BY numero_caixa", (volume_id,))
        return [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()


def obter_estatisticas_manifesto(manifesto_id):
    conn = get_connection()
    try:
        c = conn.cursor()
        # REQ-01: Progresso computado considerando caixas concluídas (recebidas, retiradas ou não recebidas com motivo)
        c.execute("SELECT COUNT(DISTINCT id) as total_volumes, SUM(quantidade_expedida) as total_caixas_expedidas FROM volumes WHERE manifesto_id=?", (manifesto_id,))
        row = dict(c.fetchone())
        
        c.execute("""
            SELECT COUNT(*) as total_caixas_recebidas FROM caixas_individuais ci
            JOIN volumes v ON ci.volume_id = v.id
            WHERE v.manifesto_id = ?
              AND (ci.status = 'RECEBIDA'
                   OR ci.status = 'RETIRADO POR OUTRA PESSOA'
                   OR (ci.status = 'NÃO RECEBIDA' AND ci.motivo_nao_recebido IS NOT NULL AND ci.motivo_nao_recebido != ''))
        """, (manifesto_id,))
        row['total_caixas_recebidas'] = c.fetchone()['total_caixas_recebidas'] or 0

        total = row['total_caixas_expedidas'] or 1
        rec = row['total_caixas_recebidas'] or 0
        row['percentual'] = round((rec/total)*100)
        return row
    finally:
        conn.close()


def listar_remetentes_manifesto(manifesto_id):
    return []


# ═══════════════════════════════════════════════════
# CRIAÇÃO DE MANIFESTOS E VOLUMES
# ═══════════════════════════════════════════════════

def criar_manifesto(numero: str, data: str, origem_terminal: str, destino: str, missao: str, aeronave: str, pdf_path: str, origem_registro: str = 'PDF_DIGITAL', usuario: str = None) -> int:
    """Cria um novo manifesto no banco de dados e sincroniza com o Google Sheets."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO manifestos (numero_manifesto, data_manifesto, terminal_origem, terminal_destino, missao, aeronave, pdf_path, origem, usuario_responsavel) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (numero, data, origem_terminal, destino, missao, aeronave, pdf_path, origem_registro, usuario)
        )
        mid = cursor.lastrowid
        conn.commit()
        run_async_sync(sheets.sincronizar_manifesto, {'numero_manifesto': numero, 'status': 'NÃO RECEBIDO', 'terminal_origem': origem_terminal, 'terminal_destino': destino})
        return mid
    finally:
        conn.close()


def adicionar_volume(manifesto_id, remetente, destinatario, numero_volume, quantidade_exp, **kwargs):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        status_init = 'NÃO RECEBIDO'
        prioridade = kwargs.get('prioridade')
        
        cursor.execute("INSERT INTO volumes (manifesto_id, remetente, destinatario, numero_volume, quantidade_expedida, peso_total, cubagem, prioridade, tipo_material, embalagem, status) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                      (manifesto_id, remetente, destinatario, numero_volume, quantidade_exp, kwargs.get('peso'), kwargs.get('cubagem'), prioridade, kwargs.get('tipo_material'), kwargs.get('embalagem'), status_init))
        vid = cursor.lastrowid
        for i in range(1, quantidade_exp + 1):
            cursor.execute("INSERT INTO caixas_individuais (volume_id, numero_caixa) VALUES (?,?)", (vid, i))
        conn.commit()

        # Sync Imediato
        cursor.execute("SELECT numero_manifesto FROM manifestos WHERE id=?", (manifesto_id,))
        man = cursor.fetchone()
        if man:
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
        cursor.execute("DELETE FROM volume_observacoes WHERE volume_id IN (SELECT id FROM volumes WHERE manifesto_id=?)", (manifesto_id,))
        cursor.execute("DELETE FROM caixas_individuais WHERE volume_id IN (SELECT id FROM volumes WHERE manifesto_id=?)", (manifesto_id,))
        cursor.execute("DELETE FROM volumes WHERE manifesto_id=?", (manifesto_id,))
        cursor.execute("DELETE FROM manifestos WHERE id=?", (manifesto_id,))
        conn.commit()
        return True
    finally:
        conn.close()


# ═══════════════════════════════════════════════════
# RECEBIMENTO E DESFAZER (v3 — com rastreabilidade)
# ═══════════════════════════════════════════════════

def marcar_recebido_web(volume_id, usuario):
    """
    Marca TODAS as caixas pendentes de um volume como RECEBIDA.
    v3 FIX (REQ-02): Não sobrescreve caixas já recebidas por outro conferente.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        agora = get_agora_br()
        manifesto_id = _obter_manifesto_id_por_volume(cursor, volume_id)

        # Capturar estado anterior para auditoria
        estado_ant = _snapshot_volume(cursor, volume_id)

        # REQ-02 FIX: Atualizar APENAS caixas que ainda NÃO foram recebidas/retiradas/tratadas
        cursor.execute("""
            UPDATE caixas_individuais SET 
                status = 'RECEBIDA', 
                data_hora_recepcao = ?, 
                usuario_conferente = ?,
                retirado_por = NULL,
                retirado_por_tipo = NULL,
                motivo_nao_recebido = NULL
            WHERE volume_id = ? 
              AND status != 'RECEBIDA' 
              AND status != 'RETIRADO POR OUTRA PESSOA'
              AND motivo_nao_recebido IS NULL
        """, (agora, usuario, volume_id))

        _recalcular_volume(cursor, volume_id, agora, usuario)
        _atualizar_status_manifesto(cursor, volume_id)

        # Auditoria
        estado_pos = _snapshot_volume(cursor, volume_id)
        registrar_log(
            cursor, manifesto_id, volume_id, None,
            'RECEBER_VOLUME_COMPLETO', usuario, estado_ant, estado_pos
        )

        conn.commit()
        _sincronizar_sheets(cursor, volume_id)
        return True
    finally:
        conn.close()


def receber_todos_volumes_web(manifesto_id, usuario):
    """
    Marca TODOS os volumes de um manifesto como RECEBIDO.
    v3 FIX (REQ-02): Não sobrescreve caixas já recebidas por outro conferente.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        agora = get_agora_br()

        cursor.execute("SELECT id FROM volumes WHERE manifesto_id=?", (manifesto_id,))
        volumes = [r['id'] for r in cursor.fetchall()]

        if not volumes: return False

        placeholders = ','.join(['?'] * len(volumes))

        # REQ-02 FIX: Atualizar APENAS caixas pendentes
        cursor.execute(f"""
            UPDATE caixas_individuais SET 
                status = 'RECEBIDA', 
                data_hora_recepcao = ?, 
                usuario_conferente = ?,
                retirado_por = NULL,
                retirado_por_tipo = NULL,
                motivo_nao_recebido = NULL
            WHERE volume_id IN ({placeholders}) 
              AND status != 'RECEBIDA'
              AND status != 'RETIRADO POR OUTRA PESSOA'
              AND motivo_nao_recebido IS NULL
        """, (agora, usuario, *volumes))

        for vid in volumes:
            _recalcular_volume(cursor, vid, agora, usuario)

        _atualizar_status_manifesto(cursor, volumes[0])
        
        # Auditoria: log por manifesto
        registrar_log(
            cursor, manifesto_id, None, None,
            'RECEBER_MANIFESTO_COMPLETO', usuario,
            {'volumes_afetados': len(volumes)},
            {'status': 'TOTALMENTE RECEBIDO'}
        )

        conn.commit()

        for vid in volumes:
            _sincronizar_sheets(cursor, vid)
        return True
    finally:
        conn.close()


def desfazer_recebimento_web(volume_id, usuario='SISTEMA'):
    """Desfaz recebimento de TODAS as caixas de um volume."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        manifesto_id = _obter_manifesto_id_por_volume(cursor, volume_id)

        # Capturar estado anterior
        estado_ant = _snapshot_volume(cursor, volume_id)

        cursor.execute(
            "UPDATE caixas_individuais SET status='NÃO RECEBIDA', data_hora_recepcao=NULL, "
            "usuario_conferente=NULL, retirado_por=NULL, retirado_por_tipo=NULL, motivo_nao_recebido=NULL "
            "WHERE volume_id=?",
            (volume_id,)
        )
        
        _recalcular_volume(cursor, volume_id, None, None)
        _atualizar_status_manifesto(cursor, volume_id)

        # Auditoria
        estado_pos = _snapshot_volume(cursor, volume_id)
        registrar_log(
            cursor, manifesto_id, volume_id, None,
            'DESFAZER_VOLUME', usuario, estado_ant, estado_pos
        )

        conn.commit()
        _sincronizar_sheets(cursor, volume_id)
        return True
    finally:
        conn.close()


def marcar_caixa_recebida_web(volume_id, numero_caixa, usuario):
    """Marca UMA caixa específica como recebida."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        agora = get_agora_br()
        manifesto_id = _obter_manifesto_id_por_volume(cursor, volume_id)

        # Capturar estado anterior da caixa
        estado_ant = _snapshot_caixa(cursor, volume_id, numero_caixa)

        cursor.execute("""
            UPDATE caixas_individuais SET 
                status = 'RECEBIDA', 
                data_hora_recepcao = ?, 
                usuario_conferente = ?,
                retirado_por = NULL,
                retirado_por_tipo = NULL,
                motivo_nao_recebido = NULL
            WHERE volume_id = ? AND numero_caixa = ?
        """, (agora, usuario, volume_id, numero_caixa))

        _recalcular_volume(cursor, volume_id, agora, usuario)
        _atualizar_status_manifesto(cursor, volume_id)

        # Auditoria
        estado_pos = _snapshot_caixa(cursor, volume_id, numero_caixa)
        registrar_log(
            cursor, manifesto_id, volume_id, numero_caixa,
            'RECEBER_CAIXA', usuario, estado_ant, estado_pos
        )

        conn.commit()
        _sincronizar_sheets(cursor, volume_id)
        return True
    finally:
        conn.close()


def desfazer_caixa_web(volume_id, numero_caixa, usuario='SISTEMA'):
    """Desfaz recebimento de UMA caixa específica."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        manifesto_id = _obter_manifesto_id_por_volume(cursor, volume_id)

        # Capturar estado anterior
        estado_ant = _snapshot_caixa(cursor, volume_id, numero_caixa)

        cursor.execute(
            "UPDATE caixas_individuais SET status='NÃO RECEBIDA', data_hora_recepcao=NULL, "
            "usuario_conferente=NULL, retirado_por=NULL, retirado_por_tipo=NULL, motivo_nao_recebido=NULL "
            "WHERE volume_id=? AND numero_caixa=?",
            (volume_id, numero_caixa)
        )

        _recalcular_volume(cursor, volume_id, None, None)
        _atualizar_status_manifesto(cursor, volume_id)

        # Auditoria
        estado_pos = _snapshot_caixa(cursor, volume_id, numero_caixa)
        registrar_log(
            cursor, manifesto_id, volume_id, numero_caixa,
            'DESFAZER_CAIXA', usuario, estado_ant, estado_pos
        )

        conn.commit()
        _sincronizar_sheets(cursor, volume_id)
        return True
    finally:
        conn.close()


# ═══════════════════════════════════════════════════
# REQ-01: STATUS ESPECIAL (Retirado / Não Recebido)
# ═══════════════════════════════════════════════════

def marcar_status_especial_caixa(volume_id, numero_caixa, novo_status,
                                  usuario_executor, retirado_por=None,
                                  motivo_nao_recebido=None):
    """
    Marca uma caixa individual com status especial:
    - 'RETIRADO POR OUTRA PESSOA' (quem retirou deve ser informado)
    - 'NÃO RECEBIDO' (motivo_nao_recebido é obrigatório)
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        agora = get_agora_br()
        manifesto_id = _obter_manifesto_id_por_volume(cursor, volume_id)

        # Capturar estado anterior
        estado_ant = _snapshot_caixa(cursor, volume_id, numero_caixa)

        if novo_status == 'RETIRADO POR OUTRA PESSOA':
            cursor.execute("""
                UPDATE caixas_individuais SET 
                    status = ?, 
                    data_hora_recepcao = ?, 
                    usuario_conferente = ?, 
                    retirado_por = ?, 
                    retirado_por_tipo = 'EXTERNO',
                    motivo_nao_recebido = NULL
                WHERE volume_id = ? AND numero_caixa = ?
            """, (novo_status, agora, usuario_executor, retirado_por, volume_id, numero_caixa))
        elif novo_status == 'NÃO RECEBIDO':
            # Salvar como NÃO RECEBIDA mas contendo o motivo_nao_recebido para computar como resolvida
            cursor.execute("""
                UPDATE caixas_individuais SET 
                    status = 'NÃO RECEBIDA', 
                    data_hora_recepcao = ?, 
                    usuario_conferente = ?, 
                    retirado_por = NULL, 
                    retirado_por_tipo = NULL,
                    motivo_nao_recebido = ?
                WHERE volume_id = ? AND numero_caixa = ?
            """, (agora, usuario_executor, motivo_nao_recebido, volume_id, numero_caixa))
        else:
            # Limpar
            cursor.execute("""
                UPDATE caixas_individuais SET 
                    status = 'NÃO RECEBIDA', 
                    data_hora_recepcao = NULL, 
                    usuario_conferente = NULL, 
                    retirado_por = NULL, 
                    retirado_por_tipo = NULL,
                    motivo_nao_recebido = NULL
                WHERE volume_id = ? AND numero_caixa = ?
            """, (volume_id, numero_caixa))

        _recalcular_volume(cursor, volume_id, agora, usuario_executor)
        _atualizar_status_manifesto(cursor, volume_id)

        # Auditoria
        estado_pos = _snapshot_caixa(cursor, volume_id, numero_caixa)
        registrar_log(
            cursor, manifesto_id, volume_id, numero_caixa,
            f'STATUS_ESPECIAL_{novo_status}', usuario_executor,
            estado_ant, estado_pos
        )

        conn.commit()
        _sincronizar_sheets(cursor, volume_id)
        return True
    except Exception as e:
        conn.rollback()
        print(f"Erro ao marcar status especial caixa: {e}")
        return False
    finally:
        conn.close()


def marcar_status_especial_volume(volume_id, novo_status, usuario_executor,
                                   retirado_por=None, motivo_nao_recebido=None):
    """Marca TODAS as caixas de um volume com status especial."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        agora = get_agora_br()
        manifesto_id = _obter_manifesto_id_por_volume(cursor, volume_id)

        # Capturar estado anterior
        estado_ant = _snapshot_volume(cursor, volume_id)

        if novo_status == 'RETIRADO POR OUTRA PESSOA':
            cursor.execute("""
                UPDATE caixas_individuais SET 
                    status = ?, 
                    data_hora_recepcao = ?, 
                    usuario_conferente = ?, 
                    retirado_por = ?, 
                    retirado_por_tipo = 'EXTERNO',
                    motivo_nao_recebido = NULL
                WHERE volume_id = ?
            """, (novo_status, agora, usuario_executor, retirado_por, volume_id))
            
            cursor.execute("""
                UPDATE volumes SET 
                    status = ?, 
                    quantidade_recebida = 0, 
                    data_hora_ultima_recepcao = ?, 
                    usuario_recepcao = ?, 
                    retirado_por = ?, 
                    motivo_nao_recebido = NULL 
                WHERE id = ?
            """, (novo_status, agora, usuario_executor, retirado_por, volume_id))
        elif novo_status == 'NÃO RECEBIDO':
            cursor.execute("""
                UPDATE caixas_individuais SET 
                    status = 'NÃO RECEBIDA', 
                    data_hora_recepcao = ?, 
                    usuario_conferente = ?, 
                    retirado_por = NULL, 
                    retirado_por_tipo = NULL,
                    motivo_nao_recebido = ?
                WHERE volume_id = ?
            """, (agora, usuario_executor, motivo_nao_recebido, volume_id))
            
            cursor.execute("""
                UPDATE volumes SET 
                    status = 'NÃO RECEBIDO', 
                    quantidade_recebida = 0, 
                    data_hora_ultima_recepcao = ?, 
                    usuario_recepcao = ?, 
                    retirado_por = NULL, 
                    motivo_nao_recebido = ? 
                WHERE id = ?
            """, (agora, usuario_executor, motivo_nao_recebido, volume_id))
        else:
            # Limpar tudo
            cursor.execute("""
                UPDATE caixas_individuais SET 
                    status = 'NÃO RECEBIDA', 
                    data_hora_recepcao = NULL, 
                    usuario_conferente = NULL, 
                    retirado_por = NULL, 
                    retirado_por_tipo = NULL,
                    motivo_nao_recebido = NULL 
                WHERE volume_id = ?
            """, (volume_id,))
            
            cursor.execute("""
                UPDATE volumes SET 
                    status = 'NÃO RECEBIDO', 
                    quantidade_recebida = 0, 
                    data_hora_ultima_recepcao = NULL, 
                    usuario_recepcao = NULL, 
                    retirado_por = NULL, 
                    motivo_nao_recebido = NULL 
                WHERE id = ?
            """, (volume_id,))

        _atualizar_status_manifesto(cursor, volume_id)

        estado_pos = _snapshot_volume(cursor, volume_id)
        registrar_log(
            cursor, manifesto_id, volume_id, None,
            f'STATUS_ESPECIAL_VOLUME_{novo_status}', usuario_executor,
            estado_ant, estado_pos
        )

        conn.commit()
        _sincronizar_sheets(cursor, volume_id)
        return True
    except Exception as e:
        conn.rollback()
        print(f"Erro ao marcar status especial volume: {e}")
        return False
    finally:
        conn.close()


# ═══════════════════════════════════════════════════
# FUNÇÕES INTERNAS DE RECÁLCULO
# ═══════════════════════════════════════════════════

def _recalcular_volume(cursor, volume_id, agora, usuario):
    """
    Recalcula status do volume com base no estado das caixas individuais.
    v4: Suporta status RETIRADO POR OUTRA PESSOA e NÃO RECEBIDO com motivo.
    """
    cursor.execute(
        "SELECT status, usuario_conferente, retirado_por, motivo_nao_recebido FROM caixas_individuais WHERE volume_id=?",
        (volume_id,)
    )
    caixas = [dict(r) for r in cursor.fetchall()]

    expedidas = len(caixas)
    recebidas = sum(1 for c in caixas if c['status'] == 'RECEBIDA')
    retiradas = sum(1 for c in caixas if c['status'] == 'RETIRADO POR OUTRA PESSOA')
    nao_recebidas = sum(1 for c in caixas if c['status'] == 'NÃO RECEBIDA' and c['motivo_nao_recebido'])

    resolvidas = recebidas + retiradas + nao_recebidas

    if resolvidas == 0:
        novo_status = 'NÃO RECEBIDO'
        cursor.execute(
            "UPDATE volumes SET quantidade_recebida=0, status=?, "
            "data_hora_ultima_recepcao=NULL, usuario_recepcao=NULL, "
            "retirado_por=NULL, motivo_nao_recebido=NULL WHERE id=?",
            (novo_status, volume_id)
        )
    else:
        # Determinar status com base no mix de estados
        if retiradas == expedidas:
            novo_status = 'RETIRADO POR OUTRA PESSOA'
        elif nao_recebidas == expedidas:
            novo_status = 'NÃO RECEBIDO'
        elif recebidas >= expedidas:
            novo_status = 'COMPLETO'
        elif resolvidas >= expedidas:
            # Todas resolvidas, mas mix de recebidas + retiradas + não recebidas
            novo_status = 'COMPLETO'
        else:
            novo_status = 'PARCIAL'

        # Obter retirador e motivo agregados
        v_retirado_por = caixas[0]['retirado_por'] if retiradas > 0 else None
        v_motivo = caixas[0]['motivo_nao_recebido'] if nao_recebidas > 0 else None

        cursor.execute("""
            UPDATE volumes SET 
                quantidade_recebida = ?, 
                status = ?, 
                data_hora_ultima_recepcao = ?, 
                usuario_recepcao = ?,
                retirado_por = ?,
                motivo_nao_recebido = ?
            WHERE id = ?
        """, (recebidas, novo_status, agora, usuario, v_retirado_por, v_motivo, volume_id))


def _atualizar_status_manifesto(cursor, volume_id):
    """Recalcula status do manifesto com base nos volumes."""
    cursor.execute("SELECT manifesto_id FROM volumes WHERE id=?", (volume_id,))
    res = cursor.fetchone()
    if not res:
        return None
    mid = res['manifesto_id']

    # Obter total de caixas expedidas
    cursor.execute("SELECT SUM(quantidade_expedida) as t FROM volumes WHERE manifesto_id=?", (mid,))
    total = cursor.fetchone()['t'] or 1

    # Obter total de caixas resolvidas
    cursor.execute("""
        SELECT COUNT(*) as r FROM caixas_individuais ci
        JOIN volumes v ON ci.volume_id = v.id
        WHERE v.manifesto_id = ?
          AND (ci.status = 'RECEBIDA' 
               OR ci.status = 'RETIRADO POR OUTRA PESSOA' 
               OR (ci.status = 'NÃO RECEBIDA' AND ci.motivo_nao_recebido IS NOT NULL AND ci.motivo_nao_recebido != ''))
    """, (mid,))
    resolvidas = cursor.fetchone()['r'] or 0

    if resolvidas == 0:
        novo_st = 'NÃO RECEBIDO'
    elif resolvidas >= total:
        novo_st = 'TOTALMENTE RECEBIDO'
    else:
        novo_st = 'PARCIALMENTE RECEBIDO'

    cursor.execute("UPDATE manifestos SET status=? WHERE id=?", (novo_st, mid))
    return mid


def _sincronizar_sheets(cursor, volume_id):
    """Sincroniza dados do volume com Google Sheets."""
    cursor.execute(
        "SELECT v.*, m.numero_manifesto, m.status as status_man "
        "FROM volumes v JOIN manifestos m ON v.manifesto_id = m.id WHERE v.id=?",
        (volume_id,)
    )
    row = cursor.fetchone()
    if not row:
        return
    dados = dict(row)
    num_man = dados.pop('numero_manifesto')
    status_man = dados.pop('status_man')

    # Verificar se há informações de retirado nas caixas
    cursor.execute(
        "SELECT retirado_por FROM caixas_individuais "
        "WHERE volume_id=? AND retirado_por IS NOT NULL LIMIT 1",
        (volume_id,)
    )
    retirado_row = cursor.fetchone()
    if retirado_row:
        dados['retirado_por'] = retirado_row['retirado_por']

    run_async_sync(sheets.sincronizar_volume, num_man, dados)
    run_async_sync(sheets.atualizar_status_cabecalho, num_man, status_man)


# ═══════════════════════════════════════════════════
# FUNÇÕES DE EDIÇÃO DE EXTRAMANIFESTO (Preservadas)
# ═══════════════════════════════════════════════════

def obter_volume_por_id(volume_id):
    """Retorna todos os dados de um volume específico"""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM volumes WHERE id = ?", (volume_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def atualizar_volume_extra(volume_id, numero_volume, remetente, quantidade, usuario):
    """Atualiza dados de volume EXTRA e retorna lista de alterações"""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        
        # Buscar dados atuais
        cursor.execute("SELECT * FROM volumes WHERE id = ?", (volume_id,))
        volume_atual = dict(cursor.fetchone())
        
        # Verificar se é EXTRA
        if volume_atual.get('prioridade') != 'EXTRA':
            return (False, [])
        
        alteracoes = []
        
        # Comparar e registrar alterações
        if str(volume_atual['numero_volume']) != str(numero_volume):
            alteracoes.append({
                'campo': 'numero_volume',
                'valor_anterior': str(volume_atual['numero_volume']),
                'valor_novo': str(numero_volume)
            })
        
        if str(volume_atual['remetente']) != str(remetente):
            alteracoes.append({
                'campo': 'remetente',
                'valor_anterior': str(volume_atual['remetente']),
                'valor_novo': str(remetente)
            })
        
        qtd_anterior = volume_atual['quantidade_expedida']
        if qtd_anterior != quantidade:
            alteracoes.append({
                'campo': 'quantidade_expedida',
                'valor_anterior': str(qtd_anterior),
                'valor_novo': str(quantidade)
            })
        
        # Se não há alterações, retornar
        if not alteracoes:
            return (True, [])
        
        # Atualizar volume
        cursor.execute("""
            UPDATE volumes 
            SET numero_volume = ?, remetente = ?, quantidade_expedida = ?
            WHERE id = ?
        """, (numero_volume, remetente, quantidade, volume_id))
        
        # Ajustar caixas se quantidade mudou
        if qtd_anterior != quantidade:
            if quantidade > qtd_anterior:
                # Adicionar caixas
                for i in range(qtd_anterior + 1, quantidade + 1):
                    cursor.execute("""
                        INSERT INTO caixas_individuais (volume_id, numero_caixa, status)
                        VALUES (?, ?, 'NÃO RECEBIDA')
                    """, (volume_id, i))
            else:
                # Remover caixas excedentes (priorizar não recebidas)
                cursor.execute("""
                    DELETE FROM caixas_individuais
                    WHERE volume_id = ? AND numero_caixa > ?
                    AND status = 'NÃO RECEBIDA'
                """, (volume_id, quantidade))
                
                # Se ainda sobrou, remover qualquer uma
                cursor.execute("""
                    DELETE FROM caixas_individuais 
                    WHERE volume_id = ? AND numero_caixa > ?
                """, (volume_id, quantidade))
            
            # Recalcular status do volume
            _recalcular_volume(cursor, volume_id, None, None)
        
        conn.commit()
        
        # Sincronizar com Sheets
        _sincronizar_sheets(cursor, volume_id)
        
        return (True, alteracoes)
    finally:
        conn.close()


def registrar_historico_edicao(volume_id, usuario, alteracoes):
    """Registra múltiplas alterações no histórico"""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        agora = get_agora_br()
        
        for alt in alteracoes:
            cursor.execute("""
                INSERT INTO historico_edicoes_extra 
                (volume_id, usuario, campo_alterado, valor_anterior, valor_novo, data_hora)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (volume_id, usuario, alt['campo'], alt['valor_anterior'], alt['valor_novo'], agora))
        
        conn.commit()
        return True
    finally:
        conn.close()


def obter_historico_edicoes(volume_id):
    """Retorna histórico completo de edições de um volume"""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM historico_edicoes_extra 
            WHERE volume_id = ? 
            ORDER BY data_hora DESC
        """, (volume_id,))
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()