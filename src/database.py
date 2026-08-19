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

    # Tabela de Usuários (v5: com secao)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            nome_completo TEXT NOT NULL,
            role TEXT DEFAULT 'operador_tsre',
            secao TEXT DEFAULT 'TSRE'
        )
    """)

    cursor.execute("CREATE TABLE IF NOT EXISTS manifestos (id INTEGER PRIMARY KEY AUTOINCREMENT, numero_manifesto TEXT UNIQUE NOT NULL, data_manifesto DATE, terminal_origem TEXT, terminal_destino TEXT, missao TEXT, aeronave TEXT, pdf_path TEXT, status TEXT DEFAULT 'PENDENTE', data_registro DATETIME DEFAULT CURRENT_TIMESTAMP, data_conferencia_inicio DATETIME, data_conferencia_fim DATETIME, usuario_responsavel TEXT, origem TEXT DEFAULT 'PDF_DIGITAL', secao_origem TEXT DEFAULT 'TSRE')")

    # Tabela manifesto_secao (v5)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS manifesto_secao (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            manifesto_id INTEGER NOT NULL,
            secao TEXT NOT NULL,
            status_conferencia TEXT DEFAULT 'PENDENTE',
            status_autorizacao TEXT DEFAULT 'PENDENTE',
            autorizado_por TEXT,
            data_autorizacao DATETIME,
            excluido INTEGER DEFAULT 0,
            data_exclusao DATETIME,
            FOREIGN KEY (manifesto_id) REFERENCES manifestos(id),
            UNIQUE(manifesto_id, secao)
        )
    """)

    # Tabela Volumes (Com campo observacao e secao_extra)
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
            status TEXT DEFAULT 'PENDENTE',
            data_hora_primeira_recepcao DATETIME,
            data_hora_ultima_recepcao DATETIME,
            usuario_recepcao TEXT,
            observacao TEXT,
            retirado_por TEXT,
            motivo_nao_recebido TEXT,
            secao_extra TEXT,
            destino_extra TEXT,
            FOREIGN KEY (manifesto_id) REFERENCES manifestos(id),
            UNIQUE(manifesto_id, numero_volume)
        )
    """)

    # Tabela conferencia_volume (v5)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conferencia_volume (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            volume_id INTEGER NOT NULL,
            secao TEXT NOT NULL,
            status TEXT DEFAULT 'PENDENTE',
            quantidade_recebida INTEGER DEFAULT 0,
            data_hora_primeira_recepcao DATETIME,
            data_hora_ultima_recepcao DATETIME,
            usuario_recepcao TEXT,
            retirado_por TEXT,
            motivo_nao_recebido TEXT,
            FOREIGN KEY (volume_id) REFERENCES volumes(id),
            UNIQUE(volume_id, secao)
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

    # Tabela conferencia_caixa (v5)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conferencia_caixa (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            volume_id INTEGER NOT NULL,
            numero_caixa INTEGER NOT NULL,
            secao TEXT NOT NULL,
            status TEXT DEFAULT 'NÃO RECEBIDA',
            data_hora_recepcao DATETIME,
            usuario_conferente TEXT,
            retirado_por TEXT,
            retirado_por_tipo TEXT,
            motivo_nao_recebido TEXT,
            FOREIGN KEY (volume_id) REFERENCES volumes(id),
            UNIQUE(volume_id, numero_caixa, secao)
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
            secao TEXT DEFAULT 'TSRE',
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

    # Tabela volume_observacoes (v4 / v5)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS volume_observacoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            volume_id INTEGER NOT NULL,
            texto TEXT NOT NULL,
            usuario TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            secao TEXT DEFAULT 'TSRE',
            auto_gerada INTEGER DEFAULT 0,
            FOREIGN KEY (volume_id) REFERENCES volumes(id)
        )
    """)

    # Migrações automáticas de colunas legadas e v5 para retrocompatibilidade total
    colunas_migracao = [
        ("users", "secao", "TEXT DEFAULT 'TSRE'"),
        ("manifestos", "origem", "TEXT DEFAULT 'PDF_DIGITAL'"),
        ("manifestos", "secao_origem", "TEXT DEFAULT 'TSRE'"),
        ("volumes", "observacao", "TEXT"),
        ("volumes", "retirado_por", "TEXT"),
        ("volumes", "motivo_nao_recebido", "TEXT"),
        ("volumes", "secao_extra", "TEXT"),
        ("volumes", "destino_extra", "TEXT"),
        ("caixas_individuais", "retirado_por", "TEXT"),
        ("caixas_individuais", "retirado_por_tipo", "TEXT"),
        ("caixas_individuais", "motivo_nao_recebido", "TEXT"),
        ("logs", "secao", "TEXT DEFAULT 'TSRE'"),
        ("volume_observacoes", "secao", "TEXT DEFAULT 'TSRE'"),
        ("volume_observacoes", "auto_gerada", "INTEGER DEFAULT 0"),
    ]
    for tabela, coluna, definicao in colunas_migracao:
        try:
            cursor.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {definicao}")
        except sqlite3.OperationalError:
            pass # A coluna já existe no banco

    # Migração automática de observações legadas de volumes.observacao para volume_observacoes
    try:
        cursor.execute("SELECT id, observacao, data_hora_ultima_recepcao FROM volumes WHERE observacao IS NOT NULL AND TRIM(observacao) != ''")
        volumes_legado = cursor.fetchall()
        agora_br = get_agora_br()
        for vol in volumes_legado:
            vol_id = vol['id']
            obs_texto = str(vol['observacao']).strip()
            data_rec = vol['data_hora_ultima_recepcao'] or agora_br
            
            cursor.execute("SELECT 1 FROM volume_observacoes WHERE volume_id = ? AND texto = ?", (vol_id, obs_texto))
            if not cursor.fetchone():
                cursor.execute("""
                    INSERT INTO volume_observacoes (volume_id, texto, usuario, timestamp)
                    VALUES (?, ?, ?, ?)
                """, (vol_id, obs_texto, 'Legado', data_rec))
    except Exception as e:
        print(f"Aviso na migração de observações legado: {e}")

    # Migração automática de status legados 'NÃO RECEBIDO' sem motivo para 'PENDENTE'
    try:
        cursor.execute("UPDATE volumes SET status = 'PENDENTE' WHERE status = 'NÃO RECEBIDO' AND (motivo_nao_recebido IS NULL OR motivo_nao_recebido = '')")
        cursor.execute("UPDATE manifestos SET status = 'PENDENTE' WHERE status = 'NÃO RECEBIDO'")
        cursor.execute("UPDATE manifesto_secao SET status_conferencia = 'PENDENTE' WHERE status_conferencia = 'NÃO RECEBIDO'")
        cursor.execute("UPDATE conferencia_volume SET status = 'PENDENTE' WHERE status = 'NÃO RECEBIDO' AND (motivo_nao_recebido IS NULL OR motivo_nao_recebido = '')")
    except Exception as e:
        print(f"Aviso na migração de status legado: {e}")

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
                  acao, usuario, estado_anterior=None, estado_posterior=None, secao='TSRE'):
    """Registra ação na trilha de auditoria imutável."""
    agora_utc = get_agora_utc()
    agora_brt = get_agora_br()
    cursor.execute("""
        INSERT INTO logs (manifesto_id, volume_id, caixa_numero, acao,
                         estado_anterior, estado_posterior,
                         usuario, timestamp_utc, timestamp_brt, secao)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        manifesto_id, volume_id, caixa_numero, acao,
        json.dumps(estado_anterior, ensure_ascii=False) if estado_anterior else None,
        json.dumps(estado_posterior, ensure_ascii=False) if estado_posterior else None,
        usuario, agora_utc, agora_brt, secao
    ))


# ═══════════════════════════════════════════════════
# FUNÇÕES DE USUÁRIO (AUTH)
# ═══════════════════════════════════════════════════

def criar_usuario(username, senha, nome, role='operador_tsre', secao='TSRE'):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        pw_hash = generate_password_hash(senha)
        cursor.execute("INSERT INTO users (username, password_hash, nome_completo, role, secao) VALUES (?, ?, ?, ?, ?)",
                      (username, pw_hash, nome, role, secao))
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

def listar_todos_usuarios(secao_filtro=None):
    """Retorna lista de todos os usuários para o painel admin (filtrado opcionalmente por seção)"""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        if secao_filtro:
            cursor.execute("SELECT id, username, nome_completo, role, secao FROM users WHERE secao = ? ORDER BY nome_completo", (secao_filtro,))
        else:
            cursor.execute("SELECT id, username, nome_completo, role, secao FROM users ORDER BY nome_completo")
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


def validar_senha_admin_secao(senha, secao=None):
    """
    Valida se a senha informada pertence a um administrador autorizado para a seção.
    Valida exclusivamente contra os hashes criptográficos dos administradores cadastrados no banco.
    """
    if not senha or not str(senha).strip():
        return False
        
    senha_clean = str(senha).strip()
    sec_clean = (secao or 'TSRE').upper()

    conn = get_connection()
    try:
        cursor = conn.cursor()
        
        # 1. Superadmins (qualquer seção)
        cursor.execute("SELECT password_hash FROM users WHERE role = 'super_admin'")
        for row in cursor.fetchall():
            if check_password_hash(row['password_hash'], senha_clean):
                return True
                
        # 2. Admins da seção indicada
        if sec_clean == 'CAN':
            cursor.execute("SELECT password_hash FROM users WHERE role IN ('admin_can', 'admin') AND (secao = 'CAN' OR secao IS NULL)")
        elif sec_clean == 'TSRE':
            cursor.execute("SELECT password_hash FROM users WHERE role IN ('admin_tsre', 'admin') AND (secao = 'TSRE' OR secao IS NULL)")
        else:
            cursor.execute("SELECT password_hash FROM users WHERE role IN ('admin', 'admin_tsre', 'admin_can')")
            
        for row in cursor.fetchall():
            if check_password_hash(row['password_hash'], senha_clean):
                return True
                
        return False
    finally:
        conn.close()


def manifesto_conferencia_finalizada(volume_id, secao=None):
    """
    Verifica se a conferência do manifesto referente ao volume já foi finalizada para a seção.
    Retorna True se status_conferencia for 'TOTALMENTE RECEBIDO' ou 'TOTAL'.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        sec_ativa = (secao or 'TSRE').upper()
        
        cursor.execute("SELECT manifesto_id FROM volumes WHERE id = ?", (volume_id,))
        v_row = cursor.fetchone()
        if not v_row:
            return False
        mid = v_row['manifesto_id']
        
        cursor.execute("""
            SELECT status_conferencia FROM manifesto_secao 
            WHERE manifesto_id = ? AND secao = ?
        """, (mid, sec_ativa))
        ms = cursor.fetchone()
        if ms and ms['status_conferencia'] in ['TOTALMENTE RECEBIDO', 'TOTAL', 'CONCLUÍDO']:
            return True
            
        if sec_ativa == 'TSRE':
            cursor.execute("SELECT status FROM manifestos WHERE id = ?", (mid,))
            m = cursor.fetchone()
            if m and m['status'] in ['TOTALMENTE RECEBIDO', 'TOTAL']:
                return True
                
        return False
    finally:
        conn.close()


# ═══════════════════════════════════════════════════
# FUNÇÕES DE OBSERVAÇÃO
# ═══════════════════════════════════════════════════

def salvar_observacao(volume_id, texto, usuario='SISTEMA', secao='TSRE'):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        agora = get_agora_br()
        cursor.execute("""
            INSERT INTO volume_observacoes (volume_id, texto, usuario, timestamp, secao)
            VALUES (?, ?, ?, ?, ?)
        """, (volume_id, texto, usuario, agora, secao))
        cursor.execute("UPDATE volumes SET observacao = ? WHERE id = ?", (texto, volume_id))
        conn.commit()
        return True
    except Exception as e:
        print(f"Erro ao salvar observacao: {e}")
        return False
    finally:
        conn.close()


# ═══════════════════════════════════════════════════
# FUNÇÕES DE OBSERVAÇÕES MANUAIS (v4)
# ═══════════════════════════════════════════════════

def adicionar_observacao_manual(volume_id, texto, usuario, secao='TSRE'):
    """Adiciona um comentário manual ao histórico de observações do volume e sincroniza."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        agora = get_agora_br()
        
        # 1. Inserir na tabela de histórico gravando a seção de origem
        cursor.execute("""
            INSERT INTO volume_observacoes (volume_id, texto, usuario, timestamp, secao)
            VALUES (?, ?, ?, ?, ?)
        """, (volume_id, texto, usuario, agora, secao or 'TSRE'))
        
        # 2. Atualizar a coluna observacao consolidada no volume
        cursor.execute("UPDATE volumes SET observacao = ? WHERE id = ?", (texto, volume_id))
        
        conn.commit()
        
        # 3. Sincronizar com Sheets de forma segura
        if secao == 'TSRE':
            try:
                _sincronizar_sheets(cursor, volume_id)
            except Exception as es:
                print(f"Aviso ao sincronizar sheets em adicionar_observacao_manual: {es}")
        
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
        
        # Buscar autor do comentário, volume_id e auto_gerada
        cursor.execute("SELECT usuario, volume_id, auto_gerada FROM volume_observacoes WHERE id = ?", (observacao_id,))
        res = cursor.fetchone()
        if not res:
            return False, "Comentário não encontrado."

        if res['auto_gerada'] == 1 and role not in ['super_admin']:
            return False, "Observações automáticas da outra seção são somente leitura."
            
        autor = res['usuario']
        volume_id = res['volume_id']
        
        if usuario == autor or role in ['admin', 'admin_tsre', 'admin_can', 'super_admin']:
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
            
            # 4. Sincronizar com Sheets (apenas TSRE - R15)
            try:
                _sincronizar_sheets(cursor, volume_id)
            except Exception as es:
                print(f"Aviso ao sincronizar sheets em excluir_observacao_manual: {es}")
            
            return True, "Comentário excluído."
        else:
            return False, "Apenas o autor do comentário ou um administrador podem excluí-lo."
    except Exception as e:
        print(f"Erro ao excluir observacao: {e}")
        return False, str(e)
    finally:
        conn.close()


# ═══════════════════════════════════════════════════
# HELPER FUNCTIONS FOR MULTI-SECTION CONFERENCE (FASE 4)
# ═══════════════════════════════════════════════════

def _garantir_conferencia_existente(cursor, volume_id, secao):
    """Garante que existam registros em conferencia_volume e conferencia_caixa para a seção."""
    cursor.execute("SELECT id, quantidade_expedida, destinatario FROM volumes WHERE id = ?", (volume_id,))
    vol = cursor.fetchone()
    if not vol:
        return
    
    cursor.execute("SELECT id FROM conferencia_volume WHERE volume_id = ? AND secao = ?", (volume_id, secao))
    if not cursor.fetchone():
        cursor.execute("""
            INSERT OR IGNORE INTO conferencia_volume (volume_id, secao, status, quantidade_recebida)
            VALUES (?, ?, 'PENDENTE', 0)
        """, (volume_id, secao))
    
    qtd_exp = vol['quantidade_expedida'] or 1
    for i in range(1, qtd_exp + 1):
        cursor.execute("""
            INSERT OR IGNORE INTO conferencia_caixa (volume_id, numero_caixa, secao, status)
            VALUES (?, ?, ?, 'NÃO RECEBIDA')
        """, (volume_id, i, secao))


def _recalcular_conferencia_volume_secao(cursor, volume_id, secao, agora, usuario):
    """Recalcula status em conferencia_volume para uma seção específica."""
    cursor.execute("""
        SELECT status, usuario_conferente, retirado_por, motivo_nao_recebido 
        FROM conferencia_caixa 
        WHERE volume_id = ? AND secao = ?
    """, (volume_id, secao))
    caixas = [dict(r) for r in cursor.fetchall()]

    if not caixas:
        return

    expedidas = len(caixas)
    recebidas = sum(1 for c in caixas if c['status'] == 'RECEBIDA')
    retiradas = sum(1 for c in caixas if c['status'] == 'RETIRADO POR OUTRA PESSOA')
    nao_recebidas = sum(1 for c in caixas if c['status'] == 'NÃO RECEBIDA' and c['motivo_nao_recebido'])

    resolvidas = recebidas + retiradas + nao_recebidas

    if resolvidas == 0:
        novo_status = 'PENDENTE'
        cursor.execute("""
            UPDATE conferencia_volume SET 
                quantidade_recebida = 0, 
                status = ?, 
                data_hora_ultima_recepcao = NULL, 
                usuario_recepcao = NULL, 
                retirado_por = NULL, 
                motivo_nao_recebido = NULL 
            WHERE volume_id = ? AND secao = ?
        """, (novo_status, volume_id, secao))
    else:
        if recebidas == expedidas:
            novo_status = 'COMPLETO'
        elif retiradas == expedidas:
            novo_status = 'RETIRADO POR OUTRA PESSOA'
        elif nao_recebidas == expedidas:
            novo_status = 'NÃO RECEBIDO'
        else:
            novo_status = 'PARCIAL'

        retirado_list = [c['retirado_por'] for c in caixas if c.get('retirado_por')]
        v_retirado_por = ", ".join(dict.fromkeys(retirado_list)) if retirado_list else None

        motivo_list = [c['motivo_nao_recebido'] for c in caixas if c.get('motivo_nao_recebido')]
        v_motivo = ", ".join(dict.fromkeys(motivo_list)) if motivo_list else None

        cursor.execute("""
            UPDATE conferencia_volume SET 
                quantidade_recebida = ?, 
                status = ?, 
                data_hora_ultima_recepcao = ?, 
                usuario_recepcao = ?,
                retirado_por = ?,
                motivo_nao_recebido = ?
            WHERE volume_id = ? AND secao = ?
        """, (recebidas, novo_status, agora, usuario, v_retirado_por, v_motivo, volume_id, secao))


def _atualizar_status_manifesto_secao(cursor, manifesto_id, secao):
    """Recalcula status_conferencia da tabela manifesto_secao para uma seção."""
    if secao == 'TSRE':
        cursor.execute("""
            SELECT id, quantidade_expedida FROM volumes 
            WHERE manifesto_id = ? AND (destinatario = 'PAMALS' OR UPPER(destinatario) LIKE '%PAMALS%' OR UPPER(destinatario) LIKE '%LAGOA SANTA%' OR UPPER(destinatario) LIKE '%PARQUE DE MATERIAL%')
        """, (manifesto_id,))
    else:
        cursor.execute("SELECT id, quantidade_expedida FROM volumes WHERE manifesto_id = ?", (manifesto_id,))
    
    vols = cursor.fetchall()
    if not vols:
        novo_st = 'PENDENTE'
    else:
        vol_ids = [v['id'] for v in vols]
        total_caixas = sum(v['quantidade_expedida'] for v in vols) or 1
        
        placeholders = ','.join(['?'] * len(vol_ids))
        cursor.execute(f"""
            SELECT COUNT(*) as r FROM conferencia_caixa
            WHERE volume_id IN ({placeholders}) AND secao = ?
              AND (status = 'RECEBIDA'
                   OR status = 'RETIRADO POR OUTRA PESSOA'
                   OR (status = 'NÃO RECEBIDA' AND motivo_nao_recebido IS NOT NULL AND motivo_nao_recebido != ''))
        """, (*vol_ids, secao))
        resolvidas = cursor.fetchone()['r'] or 0

        if resolvidas == 0:
            novo_st = 'PENDENTE'
        elif resolvidas >= total_caixas:
            novo_st = 'TOTALMENTE RECEBIDO'
        else:
            novo_st = 'PARCIALMENTE RECEBIDO'

    cursor.execute("""
        UPDATE manifesto_secao 
        SET status_conferencia = ? 
        WHERE manifesto_id = ? AND secao = ?
    """, (novo_st, manifesto_id, secao))

    if secao == 'TSRE':
        cursor.execute("UPDATE manifestos SET status = ? WHERE id = ?", (novo_st, manifesto_id))


def criar_obs_automatica_cruzada(cursor, volume_id, secao_destino, usuario, texto):
    """Cria observação automática cruzada na secao_destino (auto_gerada = 1)."""
    agora = get_agora_br()
    cursor.execute("""
        INSERT INTO volume_observacoes (volume_id, texto, usuario, timestamp, secao, auto_gerada)
        VALUES (?, ?, ?, ?, ?, 1)
    """, (volume_id, texto, usuario, agora, secao_destino))
    
    if secao_destino == 'TSRE':
        cursor.execute("UPDATE volumes SET observacao = ? WHERE id = ?", (texto, volume_id))


def _obter_status_cruzada_interna(cursor, manifesto_id):
    """Mapeia indicadores cruzados no nível do manifesto."""
    cursor.execute("SELECT secao, status_conferencia FROM manifesto_secao WHERE manifesto_id = ?", (manifesto_id,))
    rows = cursor.fetchall()
    
    tsre_st = 'PENDENTE'
    can_st = 'PENDENTE'
    for r in rows:
        if r['secao'] == 'TSRE':
            tsre_st = r['status_conferencia'] or 'PENDENTE'
        elif r['secao'] == 'CAN':
            can_st = r['status_conferencia'] or 'PENDENTE'

    if tsre_st == 'PENDENTE':
        cursor.execute("SELECT status FROM manifestos WHERE id = ?", (manifesto_id,))
        m = cursor.fetchone()
        if m and m['status'] and m['status'] not in ['PENDENTE', 'NÃO RECEBIDO']:
            tsre_st = m['status']

    tsre_conferiu = (tsre_st in ['PARCIALMENTE RECEBIDO', 'TOTALMENTE RECEBIDO', 'PARCIAL', 'TOTAL'])
    can_conferiu = (can_st in ['PARCIALMENTE RECEBIDO', 'TOTALMENTE RECEBIDO', 'PARCIAL', 'TOTAL'])

    if can_conferiu and tsre_conferiu:
        indicador = 'DOUBLE_CHECK'
    elif can_conferiu and not tsre_conferiu:
        indicador = 'CHECK'
    elif tsre_conferiu and not can_conferiu:
        indicador = 'CIRCLE'
    else:
        indicador = 'NONE'

    return {
        'tsre_conferiu': tsre_conferiu,
        'can_conferiu': can_conferiu,
        'indicador': indicador
    }


def obter_status_conferencia_cruzada(manifesto_id: int) -> dict:
    """Retorna dict com status de conferência cruzada para um manifesto."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        return _obter_status_cruzada_interna(cursor, manifesto_id)
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


def obter_info_fixas_volume(volume_id, secao=None):
    """Retorna informações de controle fixas (retirado_por, motivo_nao_recebido) para a seção."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        sec_ativa = secao or 'TSRE'
        _garantir_conferencia_existente(cursor, volume_id, sec_ativa)

        cursor.execute("""
            SELECT status, retirado_por, motivo_nao_recebido 
            FROM conferencia_volume WHERE volume_id = ? AND secao = ?
        """, (volume_id, sec_ativa))
        res = cursor.fetchone()
        
        # Se a seção tiver retirado_por ou motivo_nao_recebido definidos
        ret_por = res['retirado_por'] if res else None
        mot_nao = res['motivo_nao_recebido'] if res else None
        status_vol = res['status'] if res else 'PENDENTE'

        # Se vazio em conferencia_volume, agregar de conferencia_caixa daquela seção
        if not ret_por or not mot_nao:
            cursor.execute("""
                SELECT DISTINCT retirado_por, motivo_nao_recebido FROM conferencia_caixa 
                WHERE volume_id = ? AND secao = ?
            """, (volume_id, sec_ativa))
            c_rows = cursor.fetchall()
            if not ret_por:
                rets = [r['retirado_por'] for r in c_rows if r['retirado_por']]
                if rets:
                    ret_por = ", ".join(dict.fromkeys(rets))
            if not mot_nao:
                mots = [r['motivo_nao_recebido'] for r in c_rows if r['motivo_nao_recebido']]
                if mots:
                    mot_nao = ", ".join(dict.fromkeys(mots))

        # Se ainda vazio, buscar em qualquer conferencia_volume de outra seção
        if not ret_por or not mot_nao:
            cursor.execute("""
                SELECT retirado_por, motivo_nao_recebido FROM conferencia_volume 
                WHERE volume_id = ? AND (
                    (retirado_por IS NOT NULL AND retirado_por != '') OR 
                    (motivo_nao_recebido IS NOT NULL AND motivo_nao_recebido != '')
                )
            """, (volume_id,))
            c_any = cursor.fetchone()
            if c_any:
                ret_por = ret_por or c_any['retirado_por']
                mot_nao = mot_nao or c_any['motivo_nao_recebido']

        if not ret_por and not mot_nao:
            cursor.execute("SELECT status, retirado_por, motivo_nao_recebido FROM volumes WHERE id = ?", (volume_id,))
            res_leg = cursor.fetchone()
            if res_leg:
                ret_por = ret_por or res_leg['retirado_por']
                mot_nao = mot_nao or res_leg['motivo_nao_recebido']
                status_vol = status_vol if status_vol != 'PENDENTE' else res_leg['status']

        return {
            'status': status_vol,
            'retirado_por': ret_por or '',
            'motivo_nao_recebido': mot_nao or ''
        }
    finally:
        conn.close()


def atualizar_info_fixas_volume(volume_id, retirado_por, motivo_nao_recebido, usuario_executor, secao='TSRE'):
    """Atualiza as informações fixas para a seção indicada."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        agora = get_agora_br()
        manifesto_id = _obter_manifesto_id_por_volume(cursor, volume_id)
        _garantir_conferencia_existente(cursor, volume_id, secao)
        
        estado_ant = _snapshot_volume(cursor, volume_id)
        
        cursor.execute("""
            UPDATE conferencia_volume SET 
                retirado_por = ?,
                motivo_nao_recebido = ?
            WHERE volume_id = ? AND secao = ?
        """, (retirado_por, motivo_nao_recebido, volume_id, secao))
        
        cursor.execute("""
            UPDATE conferencia_caixa SET
                retirado_por = ?,
                motivo_nao_recebido = ?
            WHERE volume_id = ? AND secao = ?
        """, (retirado_por, motivo_nao_recebido, volume_id, secao))
        
        _recalcular_conferencia_volume_secao(cursor, volume_id, secao, agora, usuario_executor)
        _atualizar_status_manifesto_secao(cursor, manifesto_id, secao)

        if secao == 'TSRE':
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
            estado_ant, estado_pos, secao=secao
        )
        
        conn.commit()
        if secao == 'TSRE':
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

