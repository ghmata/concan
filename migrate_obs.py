import sqlite3
from pathlib import Path
from datetime import datetime, timezone, timedelta

DB_PATH = Path("data/database.db")
BRT = timezone(timedelta(hours=-3))

def get_agora_br():
    return datetime.now(BRT).replace(microsecond=0).isoformat()

def migrar_observacoes():
    if not DB_PATH.exists():
        print("Banco de dados nao encontrado.")
        return

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        # Obter volumes que possuem observações preenchidas
        cursor.execute("SELECT id, numero_volume, observacao, data_hora_ultima_recepcao FROM volumes WHERE observacao IS NOT NULL AND observacao != ''")
        volumes_com_obs = cursor.fetchall()
        
        print(f"Encontrados {len(volumes_com_obs)} volumes com observações legado.")
        migrados = 0
        
        for vol in volumes_com_obs:
            vol_id = vol['id']
            obs_texto = vol['observacao'].strip()
            data_rec = vol['data_hora_ultima_recepcao'] or get_agora_br()
            
            # Verificar se já existe essa observação na nova tabela
            cursor.execute("SELECT 1 FROM volume_observacoes WHERE volume_id = ? AND texto = ?", (vol_id, obs_texto))
            existe = cursor.fetchone()
            
            if not existe:
                cursor.execute("""
                    INSERT INTO volume_observacoes (volume_id, texto, usuario, timestamp)
                    VALUES (?, ?, ?, ?)
                """, (vol_id, obs_texto, 'Legado', data_rec))
                migrados += 1
                
        conn.commit()
        print(f"[OK] Migração concluída. {migrados} observações migradas para a tabela volume_observacoes.")
    except Exception as e:
        print(f"Erro na migração: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    migrar_observacoes()
