"""
Migração do ConCAN v3 → v4
Executa: python migrate_v4.py

Adiciona:
- volumes: motivo_nao_recebido, retirado_por
- caixas_individuais: motivo_nao_recebido
- volume_observacoes: nova tabela para comentários manuais com autoria e data/hora
"""
import sqlite3
import shutil
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "database.db"


def _coluna_existe(cursor, tabela, coluna):
    colunas = [r[1] for r in cursor.execute(f"PRAGMA table_info({tabela})")]
    return coluna in colunas


def migrar():
    if not DB_PATH.exists():
        print("[ERRO] Banco de dados nao encontrado.")
        return

    # Backup
    backup = DB_PATH.with_suffix('.db.bak_v3')
    shutil.copy2(DB_PATH, backup)
    print(f"[OK] Backup criado: {backup}")

    conn = sqlite3.connect(str(DB_PATH), timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL")
    cursor = conn.cursor()

    try:
        conn.execute("BEGIN TRANSACTION")

        # 1. Novas colunas em volumes
        if not _coluna_existe(cursor, 'volumes', 'motivo_nao_recebido'):
            cursor.execute("ALTER TABLE volumes ADD COLUMN motivo_nao_recebido TEXT")
            print("  volumes: coluna motivo_nao_recebido adicionada")
        if not _coluna_existe(cursor, 'volumes', 'retirado_por'):
            cursor.execute("ALTER TABLE volumes ADD COLUMN retirado_por TEXT")
            print("  volumes: coluna retirado_por adicionada")

        # 2. Novas colunas em caixas_individuais
        if not _coluna_existe(cursor, 'caixas_individuais', 'motivo_nao_recebido'):
            cursor.execute("ALTER TABLE caixas_individuais ADD COLUMN motivo_nao_recebido TEXT")
            print("  caixas_individuais: coluna motivo_nao_recebido adicionada")

        # 3. Tabela volume_observacoes
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
        print("  volume_observacoes: tabela criada/verificada")

        conn.commit()
        print("\n[OK] Migracao v4 concluida com sucesso!")

    except Exception as e:
        conn.rollback()
        print(f"\n[ERRO] na migracao (rollback executado): {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    print("=== MIGRACAO ConCAN v3 -> v4 ===\n")
    migrar()