def listar_manifestos(filtro_num=None, filtro_status=None, data_ini=None, data_fim=None, secao=None):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        
        secao_ativa = secao or 'TSRE'
        if secao_ativa == 'CAN':
            secao_join = "JOIN manifesto_secao ms ON m.id = ms.manifesto_id AND ms.secao = 'CAN'"
            secao_where = "AND ms.excluido = 0 AND ms.status_autorizacao = 'AUTORIZADO'"
            count_rec_query = """(SELECT COUNT(*) FROM conferencia_caixa cc
                                  JOIN volumes vol ON cc.volume_id = vol.id
                                  WHERE vol.manifesto_id = m.id AND cc.secao = 'CAN'
                                    AND (cc.status = 'RECEBIDA'
                                         OR cc.status = 'RETIRADO POR OUTRA PESSOA'
                                         OR (cc.status = 'NÃO RECEBIDA' AND cc.motivo_nao_recebido IS NOT NULL AND cc.motivo_nao_recebido != ''))) as total_caixas_recebidas"""
            vol_where = ""
        else:
            secao_join = "LEFT JOIN manifesto_secao ms ON m.id = ms.manifesto_id AND ms.secao = 'TSRE'"
            secao_where = "AND (ms.id IS NULL OR (ms.excluido = 0 AND ms.status_autorizacao = 'AUTORIZADO'))"
            count_rec_query = """(SELECT COUNT(*) FROM conferencia_caixa cc
                                  JOIN volumes vol ON cc.volume_id = vol.id
                                  WHERE vol.manifesto_id = m.id AND cc.secao = 'TSRE'
                                    AND (vol.destinatario = 'PAMALS' OR UPPER(vol.destinatario) LIKE '%PAMALS%' OR UPPER(vol.destinatario) LIKE '%LAGOA SANTA%' OR UPPER(vol.destinatario) LIKE '%PARQUE DE MATERIAL%')
                                    AND (cc.status = 'RECEBIDA'
                                         OR cc.status = 'RETIRADO POR OUTRA PESSOA'
                                         OR (cc.status = 'NÃO RECEBIDA' AND cc.motivo_nao_recebido IS NOT NULL AND cc.motivo_nao_recebido != ''))) as total_caixas_recebidas"""
            vol_where = "AND (v.destinatario = 'PAMALS' OR UPPER(v.destinatario) LIKE '%PAMALS%' OR UPPER(v.destinatario) LIKE '%LAGOA SANTA%' OR UPPER(v.destinatario) LIKE '%PARQUE DE MATERIAL%')"

        query = f"""
            SELECT m.*,
                   ms.status_conferencia AS status_conferencia_secao,
                   COUNT(DISTINCT v.id) as total_volumes,
                   SUM(v.quantidade_expedida) as total_caixas_expedidas,
                   {count_rec_query}
            FROM manifestos m
            {secao_join}
            LEFT JOIN volumes v ON m.id = v.manifesto_id {vol_where}
            WHERE 1=1 {secao_where}
        """
        params = []
        if filtro_num:
            query += " AND m.numero_manifesto LIKE ?"
            params.append(f"%{filtro_num}%")
        if filtro_status and filtro_status != "TODOS":
            if secao_ativa == 'CAN':
                query += " AND ms.status_conferencia = ?"
            else:
                query += " AND COALESCE(ms.status_conferencia, m.status) = ?"
            params.append(filtro_status)
        query += " GROUP BY m.id ORDER BY m.id DESC"
        cursor.execute(query, params)
        resultados = [dict(row) for row in cursor.fetchall()]

        # Processar status da seção consultada
        for r in resultados:
            if secao_ativa == 'CAN':
                r['status'] = r.get('status_conferencia_secao') or 'PENDENTE'
            else:
                r['status'] = r.get('status_conferencia_secao') or r.get('status') or 'PENDENTE'

            # Fallback de contagem para TSRE caso conferencia_caixa ainda esteja vazia
            if secao_ativa == 'TSRE' and (r['total_caixas_recebidas'] is None or r['total_caixas_recebidas'] == 0):
                cursor.execute("""
                    SELECT COUNT(*) as rec FROM caixas_individuais ci
                    JOIN volumes vol ON ci.volume_id = vol.id
                    WHERE vol.manifesto_id = ?
                      AND (vol.destinatario = 'PAMALS' OR UPPER(vol.destinatario) LIKE '%PAMALS%' OR UPPER(vol.destinatario) LIKE '%LAGOA SANTA%' OR UPPER(vol.destinatario) LIKE '%PARQUE DE MATERIAL%')
                      AND (ci.status = 'RECEBIDA'
                           OR ci.status = 'RETIRADO POR OUTRA PESSOA'
                           OR (ci.status = 'NÃO RECEBIDA' AND ci.motivo_nao_recebido IS NOT NULL AND ci.motivo_nao_recebido != ''))
                """, (r['id'],))
                r['total_caixas_recebidas'] = cursor.fetchone()['rec'] or 0

            # Adicionar status de conferência cruzada (R03)
            cruzado = _obter_status_cruzada_interna(cursor, r['id'])
            r['indicador_cruzado'] = cruzado['indicador']
            r['tsre_conferiu'] = cruzado['tsre_conferiu']
            r['can_conferiu'] = cruzado['can_conferiu']

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


