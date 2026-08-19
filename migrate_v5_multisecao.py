"""
Migração Versão 5.0 - Expansão Multisseção (TSRE / CAN)
Executa: python migrate_v5_multisecao.py

Objetivo:
- Adicionar colunas de multisseção (secao, secao_origem, secao_extra, auto_gerada).
- Criar novas tabelas para isolamento por seção (manifesto_secao, conferencia_volume, conferencia_caixa).
- Migrar roles legadas ('admin' -> 'admin_tsre', 'operador' -> 'operador_tsre').
- Atribuir dados legados para a seção TSRE.
- Totalmente idempotente (seguro para rodar múltiplas vezes).
"""
import sqlite3
import shutil
import sys
import os
from pathlib import Path
from datetime import datetime

# Assegura utf-8 no stdout do terminal Windows se possível
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

DB_PATH = Path(__file__).parent / "data" / "database.db"


def _coluna_existe(cursor, tabela, coluna):
    """Verifica se uma coluna já existe na tabela."""
    colunas = [r[1] for r in cursor.execute(f"PRAGMA table_info({tabela})")]
    return coluna in colunas


def _tabela_existe(cursor, tabela):
    """Verifica se uma tabela já existe no banco."""
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (tabela,)
    )
    return cursor.fetchone() is not None


def diagnosticar(cursor):
    """Imprime diagnóstico completo do estado atual do banco."""
    print("\n==========================================")
    print("       DIAGNOSTICO DO BANCO DE DADOS      ")
    print("==========================================\n")

    tabelas_esperadas = [
        'users', 'manifestos', 'manifesto_secao', 'volumes',
        'conferencia_volume', 'caixas_individuais', 'conferencia_caixa',
        'logs', 'historico_edicoes_extra', 'volume_observacoes'
    ]

    for tabela in tabelas_esperadas:
        existe = _tabela_existe(cursor, tabela)
        status = "[OK] EXISTE" if existe else "[ERRO] NAO EXISTE"
        print(f"  Tabela [{tabela}]: {status}")
        if existe:
            colunas = [r[1] for r in cursor.execute(f"PRAGMA table_info({tabela})")]
            print(f"    Colunas: {', '.join(colunas)}")
            cursor.execute(f"SELECT COUNT(*) FROM {tabela}")
            total = cursor.fetchone()[0]
            print(f"    Registros: {total}")
    print()


