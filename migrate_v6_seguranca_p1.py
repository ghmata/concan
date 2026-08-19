"""
Migração Consolidada de Produção - ConCAN (Multisseção v5 + Segurança P1)
Executa: python migrate_v6_seguranca_p1.py

Objetivo:
- Migrar com segurança bancos de dados legados (v3/v4) ou intermediários (v5) para a versão atual.
- 100% seguro: Executa backup automático prévio com timestamp e transações atômicas protegidas.
- Preserva integralmente todos os dados existentes (manifestos, volumes, caixas, logs, comentários).
- Cria automaticamente todas as novas colunas e tabelas multisseção (manifesto_secao, conferencia_volume, conferencia_caixa).
- Migra os papéis de usuários ('admin' -> 'admin_tsre', 'operador' -> 'operador_tsre') e atribui à TSRE.
- Popula o histórico de conferências existente para a seção TSRE.
- Idempotente: pode ser executado múltiplas vezes com total segurança.
"""
import sqlite3
import shutil
import sys
import os
from pathlib import Path
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

# Assegura utf-8 no stdout do terminal
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

DB_PATH = Path(__file__).parent / "data" / "database.db"


def _coluna_existe(cursor, tabela, coluna):
    """Verifica se uma coluna já existe na tabela."""
    colunas = [r[1] for r in cursor.execute(f"PRAGMA table_info('{tabela}')")]
    return coluna in colunas


def _tabela_existe(cursor, tabela):
    """Verifica se uma tabela já existe no banco."""
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (tabela,)
    )
    return cursor.fetchone() is not None