def buscar_volumes_geral(filtro_vol, secao=None):
    """
    Retorna volumes encontrados na pesquisa geral com dados e status específicos da seção consultada.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        sec_ativa = (secao or 'TSRE').upper()
        
        if sec_ativa == 'CAN':
            query = """
                SELECT v.*, m.numero_manifesto 
                FROM volumes v 
                JOIN manifestos m ON v.manifesto_id = m.id 
                JOIN manifesto_secao ms ON m.id = ms.manifesto_id AND ms.secao = 'CAN'
                WHERE v.numero_volume LIKE ? AND ms.excluido = 0
                ORDER BY v.id DESC LIMIT 50
            """
        else:
            query = """
                SELECT v.*, m.numero_manifesto 
                FROM volumes v 
                JOIN manifestos m ON v.manifesto_id = m.id 
                LEFT JOIN manifesto_secao ms ON m.id = ms.manifesto_id AND ms.secao = 'TSRE'
                WHERE v.numero_volume LIKE ? 
                  AND (ms.id IS NULL OR (ms.excluido = 0 AND ms.status_autorizacao = 'AUTORIZADO'))
                  AND (v.destinatario = 'PAMALS' OR UPPER(v.destinatario) LIKE '%PAMALS%' OR UPPER(v.destinatario) LIKE '%LAGOA SANTA%' OR UPPER(v.destinatario) LIKE '%PARQUE DE MATERIAL%' OR v.secao_extra = 'TSRE' OR v.destino_extra = 'PAMA-LS')
                ORDER BY v.id DESC LIMIT 50
            """

        cursor.execute(query, (f"%{filtro_vol}%",))
        volumes = [dict(row) for row in cursor.fetchall()]
        
        for v in volumes:
            _garantir_conferencia_existente(cursor, v['id'], sec_ativa)

            # Verificar permissão de operação da seção (PAMALS para TSRE)
            if v.get('secao_extra'):
                if v.get('secao_extra') == sec_ativa:
                    pode_operar = True
                elif sec_ativa == 'TSRE' and v.get('destino_extra') == 'PAMA-LS':
                    pode_operar = True
                else:
                    pode_operar = False
            elif sec_ativa == 'TSRE':
                pode_operar = (v['destinatario'] == 'PAMALS' or _e_destinatario_pamals(v['destinatario']))
            else:
                cursor.execute("""
                    SELECT status_autorizacao FROM manifesto_secao 
                    WHERE manifesto_id = ? AND secao = 'CAN' AND excluido = 0
                """, (v['manifesto_id'],))
                m_sec = cursor.fetchone()
                pode_operar = bool(m_sec and m_sec['status_autorizacao'] == 'AUTORIZADO')
            
            v['pode_operar'] = pode_operar

            # Buscar dados de conferência específicos da seção pesquisada
            cursor.execute("""
                SELECT * FROM conferencia_volume WHERE volume_id = ? AND secao = ?
            """, (v['id'], sec_ativa))
            cv = cursor.fetchone()
            
            if cv and cv['status']:
                v['status'] = cv['status']
                v['quantidade_recebida'] = cv['quantidade_recebida'] or 0
                v['data_hora_ultima_recepcao'] = cv['data_hora_ultima_recepcao']
                v['retirado_por'] = cv['retirado_por']
                v['motivo_nao_recebido'] = cv['motivo_nao_recebido']
                v['usuario_recepcao'] = cv['usuario_recepcao']
            else:
                v['status'] = 'PENDENTE'
                v['quantidade_recebida'] = 0
                v['data_hora_ultima_recepcao'] = None
                v['retirado_por'] = None
                v['motivo_nao_recebido'] = None
                v['usuario_recepcao'] = None

            cursor.execute("""
                SELECT DISTINCT usuario_conferente FROM conferencia_caixa 
                WHERE volume_id = ? AND secao = ? AND usuario_conferente IS NOT NULL AND usuario_conferente != ''
            """, (v['id'], sec_ativa))
            conferentes = [r['usuario_conferente'] for r in cursor.fetchall()]
            
            if not conferentes and sec_ativa == 'TSRE':
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
            if not v.get('usuario_recepcao'):
                v['usuario_recepcao'] = "-"

            # Recuperar a última observação (priorizando seção ativa, fallback para qualquer seção)
            cursor.execute("""
                SELECT texto FROM volume_observacoes 
                WHERE volume_id = ? 
                ORDER BY (CASE WHEN secao = ? THEN 1 ELSE 2 END), timestamp DESC, id DESC LIMIT 1
            """, (v['id'], sec_ativa))
            obs_row = cursor.fetchone()
            if obs_row:
                v['observacao'] = obs_row['texto']

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


def _e_destinatario_pamals(destinatario: str) -> bool:
    """Verifica se o destinatário é PAMALS ou suas variações."""
    if not destinatario: return False
    dest = destinatario.upper().strip()
    palavras_chave = ['PAMALS', 'PAMA-LS', 'PAMA LS', 'LAGOA SANTA', 'LS PAMA', 'PARQUE DE MATERIAL']
    for p in palavras_chave:
        if p in dest:
            return True
    return False


def listar_volumes_detalhado(manifesto_id, secao=None):
    """
    Retorna a listagem detalhada de volumes de um manifesto.
    v4: Concatenar recebedores se houver mais de um conferente nas caixas.
    v5: Suporte a filtro por seção (TSRE apenas PAMALS) e conferência isolada por seção.
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM volumes WHERE manifesto_id=? ORDER BY remetente, numero_volume", (manifesto_id,))
        volumes = [dict(r) for r in cur.fetchall()]
        
        if secao == 'TSRE':
            def _visivel_na_tsre(v):
                secao_extra = v.get('secao_extra')
                if secao_extra is None:
                    # Volume normal: filtrar por destinatário PAMALS
                    return v['destinatario'] == 'PAMALS' or _e_destinatario_pamals(v['destinatario'])
                if secao_extra == 'TSRE':
                    # Volume extra criado pela própria TSRE: sempre visível
                    return True
                # Volume extra de outra seção (CAN): visível na TSRE apenas se destino for PAMA-LS
                return v.get('destino_extra') == 'PAMA-LS'
            volumes = [v for v in volumes if _visivel_na_tsre(v)]
            
        sec_ativa = secao or 'TSRE'
        for v in volumes:
            _garantir_conferencia_existente(cur, v['id'], sec_ativa)
            
            if v.get('secao_extra'):
                if v.get('secao_extra') == sec_ativa:
                    pode_operar = True
                elif sec_ativa == 'TSRE' and v.get('destino_extra') == 'PAMA-LS':
                    pode_operar = True
                else:
                    pode_operar = False
            else:
                pode_operar = (sec_ativa != 'TSRE' or (v['destinatario'] == 'PAMALS' or _e_destinatario_pamals(v['destinatario'])))
            v['pode_operar'] = pode_operar
            
            cur.execute("SELECT * FROM conferencia_volume WHERE volume_id = ? AND secao = ?", (v['id'], sec_ativa))
            cv = cur.fetchone()
            
            if cv and cv['status'] and cv['status'] != 'PENDENTE':
                v['status'] = cv['status']
                v['quantidade_recebida'] = cv['quantidade_recebida'] or 0
                v['data_hora_ultima_recepcao'] = cv['data_hora_ultima_recepcao']
                v['retirado_por'] = cv['retirado_por']
                v['motivo_nao_recebido'] = cv['motivo_nao_recebido']
                v['usuario_recepcao'] = cv['usuario_recepcao']
            
            cur.execute("""
                SELECT DISTINCT usuario_conferente FROM conferencia_caixa 
                WHERE volume_id = ? AND secao = ? AND usuario_conferente IS NOT NULL AND usuario_conferente != ''
            """, (v['id'], sec_ativa))
            conferentes = [r['usuario_conferente'] for r in cur.fetchall()]
            
            if not conferentes and sec_ativa == 'TSRE':
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
            if not v.get('usuario_recepcao'):
                v['usuario_recepcao'] = "-"

            # Recuperar a última observação (priorizando seção ativa, fallback para qualquer seção)
            cur.execute("""
                SELECT texto FROM volume_observacoes 
                WHERE volume_id = ? 
                ORDER BY (CASE WHEN secao = ? THEN 1 ELSE 2 END), timestamp DESC, id DESC LIMIT 1
            """, (v['id'], sec_ativa))
            obs_row = cur.fetchone()
            if obs_row:
                v['observacao'] = obs_row['texto']

            # R04: Informação visual do status da conferência no CAN para a TSRE
            cur.execute("SELECT * FROM conferencia_volume WHERE volume_id = ? AND secao = 'CAN'", (v['id'],))
            can_cv = cur.fetchone()
            if can_cv and can_cv['status'] and can_cv['status'] != 'PENDENTE':
                v['can_conferido'] = True
                v['can_status'] = can_cv['status']
                v['can_recebedor'] = can_cv['usuario_recepcao']
                v['can_retirado_por'] = can_cv['retirado_por']
                v['can_motivo_nao_recebido'] = can_cv['motivo_nao_recebido']
                v['can_data'] = can_cv['data_hora_ultima_recepcao']
            else:
                v['can_conferido'] = False

        return volumes
    finally:
        conn.close()


