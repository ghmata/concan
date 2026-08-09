"""
Migração COMPLETA e Unificada do ConCAN
Executa: python migrate_full.py

Cobre TODAS as colunas e tabelas de TODAS as versões (v1 → v4).
Seguro para rodar múltiplas vezes (idempotente).
NÃO apaga dados existentes.
"""
import sqlite3
import shutil
from pathlib import Path
from datetime import datetime

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
    print("\n╔══════════════════════════════════════════╗")
    print("║       DIAGNÓSTICO DO BANCO DE DADOS      ║")
    print("╚══════════════════════════════════════════╝\n")

    tabelas_esperadas = [
        'users', 'manifestos', 'volumes', 'caixas_individuais',
        'logs', 'historico_edicoes_extra', 'volume_observacoes'
    ]

    for tabela in tabelas_esperadas:
        existe = _tabela_existe(cursor, tabela)
        status = "✅ EXISTE" if existe else "❌ NÃO EXISTE"
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
        print("[ERRO] Banco de dados não encontrado em:", DB_PATH.resolve())
        return False

    print(f"[INFO] Banco: {DB_PATH.resolve()}")
    print(f"[INFO] Tamanho: {DB_PATH.stat().st_size / 1024:.1f} KB\n")

    # Backup com timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = DB_PATH.parent / f"database_backup_{timestamp}.db"
    shutil.copy2(DB_PATH, backup)
    print(f"[OK] Backup criado: {backup}\n")

    conn = sqlite3.connect(str(DB_PATH), timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL")
    cursor = conn.cursor()

    # Diagnóstico ANTES
    print("═══ ESTADO ANTES DA MIGRAÇÃO ═══")
    diagnosticar(cursor)

    alteracoes = 0

    try:
        conn.execute("BEGIN TRANSACTION")

        # ─── 1. TABELAS ───────────────────────────────────────

        print("═══ VERIFICANDO TABELAS ═══\n")

        # Users
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                nome_completo TEXT NOT NULL,
                role TEXT DEFAULT 'operador'
            )
        """)

        # Manifestos
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS manifestos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                numero_manifesto TEXT UNIQUE NOT NULL,
                data_manifesto DATE,
                terminal_origem TEXT,
                terminal_destino TEXT,
                missao TEXT,
                aeronave TEXT,
                pdf_path TEXT,
                status TEXT DEFAULT 'NÃO RECEBIDO',
                data_registro DATETIME DEFAULT CURRENT_TIMESTAMP,
                data_conferencia_inicio DATETIME,
                data_conferencia_fim DATETIME,
                usuario_responsavel TEXT
            )
        """)

        # Volumes
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
                observacao TEXT,
                retirado_por TEXT,
                motivo_nao_recebido TEXT,
                FOREIGN KEY (manifesto_id) REFERENCES manifestos(id),
                UNIQUE(manifesto_id, numero_volume)
            )
        """)

        # Caixas Individuais
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

        # Logs
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

        # Histórico de Edições Extra
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

        # Volume Observações
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

        print("  Tabelas: OK\n")

        # ─── 2. COLUNAS FALTANTES ─────────────────────────────

        print("═══ VERIFICANDO COLUNAS ═══\n")

        # Lista COMPLETA de todas as colunas que podem faltar em bancos antigos
        colunas_necessarias = [
            # (tabela, coluna, tipo_sql)
            ("manifestos",          "origem",               "TEXT DEFAULT 'PDF_DIGITAL'"),
            ("volumes",             "observacao",           "TEXT"),
            ("volumes",             "retirado_por",         "TEXT"),
            ("volumes",             "motivo_nao_recebido",  "TEXT"),
            ("caixas_individuais",  "retirado_por",         "TEXT"),
            ("caixas_individuais",  "retirado_por_tipo",    "TEXT"),
            ("caixas_individuais",  "motivo_nao_recebido",  "TEXT"),
            ("logs",                "volume_id",            "INTEGER"),
            ("logs",                "caixa_numero",         "INTEGER"),
            ("logs",                "estado_anterior",      "TEXT"),
            ("logs",                "estado_posterior",      "TEXT"),
            ("logs",                "timestamp_utc",        "DATETIME"),
            ("logs",                "timestamp_brt",        "DATETIME"),
        ]

        for tabela, coluna, tipo_sql in colunas_necessarias:
            if not _tabela_existe(cursor, tabela):
                print(f"  ⚠️  Tabela [{tabela}] não existe, pulando coluna [{coluna}]")
                continue

            if _coluna_existe(cursor, tabela, coluna):
                print(f"  ✅ [{tabela}.{coluna}] já existe")
            else:
                cursor.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo_sql}")
                alteracoes += 1
                print(f"  🔧 [{tabela}.{coluna}] ADICIONADA ({tipo_sql})")

        print()

        # ─── 3. RETROCOMPATIBILIDADE ──────────────────────────

        print("═══ RETROCOMPATIBILIDADE ═══\n")

        # 3a. Preencher conferentes faltantes em caixas recebidas
        cursor.execute("""
            UPDATE caixas_individuais
            SET usuario_conferente = (
                SELECT v.usuario_recepcao FROM volumes v
                WHERE v.id = caixas_individuais.volume_id
            )
            WHERE status = 'RECEBIDA'
            AND (usuario_conferente IS NULL OR usuario_conferente = '')
        """)
        preenchidos = cursor.rowcount
        if preenchidos > 0:
            print(f"  🔧 {preenchidos} caixas com conferente preenchido")
            alteracoes += preenchidos

        # 3b. Migrar timestamps legados em logs
        cursor.execute("""
            UPDATE logs
            SET timestamp_brt = timestamp,
                timestamp_utc = timestamp
            WHERE timestamp IS NOT NULL
            AND timestamp_utc IS NULL
        """)
        ts_migrados = cursor.rowcount
        if ts_migrados > 0:
            print(f"  🔧 {ts_migrados} logs com timestamps migrados")
            alteracoes += ts_migrados

        # 3c. Migrar observações legadas de volumes.observacao → volume_observacoes
        try:
            cursor.execute(
                "SELECT id, observacao, data_hora_ultima_recepcao "
                "FROM volumes "
                "WHERE observacao IS NOT NULL AND TRIM(observacao) != ''"
            )
            volumes_legado = cursor.fetchall()
            obs_migradas = 0
            for vol in volumes_legado:
                vol_id = vol[0]
                obs_texto = str(vol[1]).strip()
                data_rec = vol[2] or datetime.now().isoformat()

                cursor.execute(
                    "SELECT 1 FROM volume_observacoes WHERE volume_id = ? AND texto = ?",
                    (vol_id, obs_texto)
                )
                if not cursor.fetchone():
                    cursor.execute(
                        "INSERT INTO volume_observacoes (volume_id, texto, usuario, timestamp) "
                        "VALUES (?, ?, ?, ?)",
                        (vol_id, obs_texto, 'Legado', data_rec)
                    )
                    obs_migradas += 1
            if obs_migradas > 0:
                print(f"  🔧 {obs_migradas} observações legadas migradas")
                alteracoes += obs_migradas
            else:
                print("  ✅ Observações legadas: nenhuma pendente")
        except Exception as e:
            print(f"  ⚠️  Aviso na migração de observações: {e}")

        if alteracoes == 0:
            print("\n  ✅ Nenhuma alteração necessária - banco já está atualizado!")

        conn.commit()

        # Diagnóstico DEPOIS
        print("\n═══ ESTADO APÓS A MIGRAÇÃO ═══")
        diagnosticar(cursor)

        print(f"╔══════════════════════════════════════════╗")
        print(f"║  MIGRAÇÃO CONCLUÍDA: {alteracoes:3d} alterações       ║")
        print(f"╚══════════════════════════════════════════╝")
        return True

    except Exception as e:
        conn.rollback()
        print(f"\n[ERRO] Migração falhou (rollback executado): {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    print("╔══════════════════════════════════════════╗")
    print("║   MIGRAÇÃO COMPLETA ConCAN (todas vers.) ║")
    print("╚══════════════════════════════════════════╝\n")
    migrar()
