"""
Migração do ConCAN v2 → v3
Executa: python migrate_v3.py

Adiciona:
- caixas_individuais: retirado_por, retirado_por_tipo
- logs: volume_id, caixa_numero, estado_anterior, estado_posterior, timestamp_utc, timestamp_brt
- Retrocompatibilidade: preenche usuario_conferente faltante em caixas já recebidas
"""
import sqlite3
import shutil
from pathlib import Path
from datetime import datetime, timezone, timedelta

DB_PATH = Path(__file__).parent / "data" / "database.db"
BRT = timezone(timedelta(hours=-3))


def _coluna_existe(cursor, tabela, coluna):
    """Verifica se uma coluna já existe na tabela."""
    colunas = [r[1] for r in cursor.execute(f"PRAGMA table_info({tabela})")]
    return coluna in colunas


def migrar():
    if not DB_PATH.exists():
        print("[ERRO] Banco de dados nao encontrado. Execute o app primeiro para cria-lo.")
        return

    # 1. Backup automático
    backup = DB_PATH.with_suffix('.db.bak_v2')
    shutil.copy2(DB_PATH, backup)
    print(f"[OK] Backup criado: {backup}")

    conn = sqlite3.connect(str(DB_PATH), timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL")
    cursor = conn.cursor()

    try:
        conn.execute("BEGIN TRANSACTION")

        # ─── 2. Novas colunas em caixas_individuais ───
        alteracoes_ci = 0
        if not _coluna_existe(cursor, 'caixas_individuais', 'retirado_por'):
            cursor.execute("ALTER TABLE caixas_individuais ADD COLUMN retirado_por TEXT")
            alteracoes_ci += 1
        if not _coluna_existe(cursor, 'caixas_individuais', 'retirado_por_tipo'):
            cursor.execute("ALTER TABLE caixas_individuais ADD COLUMN retirado_por_tipo TEXT")
            alteracoes_ci += 1
        print(f"  caixas_individuais: {alteracoes_ci} colunas adicionadas")

        # ─── 3. Novas colunas em logs ───
        novas_logs = {
            'volume_id': 'INTEGER',
            'caixa_numero': 'INTEGER',
            'estado_anterior': 'TEXT',
            'estado_posterior': 'TEXT',
            'timestamp_utc': 'DATETIME',
            'timestamp_brt': 'DATETIME',
        }
        alteracoes_logs = 0
        for col, tipo in novas_logs.items():
            if not _coluna_existe(cursor, 'logs', col):
                cursor.execute(f"ALTER TABLE logs ADD COLUMN {col} {tipo}")
                alteracoes_logs += 1
        print(f"  logs: {alteracoes_logs} colunas adicionadas")

        # ─── 4. Retrocompatibilidade: preencher conferentes faltantes ───
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
        print(f"  Retrocompatibilidade: {preenchidos} caixas com conferente preenchido")

        # ─── 5. Migrar timestamps legados ───
        cursor.execute("""
            UPDATE logs
            SET timestamp_brt = timestamp,
                timestamp_utc = timestamp
            WHERE timestamp IS NOT NULL
            AND timestamp_utc IS NULL
        """)
        ts_migrados = cursor.rowcount
        print(f"  Timestamps: {ts_migrados} logs migrados")

        conn.commit()
        print("\n[OK] Migracao v3 concluida com sucesso!")

    except Exception as e:
        conn.rollback()
        print(f"\n[ERRO] na migracao (rollback executado): {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    print("=== MIGRACAO ConCAN v2 -> v3 ===\n")
    migrar()