def obter_caixas_por_volume(volume_id, secao=None):
    """Retorna caixas com dados completos de conferente individual (com suporte a seção)."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        sec_ativa = secao or 'TSRE'
        _garantir_conferencia_existente(cursor, volume_id, sec_ativa)
        
        # Buscar dados de nível de volume na seção ativa
        cursor.execute("SELECT status, retirado_por, motivo_nao_recebido FROM conferencia_volume WHERE volume_id=? AND secao=?", (volume_id, sec_ativa))
        vol_info = cursor.fetchone()
        ret_vol = vol_info['retirado_por'] if vol_info else None
        mot_vol = vol_info['motivo_nao_recebido'] if vol_info else None
        st_vol = vol_info['status'] if vol_info else None

        # Se nulo, buscar de qualquer outra seção
        if not ret_vol and not mot_vol:
            cursor.execute("SELECT retirado_por, motivo_nao_recebido FROM conferencia_volume WHERE volume_id=? AND (retirado_por IS NOT NULL OR motivo_nao_recebido IS NOT NULL)", (volume_id,))
            vol_any = cursor.fetchone()
            if vol_any:
                ret_vol = vol_any['retirado_por']
                mot_vol = vol_any['motivo_nao_recebido']

        cursor.execute("SELECT * FROM conferencia_caixa WHERE volume_id=? AND secao=? ORDER BY numero_caixa", (volume_id, sec_ativa))
        rows = [dict(r) for r in cursor.fetchall()]
        if rows:
            for r in rows:
                if not r.get('retirado_por') and ret_vol:
                    r['retirado_por'] = ret_vol
                if not r.get('motivo_nao_recebido') and mot_vol:
                    r['motivo_nao_recebido'] = mot_vol
                if st_vol in ['RETIRADO POR OUTRA PESSOA', 'NÃO RECEBIDO'] and r['status'] == 'NÃO RECEBIDA':
                    r['status'] = st_vol
            return rows

        cursor.execute("SELECT * FROM caixas_individuais WHERE volume_id=? ORDER BY numero_caixa", (volume_id,))
        rows_leg = [dict(r) for r in cursor.fetchall()]
        for r in rows_leg:
            if not r.get('retirado_por') and ret_vol:
                r['retirado_por'] = ret_vol
            if not r.get('motivo_nao_recebido') and mot_vol:
                r['motivo_nao_recebido'] = mot_vol
            if st_vol in ['RETIRADO POR OUTRA PESSOA', 'NÃO RECEBIDO'] and r['status'] == 'NÃO RECEBIDA':
                r['status'] = st_vol
        return rows_leg
    finally:
        conn.close()


def obter_estatisticas_manifesto(manifesto_id, secao=None):
    conn = get_connection()
    try:
        c = conn.cursor()
        sec_ativa = secao or 'TSRE'
        if sec_ativa == 'TSRE':
            c.execute("""
                SELECT COUNT(DISTINCT id) as total_volumes, SUM(quantidade_expedida) as total_caixas_expedidas 
                FROM volumes 
                WHERE manifesto_id=? AND (destinatario = 'PAMALS' OR UPPER(destinatario) LIKE '%PAMALS%' OR UPPER(destinatario) LIKE '%LAGOA SANTA%' OR UPPER(destinatario) LIKE '%PARQUE DE MATERIAL%')
            """, (manifesto_id,))
            row = dict(c.fetchone())
            
            c.execute("""
                SELECT COUNT(*) as total_caixas_recebidas FROM conferencia_caixa cc
                JOIN volumes v ON cc.volume_id = v.id
                WHERE v.manifesto_id = ? AND cc.secao = 'TSRE'
                  AND (v.destinatario = 'PAMALS' OR UPPER(v.destinatario) LIKE '%PAMALS%' OR UPPER(v.destinatario) LIKE '%LAGOA SANTA%' OR UPPER(v.destinatario) LIKE '%PARQUE DE MATERIAL%')
                  AND (cc.status = 'RECEBIDA'
                       OR cc.status = 'RETIRADO POR OUTRA PESSOA'
                       OR (cc.status = 'NÃO RECEBIDA' AND cc.motivo_nao_recebido IS NOT NULL AND cc.motivo_nao_recebido != ''))
            """, (manifesto_id,))
            rec = c.fetchone()['total_caixas_recebidas'] or 0
            
            if rec == 0: # Fallback para caixas_individuais
                c.execute("""
                    SELECT COUNT(*) as total_caixas_recebidas FROM caixas_individuais ci
                    JOIN volumes v ON ci.volume_id = v.id
                    WHERE v.manifesto_id = ?
                      AND (v.destinatario = 'PAMALS' OR UPPER(v.destinatario) LIKE '%PAMALS%' OR UPPER(v.destinatario) LIKE '%LAGOA SANTA%' OR UPPER(v.destinatario) LIKE '%PARQUE DE MATERIAL%')
                      AND (ci.status = 'RECEBIDA'
                           OR ci.status = 'RETIRADO POR OUTRA PESSOA'
                           OR (ci.status = 'NÃO RECEBIDA' AND ci.motivo_nao_recebido IS NOT NULL AND ci.motivo_nao_recebido != ''))
                """, (manifesto_id,))
                rec = c.fetchone()['total_caixas_recebidas'] or 0
            row['total_caixas_recebidas'] = rec
        else: # CAN
            c.execute("SELECT COUNT(DISTINCT id) as total_volumes, SUM(quantidade_expedida) as total_caixas_expedidas FROM volumes WHERE manifesto_id=?", (manifesto_id,))
            row = dict(c.fetchone())
            
            c.execute("""
                SELECT COUNT(*) as total_caixas_recebidas FROM conferencia_caixa cc
                JOIN volumes v ON cc.volume_id = v.id
                WHERE v.manifesto_id = ? AND cc.secao = 'CAN'
                  AND (cc.status = 'RECEBIDA'
                       OR cc.status = 'RETIRADO POR OUTRA PESSOA'
                       OR (cc.status = 'NÃO RECEBIDA' AND cc.motivo_nao_recebido IS NOT NULL AND cc.motivo_nao_recebido != ''))
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

