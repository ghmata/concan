"""
Testes de Recebimento Individual de Caixas e Integrações de Busca Avançada (busca.html / APIs)
"""
import pytest
import sqlite3
from pathlib import Path
import json
import sys

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "src"))
sys.path.insert(0, str(BASE_DIR))

import app as flask_app
import database

TEST_DB = Path(__file__).parent / "test_busca_database.db"

class MockSheets:
    def __init__(self):
        self.tarefas = []
    def agendar_tarefa(self, target_func, *args):
        self.tarefas.append((target_func.__name__, args))
    def sincronizar_manifesto(self, *args, **kwargs): pass
    def sincronizar_volume(self, *args, **kwargs): pass
    def atualizar_status_cabecalho(self, *args, **kwargs): pass

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
    
    # Criar usuários de teste
    database.criar_usuario("admin_tsre_user", "senha123", "Admin TSRE", "admin_tsre", "TSRE")
    database.criar_usuario("conferente_tsre_user", "senha123", "Conferente TSRE", "operador_tsre", "TSRE")
    database.criar_usuario("admin_can_user", "senha123", "Admin CAN", "admin_can", "CAN")
    database.criar_usuario("conferente_can_user", "senha123", "Conferente CAN", "operador_can", "CAN")
    database.criar_usuario("super_user", "senha123", "Super Admin", "super_admin", "TSRE")
    
    yield mock_sheets
    
    if TEST_DB.exists():
        try:
            TEST_DB.unlink()
        except PermissionError:
            pass

@pytest.fixture
def client(setup_db):
    flask_app.app.config['TESTING'] = True
    flask_app.app.config['WTF_CSRF_ENABLED'] = False
    flask_app.app.secret_key = 'test_secret_key_busca'
    with flask_app.app.test_client() as client:
        yield client

def login(client, username):
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
    row = cursor.fetchone()
    conn.close()
    if row:
        with client.session_transaction() as sess:
            sess['_user_id'] = str(row['id'])

def test_recebimento_individual_caixas_tsre(client, setup_db):
    """Testa recebimento progressivo de caixas individuais (1/3, 2/3, 3/3) e transições de status."""
    login(client, "conferente_tsre_user")
    
    mid = database.criar_manifesto("MANIF-001", "2026-08-18", "SBBR", "SBSC", "101", "C130", None, usuario="op", secao_origem="TSRE")
    vid = database.adicionar_volume(mid, "PAMALS", "PAMALS", "VOL-MULTI-1", 3, secao_origem="TSRE")
    
    # 1. Obter caixas
    res_cx = client.post('/api/obter_caixas', json={'volume_id': vid, 'secao': 'TSRE'})
    assert res_cx.status_code == 200
    caixas = json.loads(res_cx.data)
    assert len(caixas) == 3
    assert all(c['status'] == 'NÃO RECEBIDA' for c in caixas)
    
    # 2. Receber Caixa 1
    res_rec1 = client.post('/api/receber_caixa', json={'volume_id': vid, 'numero_caixa': 1, 'secao': 'TSRE'})
    assert res_rec1.status_code == 200
    
    # Validar busca de volumes: status PARCIAL e 1/3
    res_busca = client.post('/api/busca/volumes', json={'termo': 'VOL-MULTI-1', 'secao': 'TSRE'})
    assert res_busca.status_code == 200
    dados_busca = json.loads(res_busca.data)
    assert len(dados_busca) == 1
    assert dados_busca[0]['quantidade_recebida'] == 1
    assert dados_busca[0]['quantidade_expedida'] == 3
    assert dados_busca[0]['status'] == 'PARCIAL'
    assert 'Conferente TSRE' in dados_busca[0]['usuario_recepcao']
    
    # 3. Receber Caixa 2
    res_rec2 = client.post('/api/receber_caixa', json={'volume_id': vid, 'numero_caixa': 2, 'secao': 'TSRE'})
    assert res_rec2.status_code == 200
    
    res_busca2 = client.post('/api/busca/volumes', json={'termo': 'VOL-MULTI-1', 'secao': 'TSRE'})
    dados2 = json.loads(res_busca2.data)
    assert dados2[0]['quantidade_recebida'] == 2
    assert dados2[0]['status'] == 'PARCIAL'
    
    # 4. Receber Caixa 3
    res_rec3 = client.post('/api/receber_caixa', json={'volume_id': vid, 'numero_caixa': 3, 'secao': 'TSRE'})
    assert res_rec3.status_code == 200
    
    res_busca3 = client.post('/api/busca/volumes', json={'termo': 'VOL-MULTI-1', 'secao': 'TSRE'})
    dados3 = json.loads(res_busca3.data)
    assert dados3[0]['quantidade_recebida'] == 3
    assert dados3[0]['status'] in ['COMPLETO', 'TOTALMENTE RECEBIDO']