def migrar():
    if not DB_PATH.exists():
        print("[ERRO] Banco de dados nao encontrado em:", DB_PATH.resolve())
        return False

    print(f"[INFO] Banco: {DB_PATH.resolve()}")
    print(f"[INFO] Tamanho: {DB_PATH.stat().st_size / 1024:.1f} KB\n")

    # 1. Backup automático com timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = DB_PATH.parent / f"database_backup_v5_{timestamp}.db"
    shutil.copy2(DB_PATH, backup)
    print(f"[OK] Backup v5 criado: {backup}\n")

    conn = sqlite3.connect(str(DB_PATH), timeout=30.0)
    # 2. PRAGMA journal_mode=WAL
    conn.execute("PRAGMA journal_mode=WAL")
    cursor = conn.cursor()

    print("=== ESTADO ANTES DA MIGRACAO V5 ===")
    diagnosticar(cursor)

    alteracoes = 0

    try:
        conn.execute("BEGIN TRANSACTION")

        # ─── 3. ADICIONAR NOVAS COLUNAS ───────────────────────
        print("=== 1. ADICIONANDO NOVAS COLUNAS (IF NOT EXISTS) ===\n")

        novas_colunas = [
            ("users",              "secao",        "TEXT DEFAULT 'TSRE'"),
            ("manifestos",         "secao_origem", "TEXT DEFAULT 'TSRE'"),
            ("volumes",            "secao_extra",  "TEXT"),
            ("logs",               "secao",        "TEXT DEFAULT 'TSRE'"),
            ("volume_observacoes", "secao",        "TEXT DEFAULT 'TSRE'"),
            ("volume_observacoes", "auto_gerada",  "INTEGER DEFAULT 0"),
        ]

        for tabela, coluna, definicao in novas_colunas:
            if not _tabela_existe(cursor, tabela):
                print(f"  [AVISO] Tabela [{tabela}] nao existe, pulando coluna [{coluna}]")
                continue

            if _coluna_existe(cursor, tabela, coluna):
                print(f"  [OK] [{tabela}.{coluna}] ja existe")
            else:
                try:
                    cursor.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {definicao}")
                    alteracoes += 1
                    print(f"  [NOVO] [{tabela}.{coluna}] ADICIONADA ({definicao})")
                except sqlite3.OperationalError as e:
                    print(f"  [AVISO] ao adicionar [{tabela}.{coluna}]: {e}")

        print()

        # ─── 4. CRIAR NOVAS TABELAS ───────────────────────────
        print("=== 2. CRIANDO NOVAS TABELAS (CREATE TABLE IF NOT EXISTS) ===\n")

        # manifesto_secao
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS manifesto_secao (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                manifesto_id INTEGER NOT NULL,
                secao TEXT NOT NULL,
                status_conferencia TEXT DEFAULT 'NÃO RECEBIDO',
                status_autorizacao TEXT DEFAULT 'PENDENTE',
                autorizado_por TEXT,
                data_autorizacao DATETIME,
                excluido INTEGER DEFAULT 0,
                data_exclusao DATETIME,
                FOREIGN KEY (manifesto_id) REFERENCES manifestos(id),
                UNIQUE(manifesto_id, secao)
            )
        """)

        # conferencia_volume
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conferencia_volume (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                volume_id INTEGER NOT NULL,
                secao TEXT NOT NULL,
                status TEXT DEFAULT 'NÃO RECEBIDO',
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

        # conferencia_caixa
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

        print("  Novas tabelas: OK\n")

        # ─── 5. MIGRAR ROLES E DADOS EXISTENTES PARA TSRE ──────
        print("=== 3. MIGRANDO ROLES E ATRIBUINDO SECAO TSRE ===\n")

        # 5a. Migrar roles em users
        cursor.execute("UPDATE users SET role = 'admin_tsre' WHERE role = 'admin'")
        migrated_admin = cursor.rowcount
        cursor.execute("UPDATE users SET role = 'operador_tsre' WHERE role = 'operador'")
        migrated_op = cursor.rowcount

        if migrated_admin > 0 or migrated_op > 0:
            print(f"  [MIGRADO] Roles atualizados: {migrated_admin} admins -> admin_tsre, {migrated_op} operadores -> operador_tsre")
            alteracoes += (migrated_admin + migrated_op)

        # 5b. Garantir secao='TSRE' para usuários existentes
        cursor.execute("UPDATE users SET secao = 'TSRE' WHERE secao IS NULL OR secao = ''")
        usr_sec = cursor.rowcount
        if usr_sec > 0:
            print(f"  [MIGRADO] {usr_sec} usuarios atualizados com secao='TSRE'")
            alteracoes += usr_sec

        # 5c. Garantir secao_origem='TSRE' para manifestos existentes
        cursor.execute("UPDATE manifestos SET secao_origem = 'TSRE' WHERE secao_origem IS NULL OR secao_origem = ''")
        man_sec = cursor.rowcount
        if man_sec > 0:
            print(f"  [MIGRADO] {man_sec} manifestos atualizados com secao_origem='TSRE'")
            alteracoes += man_sec

        # 5d. Popular manifesto_secao para manifestos existentes
        cursor.execute("""
            INSERT INTO manifesto_secao (manifesto_id, secao, status_conferencia, status_autorizacao, autorizado_por, data_autorizacao)
            SELECT id, 'TSRE', status, 'AUTORIZADO', usuario_responsavel, data_registro
            FROM manifestos m
            WHERE NOT EXISTS (
                SELECT 1 FROM manifesto_secao ms WHERE ms.manifesto_id = m.id AND ms.secao = 'TSRE'
            )
        """)
        ms_count = cursor.rowcount
        if ms_count > 0:
            print(f"  [MIGRADO] {ms_count} registros criados em manifesto_secao para a TSRE")
            alteracoes += ms_count

        # 5e. Popular conferencia_volume para volumes existentes
        cursor.execute("""
            INSERT INTO conferencia_volume (volume_id, secao, status, quantidade_recebida, data_hora_primeira_recepcao, data_hora_ultima_recepcao, usuario_recepcao, retirado_por, motivo_nao_recebido)
            SELECT id, 'TSRE', status, quantidade_recebida, data_hora_primeira_recepcao, data_hora_ultima_recepcao, usuario_recepcao, retirado_por, motivo_nao_recebido
            FROM volumes v
            WHERE NOT EXISTS (
                SELECT 1 FROM conferencia_volume cv WHERE cv.volume_id = v.id AND cv.secao = 'TSRE'
            )
        """)
        cv_count = cursor.rowcount
        if cv_count > 0:
            print(f"  [MIGRADO] {cv_count} registros criados em conferencia_volume para a TSRE")
            alteracoes += cv_count

        # 5f. Popular conferencia_caixa para caixas_individuais existentes
        cursor.execute("""
            INSERT INTO conferencia_caixa (volume_id, numero_caixa, secao, status, data_hora_recepcao, usuario_conferente, retirado_por, retirado_por_tipo, motivo_nao_recebido)
            SELECT volume_id, numero_caixa, 'TSRE', status, data_hora_recepcao, usuario_conferente, retirado_por, retirado_por_tipo, motivo_nao_recebido
            FROM caixas_individuais ci
            WHERE NOT EXISTS (
                SELECT 1 FROM conferencia_caixa cc WHERE cc.volume_id = ci.volume_id AND cc.numero_caixa = ci.numero_caixa AND cc.secao = 'TSRE'
            )
        """)
        cc_count = cursor.rowcount
        if cc_count > 0:
            print(f"  [MIGRADO] {cc_count} registros criados em conferencia_caixa para a TSRE")
            alteracoes += cc_count

        # 5g. Atualizar logs e volume_observacoes
        cursor.execute("UPDATE logs SET secao = 'TSRE' WHERE secao IS NULL OR secao = ''")
        logs_count = cursor.rowcount
        if logs_count > 0:
            print(f"  [MIGRADO] {logs_count} logs atualizados com secao='TSRE'")
            alteracoes += logs_count

        cursor.execute("UPDATE volume_observacoes SET secao = 'TSRE' WHERE secao IS NULL OR secao = ''")
        obs_sec = cursor.rowcount
        if obs_sec > 0:
            print(f"  [MIGRADO] {obs_sec} observacoes atualizadas com secao='TSRE'")
            alteracoes += obs_sec

        cursor.execute("UPDATE volume_observacoes SET auto_gerada = 0 WHERE auto_gerada IS NULL")
        obs_auto = cursor.rowcount
        if obs_auto > 0:
            print(f"  [MIGRADO] {obs_auto} observacoes atualizadas com auto_gerada=0")
            alteracoes += obs_auto

        if alteracoes == 0:
            print("\n  [OK] Nenhuma alteracao necessaria - banco v5 ja atualizado!")

        conn.commit()

        print("\n=== ESTADO APOS A MIGRACAO V5 ===")
        diagnosticar(cursor)

        print("==========================================")
        print(f"  MIGRACAO V5 CONCLUIDA: {alteracoes} alteracoes")
        print("==========================================")
        return True

    except Exception as e:
        conn.rollback()
        print(f"\n[ERRO] Migracao v5 falhou (rollback executado): {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    print("==========================================")
    print("   MIGRACAO V5 CONCAN (EXPANSAO CAN)")
    print("==========================================\n")
    migrar()