def criar_manifesto(numero: str, data: str, origem_terminal: str, destino: str, missao: str, aeronave: str, pdf_path: str, origem_registro: str = 'PDF_DIGITAL', usuario: str = None, secao_origem: str = 'TSRE') -> int:
    """Cria um novo manifesto ou reativa um existente para a seção criadora e sincroniza com o Google Sheets."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        agora = get_agora_br()
        sec_orig = (secao_origem or 'TSRE').upper()

        cursor.execute("SELECT id FROM manifestos WHERE numero_manifesto = ?", (numero,))
        m_row = cursor.fetchone()

        if m_row:
            mid = m_row['id']
            cursor.execute("""
                UPDATE manifestos SET 
                    data_manifesto = ?, terminal_origem = ?, terminal_destino = ?, 
                    missao = ?, aeronave = ?, pdf_path = ?, origem = ?, usuario_responsavel = ?
                WHERE id = ?
            """, (data, origem_terminal, destino, missao, aeronave, pdf_path, origem_registro, usuario, mid))
        else:
            cursor.execute(
                "INSERT INTO manifestos (numero_manifesto, data_manifesto, terminal_origem, terminal_destino, missao, aeronave, pdf_path, origem, secao_origem, usuario_responsavel) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (numero, data, origem_terminal, destino, missao, aeronave, pdf_path, origem_registro, sec_orig, usuario)
            )
            mid = cursor.lastrowid

        # Ativa/reativa a seção que está registrando o manifesto
        cursor.execute("""
            INSERT INTO manifesto_secao (manifesto_id, secao, status_conferencia, status_autorizacao, autorizado_por, data_autorizacao, excluido, data_exclusao)
            VALUES (?, ?, 'PENDENTE', 'AUTORIZADO', ?, ?, 0, NULL)
            ON CONFLICT(manifesto_id, secao) DO UPDATE SET
                status_conferencia = 'PENDENTE',
                status_autorizacao = 'AUTORIZADO',
                autorizado_por = excluded.autorizado_por,
                data_autorizacao = excluded.data_autorizacao,
                excluido = 0,
                data_exclusao = NULL
        """, (mid, sec_orig, usuario or 'SISTEMA', agora))

        # Garantir registro para a outra seção (se novo)
        outra_secao = 'CAN' if sec_orig == 'TSRE' else 'TSRE'
        cursor.execute("""
            INSERT OR IGNORE INTO manifesto_secao (manifesto_id, secao, status_conferencia, status_autorizacao, autorizado_por, data_autorizacao, excluido)
            VALUES (?, ?, 'PENDENTE', 'AUTORIZADO', 'SISTEMA_AUTO', ?, 0)
        """, (mid, outra_secao, agora))

        conn.commit()
        if sec_orig == 'TSRE':
            run_async_sync(sheets.sincronizar_manifesto, {'numero_manifesto': numero, 'status': 'PENDENTE', 'terminal_origem': origem_terminal, 'terminal_destino': destino})
        return mid
    finally:
        conn.close()


def adicionar_volume(manifesto_id, remetente, destinatario, numero_volume, quantidade_exp, secao_origem='TSRE', **kwargs):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        status_init = 'PENDENTE'
        prioridade = kwargs.get('prioridade')
        
        cursor.execute("SELECT id FROM volumes WHERE manifesto_id = ? AND numero_volume = ?", (manifesto_id, numero_volume))
        v_exist = cursor.fetchone()

        if v_exist:
            vid = v_exist['id']
            cursor.execute("""
                UPDATE volumes SET 
                    remetente = ?, destinatario = ?, quantidade_expedida = ?, peso_total = ?, cubagem = ?, 
                    prioridade = ?, tipo_material = ?, embalagem = ?, status = 'PENDENTE', 
                    secao_extra = ?, destino_extra = ?
                WHERE id = ?
            """, (remetente, destinatario, quantidade_exp, kwargs.get('peso'), kwargs.get('cubagem'), prioridade, kwargs.get('tipo_material'), kwargs.get('embalagem'), kwargs.get('secao_extra'), kwargs.get('destino_extra'), vid))
        else:
            cursor.execute("""
                INSERT INTO volumes (manifesto_id, remetente, destinatario, numero_volume, quantidade_expedida, peso_total, cubagem, prioridade, tipo_material, embalagem, status, secao_extra, destino_extra) 
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (manifesto_id, remetente, destinatario, numero_volume, quantidade_exp, kwargs.get('peso'), kwargs.get('cubagem'), prioridade, kwargs.get('tipo_material'), kwargs.get('embalagem'), status_init, kwargs.get('secao_extra'), kwargs.get('destino_extra')))
            vid = cursor.lastrowid
            
            for i in range(1, quantidade_exp + 1):
                cursor.execute("INSERT OR IGNORE INTO caixas_individuais (volume_id, numero_caixa) VALUES (?,?)", (vid, i))

        # Inserir/garantir conferencia_volume e conferencia_caixa para seções autorizadas e ativas
        cursor.execute("SELECT secao, status_autorizacao FROM manifesto_secao WHERE manifesto_id = ? AND excluido = 0", (manifesto_id,))
        secoes_info = cursor.fetchall()
        for s_row in secoes_info:
            sec = s_row['secao']
            if s_row['status_autorizacao'] == 'AUTORIZADO':
                if sec == 'TSRE' and not (destinatario == 'PAMALS' or _e_destinatario_pamals(destinatario)):
                    continue
                cursor.execute("""
                    INSERT OR IGNORE INTO conferencia_volume (volume_id, secao, status, quantidade_recebida)
                    VALUES (?, ?, 'PENDENTE', 0)
                """, (vid, sec))
                for i in range(1, quantidade_exp + 1):
                    cursor.execute("""
                        INSERT OR IGNORE INTO conferencia_caixa (volume_id, numero_caixa, secao, status)
                        VALUES (?, ?, ?, 'NÃO RECEBIDA')
                    """, (vid, i, sec))

        conn.commit()

        # Sync Imediato (Apenas TSRE - R15)
        cursor.execute("SELECT numero_manifesto FROM manifestos WHERE id=?", (manifesto_id,))
        man = cursor.fetchone()
        if man and secao_origem == 'TSRE':
             status_sync = 'VOLUME EXTRA' if prioridade == 'EXTRA' else 'PENDENTE'
             run_async_sync(sheets.sincronizar_volume, man['numero_manifesto'], {
                 'remetente': remetente, 'destinatario': destinatario, 'numero_volume': numero_volume,
                 'quantidade_expedida': quantidade_exp, 'quantidade_recebida': 0, 'status': status_sync
             })
        return vid
    finally:
        conn.close()


def autorizar_manifesto(manifesto_id: int, secao: str, usuario: str) -> bool:
    """Autoriza a visualização/conferência de um manifesto para a seção indicada."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        agora = get_agora_br()
        
        cursor.execute("""
            UPDATE manifesto_secao 
            SET status_autorizacao = 'AUTORIZADO', autorizado_por = ?, data_autorizacao = ?
            WHERE manifesto_id = ? AND secao = ?
        """, (usuario, agora, manifesto_id, secao))
        
        # Popular conferencia_volume e conferencia_caixa para a seção recém-autorizada
        cursor.execute("SELECT * FROM volumes WHERE manifesto_id = ?", (manifesto_id,))
        vols = cursor.fetchall()
        for v in vols:
            if secao == 'TSRE' and not (v['destinatario'] == 'PAMALS' or _e_destinatario_pamals(v['destinatario'])):
                continue
                
            cursor.execute("""
                INSERT OR IGNORE INTO conferencia_volume (volume_id, secao, status, quantidade_recebida)
                VALUES (?, ?, 'PENDENTE', 0)
            """, (v['id'], secao))
            
            qtd_exp = v['quantidade_expedida'] or 1
            for i in range(1, qtd_exp + 1):
                cursor.execute("""
                    INSERT OR IGNORE INTO conferencia_caixa (volume_id, numero_caixa, secao, status)
                    VALUES (?, ?, ?, 'NÃO RECEBIDA')
                """, (v['id'], i, secao))
                
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"Erro ao autorizar manifesto: {e}")
        return False
    finally:
        conn.close()


def negar_manifesto(manifesto_id: int, secao: str, usuario: str) -> bool:
    """Nega a autorização de um manifesto para a seção indicada."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        agora = get_agora_br()
        cursor.execute("""
            UPDATE manifesto_secao 
            SET status_autorizacao = 'NEGADO', autorizado_por = ?, data_autorizacao = ?
            WHERE manifesto_id = ? AND secao = ?
        """, (usuario, agora, manifesto_id, secao))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"Erro ao negar manifesto: {e}")
        return False
    finally:
        conn.close()


