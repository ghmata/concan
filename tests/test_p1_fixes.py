"""
Testes automatizados para validação das correções de Prioridade 1 (P1).
"""
import pytest
import sqlite3
from pathlib import Path
import os
import sys

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "src"))
sys.path.insert(0, str(BASE_DIR))

import app as flask_app
import database

TEST_DB = Path(__file__).parent / "test_p1_fixes.db"


class MockSheets:
    def __init__(self):
        self.tarefas = []

    def agendar_tarefa(self, target_func, *args):
        self.tarefas.append((target_func.__name__, args))

    def sincronizar_manifesto(self, *args, **kwargs):
        pass

    def sincronizar_volume(self, *args, **kwargs):
        pass

    def atualizar_status_cabecalho(self, *args, **kwargs):
        pass


@pytest.fixture
def setup_db():
    if TEST_DB.exists():
        try:
            TEST_DB.unlink()
        except PermissionError:
            pass

    database.DB_PATH = TEST_DB
    mock_sheets = MockSheets()
    database.sheets = mock_sheets
    database.SHEETS_ENABLED = True
    database.init_database()

    # Criar usuários de teste com senhas reais fortes (sem senhas padrão)
    database.criar_usuario("super_user", "SuperSenhaForte2026!", "Super Admin Real", "super_admin", "TSRE")
    database.criar_usuario("admin_tsre", "TsreAdminSecret99!", "Admin TSRE Real", "admin_tsre", "TSRE")
    database.criar_usuario("admin_can", "CanAdminSecret88!", "Admin CAN Real", "admin_can", "CAN")
    database.criar_usuario("operador_tsre", "OpTsrePass77!", "Operador TSRE", "operador_tsre", "TSRE")

    yield mock_sheets

    if TEST_DB.exists():
        try:
            TEST_DB.unlink()
        except PermissionError:
            pass


# ═══════════════════════════════════════════════════
# TESTES 1: REMOÇÃO DE SENHAS MESTRAS HARDCODED
# ═══════════════════════════════════════════════════

def test_senhas_mestras_antigas_sao_rejeitadas(setup_db):
    """Garante que as antigas senhas hardcoded ('pitaco', 'admin123', 'ConCAN2026') são REJEITADAS."""
    assert not database.validar_senha_admin_secao("pitaco", "TSRE")
    assert not database.validar_senha_admin_secao("pitaco", "CAN")
    assert not database.validar_senha_admin_secao("admin123", "TSRE")
    assert not database.validar_senha_admin_secao("admin123", "CAN")
    assert not database.validar_senha_admin_secao("ConCAN2026", "CAN")
    assert not database.validar_senha_admin_secao("ConCAN2026", "TSRE")
    assert not database.validar_senha_admin_secao("", "TSRE")
    assert not database.validar_senha_admin_secao(None, "TSRE")


def test_senhas_reais_de_administradores_sao_aceitas(setup_db):
    """Valida que as senhas reais dos administradores cadastrados no banco são aceitas corretamente."""
    # Superadmin é aceito em qualquer seção
    assert database.validar_senha_admin_secao("SuperSenhaForte2026!", "TSRE")
    assert database.validar_senha_admin_secao("SuperSenhaForte2026!", "CAN")

    # Admin TSRE é aceito na TSRE, mas não no CAN
    assert database.validar_senha_admin_secao("TsreAdminSecret99!", "TSRE")
    assert not database.validar_senha_admin_secao("TsreAdminSecret99!", "CAN")

    # Admin CAN é aceito no CAN, mas não na TSRE
    assert database.validar_senha_admin_secao("CanAdminSecret88!", "CAN")
    assert not database.validar_senha_admin_secao("CanAdminSecret88!", "TSRE")

    # Senha de operador comum NÃO é aceita como senha admin
    assert not database.validar_senha_admin_secao("OpTsrePass77!", "TSRE")
    assert not database.validar_senha_admin_secao("OpTsrePass77!", "CAN")


# ═══════════════════════════════════════════════════
# TESTES 2: ATUALIZAR_VOLUME_EXTRA COM CONFERENCIA_CAIXA
# ═══════════════════════════════════════════════════

