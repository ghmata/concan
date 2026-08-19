"""
Migração v6 - Correções de Segurança P1 (Auditoria Técnica)
Executa: python migrate_v6_seguranca_p1.py

Objetivo:
- Garantir que existam administradores com senhas reais no banco (as senhas mestras
  hardcoded 'pitaco', 'admin123' e 'ConCAN2026' foram removidas do código).
- Sincronizar a tabela conferencia_caixa para volumes extramanifesto que possam
  ter inconsistências (caixas existentes em caixas_individuais mas ausentes em
  conferencia_caixa).
- Recalcular os status de conferencia_volume e manifesto_secao para manter
  integridade dos totalizadores.
- Totalmente idempotente (seguro para rodar múltiplas vezes).

IMPORTANTE: Após a migração, as ÚNICAS senhas aceitas para operações administrativas
(desfazer recebimento de manifesto finalizado, alterar informações fixas) são as
senhas reais dos usuários com role 'super_admin', 'admin_tsre' ou 'admin_can'
cadastrados na tabela 'users'.
"""
import sqlite3
import shutil
import sys
import os
from pathlib import Path
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

# Assegura utf-8 no stdout do terminal Windows se possível
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

DB_PATH = Path(__file__).parent / "data" / "database.db"


def _tabela_existe(cursor, tabela):
    """Verifica se uma tabela já existe no banco."""
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (tabela,)
    )
    return cursor.fetchone() is not None


def diagnosticar_admins(cursor):
    """Mostra os administradores cadastrados no banco."""
    print("\n--- Administradores Cadastrados ---")
    cursor.execute("""
        SELECT username, nome, role, secao FROM users 
        WHERE role IN ('super_admin', 'admin_tsre', 'admin_can', 'admin')
        ORDER BY role, username
    """)
    admins = cursor.fetchall()
    if not admins:
        print("  [ALERTA] NENHUM administrador encontrado no banco!")
        print("  [ALERTA] Sem administradores, operações de desfazimento e")
        print("  [ALERTA] alteração de informações fixas ficarão bloqueadas.")
    else:
        for a in admins:
            print(f"  - [{a[2]}] {a[1]} (@{a[0]}) | Seção: {a[3] or 'N/A'}")
    print()
    return admins


def diagnosticar_conferencia_caixa(cursor):
    """Verifica inconsistências entre caixas_individuais e conferencia_caixa."""
    print("--- Diagnóstico de Integridade: conferencia_caixa ---")

    # Caixas que existem em caixas_individuais mas NÃO em conferencia_caixa para alguma seção ativa
    cursor.execute("""
        SELECT ci.volume_id, ci.numero_caixa, v.numero_volume, ms.secao
        FROM caixas_individuais ci
        JOIN volumes v ON v.id = ci.volume_id
        JOIN manifesto_secao ms ON ms.manifesto_id = v.manifesto_id AND ms.excluido = 0
        WHERE NOT EXISTS (
            SELECT 1 FROM conferencia_caixa cc 
            WHERE cc.volume_id = ci.volume_id 
            AND cc.numero_caixa = ci.numero_caixa 
            AND cc.secao = ms.secao
        )
    """)
    orfas = cursor.fetchall()

    if orfas:
        print(f"  [ALERTA] {len(orfas)} caixas encontradas em caixas_individuais")
        print(f"           sem registro correspondente em conferencia_caixa.")
        secoes_afetadas = set(o[3] for o in orfas)
        volumes_afetados = set(o[0] for o in orfas)
        print(f"           Seções: {', '.join(secoes_afetadas)}")
        print(f"           Volumes afetados: {len(volumes_afetados)}")
    else:
        print("  [OK] Todas as caixas estão sincronizadas entre caixas_individuais e conferencia_caixa.")
    print()
    return orfas