def test_desfazer_caixa_individual(client, setup_db):
    """Testa desfazer recebimento de uma caixa específica de um volume."""
    login(client, "conferente_tsre_user")
    
    mid = database.criar_manifesto("MANIF-002", "2026-08-18", "SBBR", "SBSC", "102", "C130", None, usuario="op", secao_origem="TSRE")
    vid = database.adicionar_volume(mid, "PAMALS", "PAMALS", "VOL-DESFAZER-1", 3, secao_origem="TSRE")
    
    # 1. Receber 2 de 3 caixas (manifesto ainda não finalizado)
    client.post('/api/receber_caixa', json={'volume_id': vid, 'numero_caixa': 1, 'secao': 'TSRE'})
    client.post('/api/receber_caixa', json={'volume_id': vid, 'numero_caixa': 2, 'secao': 'TSRE'})
    
    # 2. Desfazer Caixa 2 enquanto pendente/parcial (sem exigir senha)
    res_desf = client.post('/api/desfazer_caixa', json={'volume_id': vid, 'numero_caixa': 2, 'secao': 'TSRE'})
    assert res_desf.status_code == 200
    
    # Verificar que Caixa 1 continua recebida e Caixa 2 não
    res_cx = client.post('/api/obter_caixas', json={'volume_id': vid, 'secao': 'TSRE'})
    caixas = json.loads(res_cx.data)
    c1 = next(c for c in caixas if c['numero_caixa'] == 1)
    c2 = next(c for c in caixas if c['numero_caixa'] == 2)
    assert c1['status'] == 'RECEBIDA'
    assert c2['status'] == 'NÃO RECEBIDA'
    
    # Status do volume deve ser PARCIAL com 1/3
    res_busca = client.post('/api/busca/volumes', json={'termo': 'VOL-DESFAZER-1', 'secao': 'TSRE'})
    dados = json.loads(res_busca.data)
    assert dados[0]['quantidade_recebida'] == 1
    assert dados[0]['status'] == 'PARCIAL'

    # 3. Agora receber 2 e 3 para finalizar o manifesto
    client.post('/api/receber_caixa', json={'volume_id': vid, 'numero_caixa': 2, 'secao': 'TSRE'})
    client.post('/api/receber_caixa', json={'volume_id': vid, 'numero_caixa': 3, 'secao': 'TSRE'})

    # 4. Tentar desfazer caixa em manifesto finalizado sem senha -> 403
    res_bloq = client.post('/api/desfazer_caixa', json={'volume_id': vid, 'numero_caixa': 3, 'secao': 'TSRE'})
    assert res_bloq.status_code == 403

    # 5. Desfazer caixa em manifesto finalizado com senha de admin correta -> 200
    res_com_senha = client.post('/api/desfazer_caixa', json={'volume_id': vid, 'numero_caixa': 3, 'secao': 'TSRE', 'senha': 'senha123'})
    assert res_com_senha.status_code == 200