def test_atualizar_volume_extra_aumentar_caixas_sincroniza_conferencia_caixa(setup_db):
    """Testa que aumentar a quantidade de caixas em um volume EXTRA atualiza caixas_individuais E conferencia_caixa."""
    mid = database.criar_manifesto("999000111222", "2026-08-18", "SBBR", "SBSC", "1001", "C130", None, secao_origem="TSRE")
    
    # Criar volume extra com 2 caixas inicialmente
    vid = database.adicionar_volume(
        mid, "CABW", "PAMALS", "999000111222/0001", 2,
        secao_origem="TSRE", prioridade="EXTRA", tipo_material="VOLUME EXTRA"
    )

    # Verificar que inicialmente existem 2 caixas em caixas_individuais e conferencia_caixa
    conn = database.get_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) as qtd FROM caixas_individuais WHERE volume_id = ?", (vid,))
    assert c.fetchone()['qtd'] == 2
    c.execute("SELECT COUNT(*) as qtd FROM conferencia_caixa WHERE volume_id = ? AND secao = 'TSRE'", (vid,))
    assert c.fetchone()['qtd'] == 2
    conn.close()

    # Aumentar para 5 caixas
    sucesso, alteracoes = database.atualizar_volume_extra(vid, "999000111222/0001", "CABW", 5, "Admin TSRE")
    assert sucesso
    assert any(a['campo'] == 'quantidade_expedida' and a['valor_novo'] == '5' for a in alteracoes)

    # Verificar que agora existem 5 caixas em caixas_individuais E em conferencia_caixa
    conn = database.get_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) as qtd FROM caixas_individuais WHERE volume_id = ?", (vid,))
    assert c.fetchone()['qtd'] == 5
    c.execute("SELECT COUNT(*) as qtd FROM conferencia_caixa WHERE volume_id = ? AND secao = 'TSRE'", (vid,))
    assert c.fetchone()['qtd'] == 5

    # Verificar números das caixas
    c.execute("SELECT numero_caixa FROM conferencia_caixa WHERE volume_id = ? AND secao = 'TSRE' ORDER BY numero_caixa", (vid,))
    numeros = [r['numero_caixa'] for r in c.fetchall()]
    assert numeros == [1, 2, 3, 4, 5]
    conn.close()


def test_atualizar_volume_extra_diminuir_caixas_sincroniza_conferencia_caixa(setup_db):
    """Testa que diminuir a quantidade de caixas em um volume EXTRA remove o excedente em conferencia_caixa."""
    mid = database.criar_manifesto("888000111222", "2026-08-18", "SBBR", "SBSC", "1002", "C130", None, secao_origem="TSRE")
    
    # Criar volume extra com 4 caixas
    vid = database.adicionar_volume(
        mid, "CABW", "PAMALS", "888000111222/0001", 4,
        secao_origem="TSRE", prioridade="EXTRA", tipo_material="VOLUME EXTRA"
    )

    # Diminuir para 2 caixas
    sucesso, alteracoes = database.atualizar_volume_extra(vid, "888000111222/0001", "CABW", 2, "Admin TSRE")
    assert sucesso

    conn = database.get_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) as qtd FROM caixas_individuais WHERE volume_id = ?", (vid,))
    assert c.fetchone()['qtd'] == 2
    c.execute("SELECT COUNT(*) as qtd FROM conferencia_caixa WHERE volume_id = ? AND secao = 'TSRE'", (vid,))
    assert c.fetchone()['qtd'] == 2

    c.execute("SELECT numero_caixa FROM conferencia_caixa WHERE volume_id = ? AND secao = 'TSRE' ORDER BY numero_caixa", (vid,))
    numeros = [r['numero_caixa'] for r in c.fetchall()]
    assert numeros == [1, 2]
    conn.close()


# ═══════════════════════════════════════════════════
# TESTES 3: SECRET_KEY NO FLASK
# ═══════════════════════════════════════════════════

def test_app_secret_key_carregada():
    """Garante que a secret_key está definida e funcional no app Flask."""
    assert flask_app.app.secret_key is not None
    assert len(flask_app.app.secret_key) > 0