def migrar():
    if not DB_PATH.exists():
        print(f"[ERRO] Banco de dados não encontrado em: {DB_PATH.resolve()}")
        return False

    print("==========================================================")
    print("   MIGRAÇÃO CONSOLIDADA CONCAN (PRODUÇÃO / MULTISSEÇÃO)   ")
    print("==========================================================\n")
    print(f"[INFO] Banco: {DB_PATH.resolve()}")
    print(f"[INFO] Tamanho atual: {DB_PATH.stat().st_size / 1024:.1f} KB\n")

    # 1. Backup automático com timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = DB_PATH.parent / f"database_backup_{timestamp}.db"
    shutil.copy2(DB_PATH, backup)
    print(f"[OK] Backup de segurança criado em: {backup.name}\n")

    conn = sqlite3.connect(str(DB_PATH), timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    alteracoes = 0

    try:
        conn.execute("BEGIN TRANSACTION")

        # ─── ETAPA 1: CRIAÇÃO DE COLUNAS NOVAS (SE NÃO EXISTIREM) ───
        print("=== ETAPA 1: ATUALIZAÇÃO DO ESQUEMA DE COLUNAS ===")
        novas_colunas = [
            ("users",              "secao",        "TEXT DEFAULT 'TSRE'"),
            ("manifestos",         "secao_origem", "TEXT DEFAULT 'TSRE'"),
            ("volumes",            "secao_extra",  "TEXT"),
            ("volumes",            "destino_extra","TEXT"),
            ("logs",               "secao",        "TEXT DEFAULT 'TSRE'"),
            ("volume_observacoes", "secao",        "TEXT DEFAULT 'TSRE'"),
            ("volume_observacoes", "auto_gerada",  "INTEGER DEFAULT 0"),
        ]

        for tabela, coluna, definicao in novas_colunas:
            if not _tabela_existe(cursor, tabela):
                continue
            if not _coluna_existe(cursor, tabela, coluna):
                cursor.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {definicao}")
                print(f"  [NOVA COLUNA] {tabela}.{coluna} adicionada.")
                alteracoes += 1
            else:
                print(f"  [OK] {tabela}.{coluna} já presente.")
        print()

        # ─── ETAPA 2: CRIAÇÃO DE TABELAS MULTISSEÇÃO ──────────────
        print("=== ETAPA 2: CRIAÇÃO DE TABELAS MULTISSEÇÃO ===")
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
        print("  [OK] Tabelas multisseção verificadas com sucesso.\n")

        # ─── ETAPA 3: MIGRAÇÃO DE USUÁRIOS E PERMISSÕES ───────────
        print("=== ETAPA 3: MIGRAÇÃO DE USUÁRIOS ===")
        cursor.execute("UPDATE users SET role = 'admin_tsre' WHERE role = 'admin'")
        if cursor.rowcount > 0:
            print(f"  [MIGRADO] {cursor.rowcount} administrador(es) convertidos para 'admin_tsre'.")
            alteracoes += cursor.rowcount

        cursor.execute("UPDATE users SET role = 'operador_tsre' WHERE role = 'operador'")
        if cursor.rowcount > 0:
            print(f"  [MIGRADO] {cursor.rowcount} operador(es) convertidos para 'operador_tsre'.")
            alteracoes += cursor.rowcount

        cursor.execute("UPDATE users SET secao = 'TSRE' WHERE secao IS NULL OR secao = ''")
        if cursor.rowcount > 0:
            print(f"  [MIGRADO] {cursor.rowcount} usuário(s) associados à seção 'TSRE'.")
            alteracoes += cursor.rowcount

        cursor.execute("UPDATE manifestos SET secao_origem = 'TSRE' WHERE secao_origem IS NULL OR secao_origem = ''")
        cursor.execute("UPDATE logs SET secao = 'TSRE' WHERE secao IS NULL OR secao = ''")
        cursor.execute("UPDATE volume_observacoes SET secao = 'TSRE' WHERE secao IS NULL OR secao = ''")
        cursor.execute("UPDATE volume_observacoes SET auto_gerada = 0 WHERE auto_gerada IS NULL")
        print()

        # ─── ETAPA 4: POPULAR TABELAS MULTISSEÇÃO (DADOS TSRE) ───
        print("=== ETAPA 4: MIGRAÇÃO DOS DADOS HISTÓRICOS PARA TSRE ===")

        # 4a. manifesto_secao
        cursor.execute("""
            INSERT INTO manifesto_secao (manifesto_id, secao, status_conferencia, status_autorizacao, autorizado_por, data_autorizacao)
            SELECT id, 'TSRE', status, 'AUTORIZADO', usuario_responsavel, data_registro
            FROM manifestos m
            WHERE NOT EXISTS (
                SELECT 1 FROM manifesto_secao ms WHERE ms.manifesto_id = m.id AND ms.secao = 'TSRE'
            )
        """)
        ms_migrados = cursor.rowcount
        if ms_migrados > 0:
            print(f"  [MIGRADO] {ms_migrados} manifesto(s) vinculados à seção TSRE.")
            alteracoes += ms_migrados

        # 4b. conferencia_volume
        cursor.execute("""
            INSERT INTO conferencia_volume (volume_id, secao, status, quantidade_recebida, data_hora_primeira_recepcao, data_hora_ultima_recepcao, usuario_recepcao, retirado_por, motivo_nao_recebido)
            SELECT id, 'TSRE', status, quantidade_recebida, data_hora_primeira_recepcao, data_hora_ultima_recepcao, usuario_recepcao, retirado_por, motivo_nao_recebido
            FROM volumes v
            WHERE NOT EXISTS (
                SELECT 1 FROM conferencia_volume cv WHERE cv.volume_id = v.id AND cv.secao = 'TSRE'
            )
        """)
        cv_migrados = cursor.rowcount
        if cv_migrados > 0:
            print(f"  [MIGRADO] {cv_migrados} volume(s) vinculados à conferência da TSRE.")
            alteracoes += cv_migrados

        # 4c. conferencia_caixa
        cursor.execute("""
            INSERT INTO conferencia_caixa (volume_id, numero_caixa, secao, status, data_hora_recepcao, usuario_conferente, retirado_por, retirado_por_tipo, motivo_nao_recebido)
            SELECT volume_id, numero_caixa, 'TSRE', status, data_hora_recepcao, usuario_conferente, retirado_por, retirado_por_tipo, motivo_nao_recebido
            FROM caixas_individuais ci
            WHERE NOT EXISTS (
                SELECT 1 FROM conferencia_caixa cc WHERE cc.volume_id = ci.volume_id AND cc.numero_caixa = ci.numero_caixa AND cc.secao = 'TSRE'
            )
        """)
        cc_migrados = cursor.rowcount
        if cc_migrados > 0:
            print(f"  [MIGRADO] {cc_migrados} caixa(s) vinculadas à conferência da TSRE.")
            alteracoes += cc_migrados
        print()

        # ─── ETAPA 5: DIAGNÓSTICO DE ADMINISTRADORES ─────────────
        print("=== ETAPA 5: AUDITORIA DE ADMINISTRADORES ===")
        cursor.execute("""
            SELECT username, nome_completo, role, secao FROM users 
            WHERE role IN ('super_admin', 'admin_tsre', 'admin_can', 'admin')
            ORDER BY role, username
        """)
        admins = cursor.fetchall()
        if not admins:
            print("  [ALERTA] Nenhum administrador encontrado. Criando 'admin' padrão...")
            senha_hash = generate_password_hash("admin123")
            cursor.execute("""
                INSERT INTO users (username, password_hash, nome_completo, role, secao)
                VALUES ('admin', ?, 'Administrador Geral', 'super_admin', 'TSRE')
            """, (senha_hash,))
            alteracoes += 1
            print("  [CRIADO] Usuário 'admin' criado com sucesso. Altere a senha pelo painel.")
        else:
            for a in admins:
                print(f"  - [{a['role']}] {a['nome_completo']} (@{a['username']}) | Seção: {a['secao']}")
        print()

        conn.commit()

        # Resumo final
        print("==========================================================")
        print(f"   MIGRAÇÃO CONCLUÍDA COM SUCESSO! ({alteracoes} alterações)   ")
        print("==========================================================")
        print("  Status atual do banco:")
        cursor.execute("SELECT COUNT(*) FROM manifestos")
        print(f"  - Manifestos cadastrados: {cursor.fetchone()[0]}")
        cursor.execute("SELECT COUNT(*) FROM volumes")
        print(f"  - Volumes cadastrados:    {cursor.fetchone()[0]}")
        cursor.execute("SELECT COUNT(*) FROM caixas_individuais")
        print(f"  - Caixas individuais:    {cursor.fetchone()[0]}")
        cursor.execute("SELECT COUNT(*) FROM users")
        print(f"  - Usuários ativos:        {cursor.fetchone()[0]}")
        print("==========================================================\n")
        return True

    except Exception as e:
        conn.rollback()
        print(f"\n[ERRO FATAL] A migração falhou. Rollback executado: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        conn.close()


if __name__ == "__main__":
    migrar()
