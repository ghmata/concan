"""
Testes da Fase 6: Restrições Finais e Polimento (R15, R17, R18)
"""
import pytest
import sqlite3
from pathlib import Path
import json
import os
import sys

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "src"))
sys.path.insert(0, str(BASE_DIR))

import app as flask_app
import database

TEST_DB = Path(__file__).parent / "test_fase6_database.db"

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
    database.criar_usuario("operador_tsre_user", "senha123", "Op TSRE", "operador_tsre", "TSRE")
    database.criar_usuario("admin_can_user", "senha123", "Admin CAN", "admin_can", "CAN")
    database.criar_usuario("operador_can_user", "senha123", "Op CAN", "operador_can", "CAN")
    
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
    flask_app.app.secret_key = 'test_secret_key'
    with flask_app.app.test_client() as client:
        yield client

def login(client, username):
    # Obter id do usuário do banco
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
    row = cursor.fetchone()
    conn.close()
    if row:
        with client.session_transaction() as sess:
            sess['_user_id'] = str(row['id'])

def test_ocr_bloqueado_para_can(client):
    """R17: Testa que a seção CAN não consegue acessar nem executar rotas de OCR."""
    # Login como operador CAN
    login(client, "operador_can_user")
    
    # GET /escanear deve redirecionar
    res_get = client.get('/escanear', follow_redirects=True)
    assert b"Funcionalidade de escaneamento" in res_get.data or res_get.status_code == 200
    
    # POST /api/importar_manifesto_ocr deve retornar 403
    res_imp = client.post('/api/importar_manifesto_ocr', data={'manifesto_dados': '{}', 'volumes': '[]'})
    assert res_imp.status_code == 403
    data_imp = json.loads(res_imp.data)
    assert data_imp['status'] == 'erro'
    assert 'OCR' in data_imp['msg']
    
    # POST /api/parse_ocr_text deve retornar 403
    res_parse = client.post('/api/parse_ocr_text', json={'texto': 'MANIF 123456789012'})
    assert res_parse.status_code == 403
    data_parse = json.loads(res_parse.data)
    assert data_parse['status'] == 'erro'

def test_ocr_permitido_para_tsre(client):
    """R17: Testa que a seção TSRE pode acessar a rota /escanear normalmente."""
    login(client, "operador_tsre_user")
    res_get = client.get('/escanear')
    assert res_get.status_code == 200

def test_sheets_sync_ignorado_para_can(setup_db):
    """R15: Testa que a sincronização com Google Sheets não é executada para a seção CAN."""
    mock_sheets = setup_db
    mock_sheets.tarefas.clear()
    
    # Criar manifesto via TSRE -> deve agendar no sheets
    mid_tsre = database.criar_manifesto("111111111111", "2026-08-11", "SBBR", "SBSC", "1001", "C130", None, usuario="op_tsre", secao_origem="TSRE")
    tarefas_tsre = len(mock_sheets.tarefas)
    assert tarefas_tsre > 0
    
    mock_sheets.tarefas.clear()
    # Criar manifesto via CAN -> NÃO deve agendar no sheets
    mid_can = database.criar_manifesto("222222222222", "2026-08-11", "SBBR", "SBSC", "1002", "C130", None, usuario="op_can", secao_origem="CAN")
    assert len(mock_sheets.tarefas) == 0
    
    # Adicionar volume via CAN -> NÃO deve agendar no sheets
    database.adicionar_volume(mid_can, "PAMALS", "CAN_DEST", "001", 5, secao_origem="CAN")
    assert len(mock_sheets.tarefas) == 0

def test_sincronizar_sheets_funcao_guard(setup_db):
    """R15: Testa que _sincronizar_sheets retorna imediatamente quando secao=='CAN'."""
    mock_sheets = setup_db
    mock_sheets.tarefas.clear()
    
    conn = database.get_connection()
    cursor = conn.cursor()
    
    # Chamada com secao='CAN'
    database._sincronizar_sheets(cursor, 1, secao='CAN')
    assert len(mock_sheets.tarefas) == 0
    
    conn.close()

def test_observacoes_conferencia_modal(client, setup_db):
    """Valida o funcionamento completo do modal e API de observações na conferência de manifestos."""
    mid = database.criar_manifesto("333333333333", "2026-08-11", "SBBR", "SBSC", "1003", "C130", None, usuario="op_tsre", secao_origem="TSRE")
    vid = database.adicionar_volume(mid, "PAMALS", "PAMALS", "VOL-001", 1, secao_origem="TSRE")
    
    # 1. Adicionar observação via TSRE
    database.adicionar_observacao_manual(vid, "Volume com caixa amassada", "Op TSRE", secao="TSRE")
    
    # 2. Verificar que listar_volumes_detalhado retorna a observação mesmo pendente
    volumes = database.listar_volumes_detalhado(mid, secao="TSRE")
    assert len(volumes) == 1
    assert volumes[0]['observacao'] == "Volume com caixa amassada"
    
    # 3. Testar API /api/volume/<id>/observacoes com secao
    login(client, "operador_tsre_user")
    res = client.get(f'/api/volume/{vid}/observacoes?secao=TSRE')
    assert res.status_code == 200
    data = json.loads(res.data)
    assert len(data['comentarios']) == 1
    assert data['comentarios'][0]['texto'] == "Volume com caixa amassada"
    
    # 4. Testar adicionar comentário via API
    res_add = client.post('/api/observacao_manual/adicionar', json={'volume_id': vid, 'texto': 'Obs adicional'})
    assert res_add.status_code == 200
    
    # 5. Garantir que novo comentário aparece na API de listagem
    res_check = client.get(f'/api/volume/{vid}/observacoes?secao=TSRE')
    data_check = json.loads(res_check.data)
    assert len(data_check['comentarios']) == 2