def migrar():
    if not DB_PATH.exists():
        print("[ERRO] Banco de dados não encontrado em:", DB_PATH.resolve())
        return False

    print(f"[INFO] Banco: {DB_PATH.resolve()}")
    print(f"[INFO] Tamanho: {DB_PATH.stat().st_size / 1024:.1f} KB\n")

    # 1. Backup automático com timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = DB_PATH.parent / f"database_backup_v6_seguranca_{timestamp}.db"
    shutil.copy2(DB_PATH, backup)
    print(f"[OK] Backup v6 criado: {backup}\n")

    conn = sqlite3.connect(str(DB_PATH), timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    alteracoes = 0

    try:
        # ═══════════════════════════════════════════════════
        # ETAPA 1: VERIFICAÇÃO DE ADMINISTRADORES
        # ═══════════════════════════════════════════════════
        print("==========================================")
        print("  ETAPA 1: VERIFICAÇÃO DE ADMINISTRADORES")
        print("==========================================\n")

        admins = diagnosticar_admins(cursor)

        if not admins:
            print("  ╔══════════════════════════════════════════════════════╗")
            print("  ║  ATENÇÃO: Nenhum administrador cadastrado no banco! ║")
            print("  ║                                                      ║")
            print("  ║  As senhas mestras hardcoded foram REMOVIDAS.        ║")
            print("  ║  Sem administradores, operações protegidas ficarão   ║")
            print("  ║  inacessíveis.                                       ║")
            print("  ║                                                      ║")
            print("  ║  Deseja criar um super_admin emergencial agora?      ║")
            print("  ╚══════════════════════════════════════════════════════╝")
            print()
            resposta = input("  Criar super_admin emergencial? (s/N): ").strip().lower()
            if resposta == 's':
                username = input("  Username: ").strip() or "admin"
                nome = input("  Nome completo: ").strip() or "Administrador"
                senha = input("  Senha: ").strip()
                if not senha:
                    print("  [ERRO] Senha não pode ser vazia. Pulando criação.")
                else:
                    senha_hash = generate_password_hash(senha)
                    cursor.execute("""
                        INSERT INTO users (username, password_hash, nome, role, secao)
                        VALUES (?, ?, ?, 'super_admin', 'TSRE')
                    """, (username, senha_hash, nome))
                    alteracoes += 1
                    print(f"  [OK] Super admin '{username}' criado com sucesso!")
            else:
                print("  [INFO] Nenhum admin criado. Lembre-se de criar um via '/usuarios' após o deploy.")
        else:
            # Verificar se algum admin tem senha que era uma das senhas mestras
            senhas_fracas_encontradas = False
            senhas_mestras = ['pitaco', 'admin123', 'ConCAN2026']
            for admin in admins:
                cursor.execute("SELECT password_hash FROM users WHERE username = ?", (admin[0],))
                row = cursor.fetchone()
                if row:
                    for senha_fraca in senhas_mestras:
                        if check_password_hash(row['password_hash'], senha_fraca):
                            senhas_fracas_encontradas = True
                            print(f"  [AVISO] Admin '{admin[0]}' possui senha fraca (antiga senha mestra).")
                            print(f"          Recomenda-se alterar via /perfil após o deploy.")

            if not senhas_fracas_encontradas:
                print("  [OK] Nenhum administrador com senhas fracas conhecidas.")

        print()

        # ═══════════════════════════════════════════════════
        # ETAPA 2: SINCRONIZAÇÃO DE CONFERENCIA_CAIXA
        # ═══════════════════════════════════════════════════
        print("==========================================")
        print("  ETAPA 2: SINCRONIZAÇÃO conferencia_caixa")
        print("==========================================\n")

        if not _tabela_existe(cursor, 'conferencia_caixa'):
            print("  [AVISO] Tabela conferencia_caixa não existe.")
            print("  [INFO] Execute primeiro a migração v5 (migrate_v5_multisecao.py).")
        else:
            orfas = diagnosticar_conferencia_caixa(cursor)

            if orfas:
                print("  Sincronizando caixas órfãs...")
                conn.execute("BEGIN TRANSACTION")

                # Inserir caixas faltantes em conferencia_caixa usando dados de caixas_individuais
                cursor.execute("""
                    INSERT OR IGNORE INTO conferencia_caixa 
                        (volume_id, numero_caixa, secao, status, data_hora_recepcao, 
                         usuario_conferente, retirado_por, retirado_por_tipo, motivo_nao_recebido)
                    SELECT ci.volume_id, ci.numero_caixa, ms.secao, ci.status, 
                           ci.data_hora_recepcao, ci.usuario_conferente, 
                           ci.retirado_por, ci.retirado_por_tipo, ci.motivo_nao_recebido
                    FROM caixas_individuais ci
                    JOIN volumes v ON v.id = ci.volume_id
                    JOIN manifesto_secao ms ON ms.manifesto_id = v.manifesto_id AND ms.excluido = 0
                    WHERE NOT EXISTS (
                        SELECT 1 FROM conferencia_caixa cc 
                        WHERE cc.volume_id = ci.volume_id 
                        AND cc.numero_caixa = ci.numero_caixa 
                        AND cc.secao = ms.secao
                    )
                """)
                sincronizados = cursor.rowcount
                alteracoes += sincronizados
                print(f"  [MIGRADO] {sincronizados} caixas sincronizadas em conferencia_caixa.")

                conn.commit()
            else:
                print("  [OK] Nenhuma sincronização necessária.")

        print()

        # ═══════════════════════════════════════════════════
        # ETAPA 3: RECÁLCULO DE STATUS (conferencia_volume)
        # ═══════════════════════════════════════════════════
        print("==========================================")
        print("  ETAPA 3: RECÁLCULO DE STATUS")
        print("==========================================\n")

        if _tabela_existe(cursor, 'conferencia_volume') and _tabela_existe(cursor, 'conferencia_caixa'):
            conn.execute("BEGIN TRANSACTION")

            # Recalcular quantidade_recebida em conferencia_volume a partir de conferencia_caixa
            cursor.execute("""
                UPDATE conferencia_volume SET quantidade_recebida = (
                    SELECT COUNT(*) FROM conferencia_caixa cc
                    WHERE cc.volume_id = conferencia_volume.volume_id 
                    AND cc.secao = conferencia_volume.secao
                    AND cc.status IN ('RECEBIDA', 'RETIRADA POR OUTRA PESSOA', 'NÃO RECEBIDA COM MOTIVO')
                )
                WHERE EXISTS (
                    SELECT 1 FROM conferencia_caixa cc2
                    WHERE cc2.volume_id = conferencia_volume.volume_id
                    AND cc2.secao = conferencia_volume.secao
                )
            """)
            recalculados_cv = cursor.rowcount
            if recalculados_cv > 0:
                print(f"  [RECALCULADO] {recalculados_cv} registros de conferencia_volume atualizados.")
                alteracoes += recalculados_cv

            # Atualizar status de conferencia_volume baseado na contagem
            cursor.execute("""
                UPDATE conferencia_volume SET status = 
                    CASE 
                        WHEN quantidade_recebida >= (
                            SELECT v.quantidade_expedida FROM volumes v WHERE v.id = conferencia_volume.volume_id
                        ) THEN 'RECEBIDO'
                        WHEN quantidade_recebida > 0 THEN 'PARCIAL'
                        ELSE 'NÃO RECEBIDO'
                    END
                WHERE EXISTS (
                    SELECT 1 FROM volumes v2 WHERE v2.id = conferencia_volume.volume_id
                )
            """)
            status_atualizados = cursor.rowcount
            if status_atualizados > 0:
                print(f"  [RECALCULADO] {status_atualizados} status de conferencia_volume recalculados.")

            # Recalcular status de manifesto_secao
            cursor.execute("""
                UPDATE manifesto_secao SET status_conferencia = (
                    CASE
                        WHEN (SELECT COUNT(*) FROM conferencia_volume cv 
                              JOIN volumes v ON v.id = cv.volume_id 
                              WHERE v.manifesto_id = manifesto_secao.manifesto_id 
                              AND cv.secao = manifesto_secao.secao
                              AND cv.status IN ('RECEBIDO', 'RETIRADA POR OUTRA PESSOA', 'NÃO RECEBIDA COM MOTIVO')
                             ) >= (
                              SELECT COUNT(*) FROM volumes v2 
                              WHERE v2.manifesto_id = manifesto_secao.manifesto_id
                             ) THEN 'RECEBIDO'
                        WHEN (SELECT COUNT(*) FROM conferencia_volume cv2 
                              JOIN volumes v3 ON v3.id = cv2.volume_id 
                              WHERE v3.manifesto_id = manifesto_secao.manifesto_id 
                              AND cv2.secao = manifesto_secao.secao
                              AND cv2.status != 'NÃO RECEBIDO'
                             ) > 0 THEN 'PARCIAL'
                        ELSE 'NÃO RECEBIDO'
                    END
                )
                WHERE excluido = 0
            """)
            ms_atualizados = cursor.rowcount
            if ms_atualizados > 0:
                print(f"  [RECALCULADO] {ms_atualizados} status de manifesto_secao recalculados.")

            conn.commit()
        else:
            print("  [INFO] Tabelas de conferência não existem. Nada a recalcular.")

        if alteracoes == 0:
            print("\n  [OK] Nenhuma alteração necessária - banco já está consistente!")

        # ═══════════════════════════════════════════════════
        # RESUMO FINAL
        # ═══════════════════════════════════════════════════
        print()
        print("==========================================")
        print(f"  MIGRAÇÃO V6 (SEGURANÇA P1) CONCLUÍDA")
        print(f"  Total de alterações: {alteracoes}")
        print("==========================================")
        print()
        print("  LEMBRETE PÓS-DEPLOY:")
        print("  1. Configure CONCAN_SECRET_KEY no ambiente de produção")
        print("     (PythonAnywhere → Web → Environment Variables)")
        print("  2. Verifique que ao menos um admin existe via /usuarios")
        print("  3. As senhas 'pitaco', 'admin123' e 'ConCAN2026' NÃO")
        print("     são mais aceitas para operações administrativas.")
        print()
        return True

    except Exception as e:
        conn.rollback()
        print(f"\n[ERRO] Migração v6 falhou (rollback executado): {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        conn.close()


if __name__ == "__main__":
    print("==========================================")
    print("   MIGRAÇÃO V6 CONCAN (SEGURANÇA P1)")
    print("==========================================\n")
    migrar()