def test_status_especial_caixa_individual(client, setup_db):
    """Testa marcação de status especial (RETIRADO POR OUTRA PESSOA e NÃO RECEBIDO) em nível de caixa individual."""
    login(client, "conferente_tsre_user")
    
    mid = database.criar_manifesto("MANIF-003", "2026-08-18", "SBBR", "SBSC", "103", "C130", None, usuario="op", secao_origem="TSRE")
    vid = database.adicionar_volume(mid, "PAMALS", "PAMALS", "VOL-ESP-1", 2, secao_origem="TSRE")
    
    # Marcar Caixa 1 como RETIRADO POR OUTRA PESSOA
    res_ret = client.post('/api/status_especial', json={
        'volume_id': vid,
        'numero_caixa': 1,
        'status': 'RETIRADO POR OUTRA PESSOA',
        'retirado_por': 'Cap. Silva',
        'secao': 'TSRE'
    })
    assert res_ret.status_code == 200
    
    # Marcar Caixa 2 como NÃO RECEBIDO
    res_nao = client.post('/api/status_especial', json={
        'volume_id': vid,
        'numero_caixa': 2,
        'status': 'NÃO RECEBIDO',
        'motivo_nao_recebido': 'Faltando no lote',
        'secao': 'TSRE'
    })
    assert res_nao.status_code == 200
    
    # Validar detalhes de observação
    res_obs = client.get(f'/api/volume/{vid}/observacoes?secao=TSRE')
    assert res_obs.status_code == 200
    dados_obs = json.loads(res_obs.data)
    cx1 = next(c for c in dados_obs['caixas'] if c['numero_caixa'] == 1)
    cx2 = next(c for c in dados_obs['caixas'] if c['numero_caixa'] == 2)
    assert cx1['retirado_por'] == 'Cap. Silva'
    assert cx2['motivo_nao_recebido'] == 'Faltando no lote'

def test_permissao_secao_bloqueio_operacao(client, setup_db):
    """Testa que um usuário de outra seção não pode receber caixas em seção que não opera sem ser superadmin."""
    login(client, "conferente_can_user") # Usuário do CAN
    
    mid = database.criar_manifesto("MANIF-004", "2026-08-18", "SBBR", "SBSC", "104", "C130", None, usuario="op", secao_origem="TSRE")
    vid = database.adicionar_volume(mid, "PAMALS", "PAMALS", "VOL-SEC-1", 2, secao_origem="TSRE")
    
    # Tentar receber caixa na TSRE como usuário do CAN
    res = client.post('/api/receber_caixa', json={'volume_id': vid, 'numero_caixa': 1, 'secao': 'TSRE'})
    assert res.status_code == 403
    
    # Tentar status especial na TSRE como usuário do CAN
    res_esp = client.post('/api/status_especial', json={
        'volume_id': vid, 'numero_caixa': 1, 'status': 'NÃO RECEBIDO', 'motivo_nao_recebido': 'Teste', 'secao': 'TSRE'
    })
    assert res_esp.status_code == 403

def test_volume_nao_completo_status_parcial(client, setup_db):
    """Garante que volume com caixas mistas (ex: 1 recebida + 1 retirada + 1 não recebida) conste como PARCIAL."""
    login(client, "conferente_tsre_user")
    
    mid = database.criar_manifesto("MANIF-005", "2026-08-18", "SBBR", "SBSC", "105", "C130", None, usuario="op", secao_origem="TSRE")
    vid = database.adicionar_volume(mid, "PAMALS", "PAMALS", "VOL-PARCIAL-MISTO", 3, secao_origem="TSRE")
    
    # 1. Caixa 1: Recebida
    client.post('/api/receber_caixa', json={'volume_id': vid, 'numero_caixa': 1, 'secao': 'TSRE'})
    
    # 2. Caixa 2: Retirada por terceiro
    client.post('/api/status_especial', json={
        'volume_id': vid, 'numero_caixa': 2, 'status': 'RETIRADO POR OUTRA PESSOA', 'retirado_por': 'Maj. Santos', 'secao': 'TSRE'
    })
    
    # 3. Caixa 3: Não recebida
    client.post('/api/status_especial', json={
        'volume_id': vid, 'numero_caixa': 3, 'status': 'NÃO RECEBIDO', 'motivo_nao_recebido': 'Extraviado', 'secao': 'TSRE'
    })
    
    # Verificar status na Busca Avançada (/api/busca/volumes)
    res_busca = client.post('/api/busca/volumes', json={'termo': 'VOL-PARCIAL-MISTO', 'secao': 'TSRE'})
    dados_busca = json.loads(res_busca.data)
    assert len(dados_busca) == 1
    assert dados_busca[0]['quantidade_recebida'] == 1
    assert dados_busca[0]['quantidade_expedida'] == 3
    assert dados_busca[0]['status'] == 'PARCIAL'
    
    # Verificar status na Janela de Detalhes (/api/manifesto/<id>/volumes)
    res_detalhes = client.get(f'/api/manifesto/{mid}/volumes?secao=TSRE')
    dados_det = json.loads(res_detalhes.data)
    vol_det = next(v for v in dados_det if v['id'] == vid)
    assert vol_det['status'] == 'PARCIAL'
    assert vol_det['quantidade_recebida'] == 1