def listar_manifestos_pendentes(secao: str) -> list:
    """Retorna a lista de manifestos pendentes de autorização para a seção."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT m.*, ms.status_autorizacao,
                   COUNT(DISTINCT v.id) as total_volumes
            FROM manifestos m
            JOIN manifesto_secao ms ON m.id = ms.manifesto_id
            LEFT JOIN volumes v ON m.id = v.manifesto_id
            WHERE ms.secao = ? AND ms.status_autorizacao = 'PENDENTE' AND ms.excluido = 0
            GROUP BY m.id
            ORDER BY m.id DESC
        """, (secao,))
        return [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()


def obter_info_manifesto_secao(manifesto_id: int, secao: str) -> dict:
    """Retorna dados de manifesto_secao para uma seção específica."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM manifesto_secao WHERE manifesto_id = ? AND secao = ?", (manifesto_id, secao))
        r = cursor.fetchone()
        return dict(r) if r else None
    finally:
        conn.close()


def obter_manifesto_por_numero(numero: str, secao: str = None) -> dict:
    """Obtém um manifesto pelo seu número (filtrando por seção ativa se informada)."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        if secao:
            sec_clean = secao.upper()
            cursor.execute("""
                SELECT m.* FROM manifestos m
                JOIN manifesto_secao ms ON m.id = ms.manifesto_id
                WHERE m.numero_manifesto = ? AND ms.secao = ? AND ms.excluido = 0
            """, (numero, sec_clean))
        else:
            cursor.execute("SELECT * FROM manifestos WHERE numero_manifesto = ?", (numero,))
        r = cursor.fetchone()
        return dict(r) if r else None
    finally:
        conn.close()


def excluir_manifesto_secao(manifesto_id: int, secao: str, usuario: str = None) -> bool:
    """
    Realiza a exclusão de um manifesto para a seção solicitada (R23, Opção A).
    Marca excluido = 1 na manifesto_secao.
    Se todas as seções tiverem excluído o manifesto, apaga completamente o registro e arquivos do banco de dados (Hard Delete).
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        agora = get_agora_br()
        sec_clean = (secao or 'TSRE').upper()
        
        # 1. Soft-delete na seção informada
        cursor.execute("""
            INSERT INTO manifesto_secao (manifesto_id, secao, status_conferencia, status_autorizacao, excluido, data_exclusao)
            VALUES (?, ?, 'PENDENTE', 'AUTORIZADO', 1, ?)
            ON CONFLICT(manifesto_id, secao) DO UPDATE SET
                excluido = 1,
                data_exclusao = excluded.data_exclusao
        """, (manifesto_id, sec_clean, agora))
        
        # Limpar conferências da seção excluída
        cursor.execute("DELETE FROM conferencia_volume WHERE volume_id IN (SELECT id FROM volumes WHERE manifesto_id = ?) AND secao = ?", (manifesto_id, sec_clean))
        cursor.execute("DELETE FROM conferencia_caixa WHERE volume_id IN (SELECT id FROM volumes WHERE manifesto_id = ?) AND secao = ?", (manifesto_id, sec_clean))
        
        registrar_log(
            cursor, manifesto_id, None, None,
            'EXCLUIR_MANIFESTO_SECAO', usuario or 'SISTEMA',
            None, {'excluido': 1, 'secao_exclusao': sec_clean},
            secao=sec_clean
        )
        
        # 2. Verificar se ainda resta alguma seção ativa
        cursor.execute("SELECT COUNT(*) as ativas FROM manifesto_secao WHERE manifesto_id = ? AND excluido = 0", (manifesto_id,))
        r_ativ = cursor.fetchone()
        qtd_ativas = r_ativ['ativas'] if r_ativ else 0
        
        if qtd_ativas == 0:
            # Apagar fisicamente todos os dados associados a este manifesto
            cursor.execute("SELECT pdf_path FROM manifestos WHERE id = ?", (manifesto_id,))
            m_pdf = cursor.fetchone()
            pdf_filepath = m_pdf['pdf_path'] if m_pdf else None

            cursor.execute("DELETE FROM conferencia_caixa WHERE volume_id IN (SELECT id FROM volumes WHERE manifesto_id = ?)", (manifesto_id,))
            cursor.execute("DELETE FROM conferencia_volume WHERE volume_id IN (SELECT id FROM volumes WHERE manifesto_id = ?)", (manifesto_id,))
            cursor.execute("DELETE FROM caixas_individuais WHERE volume_id IN (SELECT id FROM volumes WHERE manifesto_id = ?)", (manifesto_id,))
            cursor.execute("DELETE FROM volume_observacoes WHERE volume_id IN (SELECT id FROM volumes WHERE manifesto_id = ?)", (manifesto_id,))
            cursor.execute("DELETE FROM historico_edicoes_extra WHERE volume_id IN (SELECT id FROM volumes WHERE manifesto_id = ?)", (manifesto_id,))
            cursor.execute("DELETE FROM volumes WHERE manifesto_id = ?", (manifesto_id,))
            cursor.execute("DELETE FROM logs WHERE manifesto_id = ?", (manifesto_id,))
            cursor.execute("DELETE FROM manifesto_secao WHERE manifesto_id = ?", (manifesto_id,))
            cursor.execute("DELETE FROM manifestos WHERE id = ?", (manifesto_id,))
            
            # Remover arquivo ou pasta do PDF se existir e for do sistema
            if pdf_filepath and os.path.exists(pdf_filepath):
                try:
                    if os.path.isfile(pdf_filepath):
                        os.remove(pdf_filepath)
                    elif os.path.isdir(pdf_filepath):
                        import shutil
                        shutil.rmtree(pdf_filepath)
                except Exception as ef:
                    print(f"Aviso ao remover arquivo do manifesto {manifesto_id}: {ef}")
        
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"Erro ao excluir manifesto por seção: {e}")
        return False
    finally:
        conn.close()


def listar_logs(manifesto_id: int = None, secao: str = None) -> list:
    """Retorna a lista de logs de auditoria (R06), opcionalmente filtrados por manifesto_id e/ou seção."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        query = "SELECT * FROM logs WHERE 1=1"
        params = []
        if manifesto_id:
            query += " AND manifesto_id = ?"
            params.append(manifesto_id)
        if secao:
            query += " AND secao = ?"
            params.append(secao.upper())
        query += " ORDER BY id DESC"
        cursor.execute(query, params)
        return [dict(r) for r in cursor.fetchall()]
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
# RECEBIMENTO E DESFAZER (v3 — com rastreabilidade e multisseção v5)
# ═══════════════════════════════════════════════════

def marcar_recebido_web(volume_id, usuario, secao='TSRE'):
    """
    Marca TODAS as caixas pendentes de um volume como RECEBIDA para a seção informada.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        agora = get_agora_br()
        manifesto_id = _obter_manifesto_id_por_volume(cursor, volume_id)

        _garantir_conferencia_existente(cursor, volume_id, secao)
        estado_ant = _snapshot_volume(cursor, volume_id)

        cursor.execute("""
            UPDATE conferencia_caixa SET 
                status = 'RECEBIDA', 
                data_hora_recepcao = ?, 
                usuario_conferente = ?,
                retirado_por = NULL,
                retirado_por_tipo = NULL,
                motivo_nao_recebido = NULL
            WHERE volume_id = ? AND secao = ?
              AND status != 'RECEBIDA' 
              AND status != 'RETIRADO POR OUTRA PESSOA'
              AND motivo_nao_recebido IS NULL
        """, (agora, usuario, volume_id, secao))

        _recalcular_conferencia_volume_secao(cursor, volume_id, secao, agora, usuario)
        _atualizar_status_manifesto_secao(cursor, manifesto_id, secao)

        if secao == 'TSRE':
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

        estado_pos = _snapshot_volume(cursor, volume_id)
        registrar_log(
            cursor, manifesto_id, volume_id, None,
            'RECEBER_VOLUME_COMPLETO', usuario, estado_ant, estado_pos, secao=secao
        )

        conn.commit()
        if secao == 'TSRE':
            _sincronizar_sheets(cursor, volume_id)
        return True
    finally:
        conn.close()


def receber_todos_volumes_web(manifesto_id, usuario, secao='TSRE'):
    """
    Marca TODOS os volumes de um manifesto como RECEBIDO para a seção informada.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        agora = get_agora_br()

        if secao == 'TSRE':
            cursor.execute("SELECT id, destinatario FROM volumes WHERE manifesto_id=?", (manifesto_id,))
            all_vols = cursor.fetchall()
            pamals_vols = [v['id'] for v in all_vols if v['destinatario'] == 'PAMALS' or _e_destinatario_pamals(v['destinatario'])]
            if pamals_vols:
                volumes = pamals_vols
            else:
                volumes = [v['id'] for v in all_vols]
        else:
            cursor.execute("SELECT id FROM volumes WHERE manifesto_id=?", (manifesto_id,))
            volumes = [r['id'] for r in cursor.fetchall()]
        if not volumes:
            return False

        for vid in volumes:
            _garantir_conferencia_existente(cursor, vid, secao)

        placeholders = ','.join(['?'] * len(volumes))

        cursor.execute(f"""
            UPDATE conferencia_caixa SET 
                status = 'RECEBIDA', 
                data_hora_recepcao = ?, 
                usuario_conferente = ?,
                retirado_por = NULL,
                retirado_por_tipo = NULL,
                motivo_nao_recebido = NULL
            WHERE volume_id IN ({placeholders}) AND secao = ?
              AND status != 'RECEBIDA'
              AND status != 'RETIRADO POR OUTRA PESSOA'
              AND motivo_nao_recebido IS NULL
        """, (agora, usuario, *volumes, secao))

        for vid in volumes:
            _recalcular_conferencia_volume_secao(cursor, vid, secao, agora, usuario)

        _atualizar_status_manifesto_secao(cursor, manifesto_id, secao)

        if secao == 'TSRE':
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

        registrar_log(
            cursor, manifesto_id, None, None,
            'RECEBER_MANIFESTO_COMPLETO', usuario,
            {'volumes_afetados': len(volumes)},
            {'status': 'TOTALMENTE RECEBIDO'},
            secao=secao
        )

        conn.commit()

        if secao == 'TSRE':
            for vid in volumes:
                _sincronizar_sheets(cursor, vid)
        return True
    finally:
        conn.close()


def desfazer_recebimento_web(volume_id, usuario='SISTEMA', secao='TSRE'):
    """Desfaz recebimento de TODAS as caixas de um volume para a seção."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        manifesto_id = _obter_manifesto_id_por_volume(cursor, volume_id)

        _garantir_conferencia_existente(cursor, volume_id, secao)
        estado_ant = _snapshot_volume(cursor, volume_id)

        cursor.execute(
            "UPDATE conferencia_caixa SET status='NÃO RECEBIDA', data_hora_recepcao=NULL, "
            "usuario_conferente=NULL, retirado_por=NULL, retirado_por_tipo=NULL, motivo_nao_recebido=NULL "
            "WHERE volume_id=? AND secao=?",
            (volume_id, secao)
        )
        
        _recalcular_conferencia_volume_secao(cursor, volume_id, secao, None, None)
        _atualizar_status_manifesto_secao(cursor, manifesto_id, secao)

        if secao == 'TSRE':
            cursor.execute(
                "UPDATE caixas_individuais SET status='NÃO RECEBIDA', data_hora_recepcao=NULL, "
                "usuario_conferente=NULL, retirado_por=NULL, retirado_por_tipo=NULL, motivo_nao_recebido=NULL "
                "WHERE volume_id=?",
                (volume_id,)
            )
            _recalcular_volume(cursor, volume_id, None, None)
            _atualizar_status_manifesto(cursor, volume_id)

        estado_pos = _snapshot_volume(cursor, volume_id)
        registrar_log(
            cursor, manifesto_id, volume_id, None,
            'DESFAZER_VOLUME', usuario, estado_ant, estado_pos, secao=secao
        )

        conn.commit()
        if secao == 'TSRE':
            _sincronizar_sheets(cursor, volume_id)
        return True
    finally:
        conn.close()


def marcar_caixa_recebida_web(volume_id, numero_caixa, usuario, secao='TSRE'):
    """Marca UMA caixa específica como recebida para a seção."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        agora = get_agora_br()
        manifesto_id = _obter_manifesto_id_por_volume(cursor, volume_id)

        _garantir_conferencia_existente(cursor, volume_id, secao)
        estado_ant = _snapshot_caixa(cursor, volume_id, numero_caixa)

        cursor.execute("""
            UPDATE conferencia_caixa SET 
                status = 'RECEBIDA', 
                data_hora_recepcao = ?, 
                usuario_conferente = ?,
                retirado_por = NULL,
                retirado_por_tipo = NULL,
                motivo_nao_recebido = NULL
            WHERE volume_id = ? AND numero_caixa = ? AND secao = ?
        """, (agora, usuario, volume_id, numero_caixa, secao))

        _recalcular_conferencia_volume_secao(cursor, volume_id, secao, agora, usuario)
        _atualizar_status_manifesto_secao(cursor, manifesto_id, secao)

        if secao == 'TSRE':
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

        estado_pos = _snapshot_caixa(cursor, volume_id, numero_caixa)
        registrar_log(
            cursor, manifesto_id, volume_id, numero_caixa,
            'RECEBER_CAIXA', usuario, estado_ant, estado_pos, secao=secao
        )

        conn.commit()
        if secao == 'TSRE':
            _sincronizar_sheets(cursor, volume_id)
        return True
    finally:
        conn.close()


def desfazer_caixa_web(volume_id, numero_caixa, usuario='SISTEMA', secao='TSRE'):
    """Desfaz recebimento de UMA caixa específica para a seção."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        manifesto_id = _obter_manifesto_id_por_volume(cursor, volume_id)

        _garantir_conferencia_existente(cursor, volume_id, secao)
        estado_ant = _snapshot_caixa(cursor, volume_id, numero_caixa)

        cursor.execute(
            "UPDATE conferencia_caixa SET status='NÃO RECEBIDA', data_hora_recepcao=NULL, "
            "usuario_conferente=NULL, retirado_por=NULL, retirado_por_tipo=NULL, motivo_nao_recebido=NULL "
            "WHERE volume_id=? AND numero_caixa=? AND secao=?",
            (volume_id, numero_caixa, secao)
        )

        _recalcular_conferencia_volume_secao(cursor, volume_id, secao, None, None)
        _atualizar_status_manifesto_secao(cursor, manifesto_id, secao)

        if secao == 'TSRE':
            cursor.execute(
                "UPDATE caixas_individuais SET status='NÃO RECEBIDA', data_hora_recepcao=NULL, "
                "usuario_conferente=NULL, retirado_por=NULL, retirado_por_tipo=NULL, motivo_nao_recebido=NULL "
                "WHERE volume_id=? AND numero_caixa=?",
                (volume_id, numero_caixa)
            )
            _recalcular_volume(cursor, volume_id, None, None)
            _atualizar_status_manifesto(cursor, volume_id)

        estado_pos = _snapshot_caixa(cursor, volume_id, numero_caixa)
        registrar_log(
            cursor, manifesto_id, volume_id, numero_caixa,
            'DESFAZER_CAIXA', usuario, estado_ant, estado_pos, secao=secao
        )

        conn.commit()
        if secao == 'TSRE':
            _sincronizar_sheets(cursor, volume_id)
        return True
    finally:
        conn.close()


# ═══════════════════════════════════════════════════
# REQ-01: STATUS ESPECIAL (Retirado / Não Recebido com multisseção v5 e R09)
# ═══════════════════════════════════════════════════

def marcar_status_especial_caixa(volume_id, numero_caixa, novo_status,
                                  usuario_executor, retirado_por=None,
                                  motivo_nao_recebido=None, secao='TSRE'):
    """
    Marca uma caixa individual com status especial para a seção.
    - 'RETIRADO POR OUTRA PESSOA' (quem retirou deve ser informado)
    - 'NÃO RECEBIDO' (motivo_nao_recebido é obrigatório)
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        agora = get_agora_br()
        manifesto_id = _obter_manifesto_id_por_volume(cursor, volume_id)
        _garantir_conferencia_existente(cursor, volume_id, secao)
        estado_ant = _snapshot_caixa(cursor, volume_id, numero_caixa)

        if novo_status == 'RETIRADO POR OUTRA PESSOA':
            cursor.execute("""
                UPDATE conferencia_caixa SET 
                    status = ?, 
                    data_hora_recepcao = ?, 
                    usuario_conferente = ?, 
                    retirado_por = ?, 
                    retirado_por_tipo = 'EXTERNO',
                    motivo_nao_recebido = NULL
                WHERE volume_id = ? AND numero_caixa = ? AND secao = ?
            """, (novo_status, agora, usuario_executor, retirado_por, volume_id, numero_caixa, secao))
        elif novo_status == 'NÃO RECEBIDO':
            cursor.execute("""
                UPDATE conferencia_caixa SET 
                    status = 'NÃO RECEBIDA', 
                    data_hora_recepcao = ?, 
                    usuario_conferente = ?, 
                    retirado_por = NULL, 
                    retirado_por_tipo = NULL,
                    motivo_nao_recebido = ?
                WHERE volume_id = ? AND numero_caixa = ? AND secao = ?
            """, (agora, usuario_executor, motivo_nao_recebido, volume_id, numero_caixa, secao))
        else:
            cursor.execute("""
                UPDATE conferencia_caixa SET 
                    status = 'NÃO RECEBIDA', 
                    data_hora_recepcao = NULL, 
                    usuario_conferente = NULL, 
                    retirado_por = NULL, 
                    retirado_por_tipo = NULL,
                    motivo_nao_recebido = NULL
                WHERE volume_id = ? AND numero_caixa = ? AND secao = ?
            """, (volume_id, numero_caixa, secao))

        _recalcular_conferencia_volume_secao(cursor, volume_id, secao, agora, usuario_executor)
        _atualizar_status_manifesto_secao(cursor, manifesto_id, secao)

        if secao == 'TSRE':
            if novo_status == 'RETIRADO POR OUTRA PESSOA':
                cursor.execute("""
                    UPDATE caixas_individuais SET 
                        status = ?, data_hora_recepcao = ?, usuario_conferente = ?, 
                        retirado_por = ?, retirado_por_tipo = 'EXTERNO', motivo_nao_recebido = NULL
                    WHERE volume_id = ? AND numero_caixa = ?
                """, (novo_status, agora, usuario_executor, retirado_por, volume_id, numero_caixa))
            elif novo_status == 'NÃO RECEBIDO':
                cursor.execute("""
                    UPDATE caixas_individuais SET 
                        status = 'NÃO RECEBIDA', data_hora_recepcao = ?, usuario_conferente = ?, 
                        retirado_por = NULL, retirado_por_tipo = NULL, motivo_nao_recebido = ?
                    WHERE volume_id = ? AND numero_caixa = ?
                """, (agora, usuario_executor, motivo_nao_recebido, volume_id, numero_caixa))
            else:
                cursor.execute("""
                    UPDATE caixas_individuais SET 
                        status = 'NÃO RECEBIDA', data_hora_recepcao = NULL, usuario_conferente = NULL, 
                        retirado_por = NULL, retirado_por_tipo = NULL, motivo_nao_recebido = NULL
                    WHERE volume_id = ? AND numero_caixa = ?
                """, (volume_id, numero_caixa))
            _recalcular_volume(cursor, volume_id, agora, usuario_executor)
            _atualizar_status_manifesto(cursor, volume_id)

        # R09: Se CAN, gerar OBS automática para TSRE
        if secao == 'CAN':
            cursor.execute("SELECT numero_volume FROM volumes WHERE id = ?", (volume_id,))
            v_row = cursor.fetchone()
            vol_num = v_row['numero_volume'] if v_row else f"ID {volume_id}"
            if novo_status == 'RETIRADO POR OUTRA PESSOA':
                texto_obs = f"[CAN] Caixa {numero_caixa} do volume {vol_num} retirada por {retirado_por} (por {usuario_executor})"
            elif novo_status == 'NÃO RECEBIDO':
                texto_obs = f"[CAN] Caixa {numero_caixa} do volume {vol_num} não recebida: {motivo_nao_recebido} (por {usuario_executor})"
            else:
                texto_obs = None
            if texto_obs:
                criar_obs_automatica_cruzada(cursor, volume_id, 'TSRE', usuario_executor, texto_obs)

        estado_pos = _snapshot_caixa(cursor, volume_id, numero_caixa)
        registrar_log(
            cursor, manifesto_id, volume_id, numero_caixa,
            f'STATUS_ESPECIAL_{novo_status}', usuario_executor,
            estado_ant, estado_pos, secao=secao
        )

        conn.commit()
        if secao == 'TSRE':
            _sincronizar_sheets(cursor, volume_id)
        return True
    except Exception as e:
        conn.rollback()
        print(f"Erro ao marcar status especial caixa: {e}")
        return False
    finally:
        conn.close()


def marcar_status_especial_volume(volume_id, novo_status, usuario_executor,
                                   retirado_por=None, motivo_nao_recebido=None, secao='TSRE'):
    """Marca TODAS as caixas de um volume com status especial para a seção."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        agora = get_agora_br()
        manifesto_id = _obter_manifesto_id_por_volume(cursor, volume_id)
        _garantir_conferencia_existente(cursor, volume_id, secao)
        estado_ant = _snapshot_volume(cursor, volume_id)

        if novo_status == 'RETIRADO POR OUTRA PESSOA':
            cursor.execute("""
                UPDATE conferencia_caixa SET 
                    status = ?, 
                    data_hora_recepcao = ?, 
                    usuario_conferente = ?, 
                    retirado_por = ?, 
                    retirado_por_tipo = 'EXTERNO',
                    motivo_nao_recebido = NULL
                WHERE volume_id = ? AND secao = ?
            """, (novo_status, agora, usuario_executor, retirado_por, volume_id, secao))
            cursor.execute("""
                UPDATE conferencia_volume SET 
                    status = ?, 
                    quantidade_recebida = 0, 
                    data_hora_ultima_recepcao = ?, 
                    usuario_recepcao = ?, 
                    retirado_por = ?, 
                    motivo_nao_recebido = NULL 
                WHERE volume_id = ? AND secao = ?
            """, (novo_status, agora, usuario_executor, retirado_por, volume_id, secao))
        elif novo_status == 'NÃO RECEBIDO':
            cursor.execute("""
                UPDATE conferencia_caixa SET 
                    status = 'NÃO RECEBIDA', 
                    data_hora_recepcao = ?, 
                    usuario_conferente = ?, 
                    retirado_por = NULL, 
                    retirado_por_tipo = NULL,
                    motivo_nao_recebido = ?
                WHERE volume_id = ? AND secao = ?
            """, (agora, usuario_executor, motivo_nao_recebido, volume_id, secao))
            cursor.execute("""
                UPDATE conferencia_volume SET 
                    status = 'NÃO RECEBIDO', 
                    quantidade_recebida = 0, 
                    data_hora_ultima_recepcao = ?, 
                    usuario_recepcao = ?, 
                    retirado_por = NULL, 
                    motivo_nao_recebido = ? 
                WHERE volume_id = ? AND secao = ?
            """, (agora, usuario_executor, motivo_nao_recebido, volume_id, secao))
        else:
            cursor.execute("""
                UPDATE conferencia_caixa SET 
                    status = 'NÃO RECEBIDA', 
                    data_hora_recepcao = NULL, 
                    usuario_conferente = NULL, 
                    retirado_por = NULL, 
                    retirado_por_tipo = NULL,
                    motivo_nao_recebido = NULL 
                WHERE volume_id = ? AND secao = ?
            """, (volume_id, secao))
            cursor.execute("""
                UPDATE conferencia_volume SET 
                    status = 'NÃO RECEBIDO', 
                    quantidade_recebida = 0, 
                    data_hora_ultima_recepcao = NULL, 
                    usuario_recepcao = NULL, 
                    retirado_por = NULL, 
                    motivo_nao_recebido = NULL 
                WHERE volume_id = ? AND secao = ?
            """, (volume_id, secao))

        _atualizar_status_manifesto_secao(cursor, manifesto_id, secao)

        if secao == 'TSRE':
            if novo_status == 'RETIRADO POR OUTRA PESSOA':
                cursor.execute("""
                    UPDATE caixas_individuais SET 
                        status = ?, data_hora_recepcao = ?, usuario_conferente = ?, 
                        retirado_por = ?, retirado_por_tipo = 'EXTERNO', motivo_nao_recebido = NULL
                    WHERE volume_id = ?
                """, (novo_status, agora, usuario_executor, retirado_por, volume_id))
                cursor.execute("""
                    UPDATE volumes SET 
                        status = ?, quantidade_recebida = 0, data_hora_ultima_recepcao = ?, 
                        usuario_recepcao = ?, retirado_por = ?, motivo_nao_recebido = NULL 
                    WHERE id = ?
                """, (novo_status, agora, usuario_executor, retirado_por, volume_id))
            elif novo_status == 'NÃO RECEBIDO':
                cursor.execute("""
                    UPDATE caixas_individuais SET 
                        status = 'NÃO RECEBIDA', data_hora_recepcao = ?, usuario_conferente = ?, 
                        retirado_por = NULL, retirado_por_tipo = NULL, motivo_nao_recebido = ?
                    WHERE volume_id = ?
                """, (agora, usuario_executor, motivo_nao_recebido, volume_id))
                cursor.execute("""
                    UPDATE volumes SET 
                        status = 'NÃO RECEBIDO', quantidade_recebida = 0, data_hora_ultima_recepcao = ?, 
                        usuario_recepcao = ?, retirado_por = NULL, motivo_nao_recebido = ? 
                    WHERE id = ?
                """, (agora, usuario_executor, motivo_nao_recebido, volume_id))
            else:
                cursor.execute("""
                    UPDATE caixas_individuais SET 
                        status = 'NÃO RECEBIDA', data_hora_recepcao = NULL, usuario_conferente = NULL, 
                        retirado_por = NULL, retirado_por_tipo = NULL, motivo_nao_recebido = NULL 
                    WHERE volume_id = ?
                """, (volume_id,))
                cursor.execute("""
                    UPDATE volumes SET 
                        status = 'NÃO RECEBIDO', quantidade_recebida = 0, data_hora_ultima_recepcao = NULL, 
                        usuario_recepcao = NULL, retirado_por = NULL, motivo_nao_recebido = NULL 
                    WHERE id = ?
                """, (volume_id,))
            _atualizar_status_manifesto(cursor, volume_id)

        # R09: Se CAN, gerar OBS automática para TSRE
        if secao == 'CAN':
            cursor.execute("SELECT numero_volume FROM volumes WHERE id = ?", (volume_id,))
            v_row = cursor.fetchone()
            vol_num = v_row['numero_volume'] if v_row else f"ID {volume_id}"
            if novo_status == 'RETIRADO POR OUTRA PESSOA':
                texto_obs = f"[CAN] Volume {vol_num} retirado por {retirado_por} (por {usuario_executor})"
            elif novo_status == 'NÃO RECEBIDO':
                texto_obs = f"[CAN] Volume {vol_num} não recebido: {motivo_nao_recebido} (por {usuario_executor})"
            else:
                texto_obs = None
            if texto_obs:
                criar_obs_automatica_cruzada(cursor, volume_id, 'TSRE', usuario_executor, texto_obs)

        estado_pos = _snapshot_volume(cursor, volume_id)
        registrar_log(
            cursor, manifesto_id, volume_id, None,
            f'STATUS_ESPECIAL_VOLUME_{novo_status}', usuario_executor,
            estado_ant, estado_pos, secao=secao
        )

        conn.commit()
        if secao == 'TSRE':
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
        novo_status = 'PENDENTE'
        cursor.execute(
            "UPDATE volumes SET quantidade_recebida=0, status=?, "
            "data_hora_ultima_recepcao=NULL, usuario_recepcao=NULL, "
            "retirado_por=NULL, motivo_nao_recebido=NULL WHERE id=?",
            (novo_status, volume_id)
        )
    else:
        # Determinar status com base no mix de estados
        if recebidas == expedidas:
            novo_status = 'COMPLETO'
        elif retiradas == expedidas:
            novo_status = 'RETIRADO POR OUTRA PESSOA'
        elif nao_recebidas == expedidas:
            novo_status = 'NÃO RECEBIDO'
        else:
            novo_status = 'PARCIAL'

        # Obter retirador e motivo agregados de todas as caixas do volume
        retirado_list = [c['retirado_por'] for c in caixas if c.get('retirado_por')]
        v_retirado_por = ", ".join(dict.fromkeys(retirado_list)) if retirado_list else None

        motivo_list = [c['motivo_nao_recebido'] for c in caixas if c.get('motivo_nao_recebido')]
        v_motivo = ", ".join(dict.fromkeys(motivo_list)) if motivo_list else None

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
        novo_st = 'PENDENTE'
    elif resolvidas >= total:
        novo_st = 'TOTALMENTE RECEBIDO'
    else:
        novo_st = 'PARCIALMENTE RECEBIDO'

    cursor.execute("UPDATE manifestos SET status=? WHERE id=?", (novo_st, mid))
    return mid


def _sincronizar_sheets(cursor, volume_id, secao='TSRE'):
    """Sincroniza dados do volume com Google Sheets (desabilitado para a seção CAN - R15)."""
    if secao == 'CAN':
        return
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
            # Obter seções ativas para atualizar conferencia_caixa
            cursor.execute("""
                SELECT DISTINCT secao FROM conferencia_caixa WHERE volume_id = ?
            """, (volume_id,))
            secoes_existentes = [r['secao'] for r in cursor.fetchall()]
            if not secoes_existentes:
                cursor.execute("""
                    SELECT secao FROM manifesto_secao 
                    WHERE manifesto_id = (SELECT manifesto_id FROM volumes WHERE id = ?) AND excluido = 0
                """, (volume_id,))
                secoes_existentes = [r['secao'] for r in cursor.fetchall()] or ['TSRE']

            if quantidade > qtd_anterior:
                # Adicionar caixas
                for i in range(qtd_anterior + 1, quantidade + 1):
                    cursor.execute("""
                        INSERT INTO caixas_individuais (volume_id, numero_caixa, status)
                        VALUES (?, ?, 'NÃO RECEBIDA')
                    """, (volume_id, i))
                    for sec in secoes_existentes:
                        cursor.execute("""
                            INSERT OR IGNORE INTO conferencia_caixa (volume_id, numero_caixa, secao, status)
                            VALUES (?, ?, ?, 'NÃO RECEBIDA')
                        """, (volume_id, i, sec))
            else:
                # Remover caixas excedentes (priorizar não recebidas)
                cursor.execute("""
                    DELETE FROM caixas_individuais
                    WHERE volume_id = ? AND numero_caixa > ?
                    AND status = 'NÃO RECEBIDA'
                """, (volume_id, quantidade))
                cursor.execute("""
                    DELETE FROM caixas_individuais 
                    WHERE volume_id = ? AND numero_caixa > ?
                """, (volume_id, quantidade))

                for sec in secoes_existentes:
                    cursor.execute("""
                        DELETE FROM conferencia_caixa
                        WHERE volume_id = ? AND numero_caixa > ? AND secao = ?
                        AND status = 'NÃO RECEBIDA'
                    """, (volume_id, quantidade, sec))
                    cursor.execute("""
                        DELETE FROM conferencia_caixa
                        WHERE volume_id = ? AND numero_caixa > ? AND secao = ?
                    """, (volume_id, quantidade, sec))
            
            # Recalcular status do volume legado e multisseção
            _recalcular_volume(cursor, volume_id, None, None)
            cursor.execute("SELECT manifesto_id FROM volumes WHERE id = ?", (volume_id,))
            mid_row = cursor.fetchone()
            mid_val = mid_row['manifesto_id'] if mid_row else None

            for sec in secoes_existentes:
                _recalcular_conferencia_volume_secao(cursor, volume_id, sec, None, None)
                if mid_val:
                    _atualizar_status_manifesto_secao(cursor, mid_val, sec)
            if mid_val:
                _atualizar_status_manifesto(cursor, volume_id)
        
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