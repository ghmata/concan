"""
Testes Unitários e de Integração — Pipeline de OCR e Segurança do ConCAN
Arquivo: tests/test_ocr_pipeline.py
"""

import unittest
import json
import io
import os
import sys
import shutil
import sqlite3
from pathlib import Path

# Ajustar path para importar módulos do ConCAN
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

# Mock do Banco de Dados para os testes
import database
TEST_DB = Path(__file__).parent / "test_ocr_database.db"
database.DB_PATH = TEST_DB

class MockSheets:
    def sincronizar_manifesto(self, *args, **kwargs): pass
    def sincronizar_volume(self, *args, **kwargs): pass
    def atualizar_status_cabecalho(self, *args, **kwargs): pass
    def agendar_tarefa(self, func, *args): pass

database.SHEETS_ENABLED = True
database.sheets = MockSheets()

from app import app, UPLOAD_FOLDER
from ocr_parser import parse_ocr_text
from database import init_database, get_connection, obter_manifesto, obter_imagens_manifesto_ocr, criar_usuario

class TestOCRPipeline(unittest.TestCase):

    def setUp(self):
        """Prepara o banco de dados de teste de forma robusta sem deletar o arquivo físico no Windows."""
        init_database()
        
        # Limpa os dados das tabelas e reseta a sequência do autoincrement
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM logs")
            cursor.execute("DELETE FROM caixas_individuais")
            cursor.execute("DELETE FROM volumes")
            cursor.execute("DELETE FROM manifestos")
            cursor.execute("DELETE FROM users")
            cursor.execute("DELETE FROM volume_observacoes")
            cursor.execute("DELETE FROM sqlite_sequence")
            conn.commit()
        except sqlite3.OperationalError:
            pass
        finally:
            conn.close()
            
        # Cria o usuário para permitir bypass de autenticação no login_required
        criar_usuario('admin', 'senha', 'Administrador', 'admin')
        
        # Obtém o ID exato gerado para o usuário admin (evita problemas de autoincrement desalinhado)
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE username = 'admin'")
        user_row = cursor.fetchone()
        user_id = str(user_row['id']) if user_row else '1'
        conn.close()
        
        # Limpar diretórios temporários na pasta de uploads de teste se necessário
        self.temp_upload_dir = Path(UPLOAD_FOLDER) / "manifestos_escaneados"
        if self.temp_upload_dir.exists():
            try:
                shutil.rmtree(self.temp_upload_dir)
            except Exception:
                pass
            
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        self.client = app.test_client()
        
        # Cria uma sessão simulada para as rotas que exigem login
        with self.client.session_transaction() as sess:
            sess['_user_id'] = user_id  # Vinculado ao ID real do usuário no banco
            
    def tearDown(self):
        """Limpa dados pós-teste."""
        if self.temp_upload_dir.exists():
            try:
                shutil.rmtree(self.temp_upload_dir)
            except Exception:
                pass

    def test_ocr_parser_tolerante_ruido(self):
        """Testa se o ocr_parser extrai corretamente manifesto e volumes mesmo com ruído."""
        texto_ocr_ruidoso = (
            "MANIFESTO DE CARGA AÉREA NACIONAL\n"
            "Manifesto: 202612345678\n"  # Manifesto de 12 dígitos
            "ORIGEM: PCAN-DF   DESTINO: TCTL-LS\n"
            "MISSÃO: OPERAÇÃO OCR 2026\n"
            "AERONAVE: C-105\n"
            "TOTAIS DE VOLUMES E CAIXAS\n"
            "Volume 202612345678/0001  CABW  PAMALS  4  120.5  0.88  02\n"  # Volume simples
            "Outro texto irrelevante no meio...\n"
            "202612345678/0002-0004   CABE   PAMALS   1   40.0   0.22   00\n" # Volume com hífen
        )

        dados, volumes, erros = parse_ocr_text(texto_ocr_ruidoso)
        
        self.assertEqual(len(erros), 0)
        self.assertEqual(dados['numero_manifesto'], '202612345678')
        self.assertEqual(dados['terminal_origem'], 'PCAN-DF')
        self.assertEqual(dados['terminal_destino'], 'TCTL-LS')
        self.assertEqual(dados['aeronave'], 'C-105')
        
        self.assertEqual(len(volumes), 2)
        # Primeiro volume
        self.assertEqual(volumes[0]['numero_volume'], '202612345678/0001')
        self.assertEqual(volumes[0]['remetente'], 'CABW')
        self.assertEqual(volumes[0]['quantidade_expedida'], 4)
        
        # Segundo volume
        self.assertEqual(volumes[1]['numero_volume'], '202612345678/0002-0004')
        self.assertEqual(volumes[1]['remetente'], 'CABE')
        self.assertEqual(volumes[1]['quantidade_expedida'], 1)

    def test_api_parse_ocr_endpoint(self):
        """Testa se a API de parsing AJAX responde corretamente com JSON estruturado."""
        payload = {'texto': 'Manifesto: 999988887777\nVolume: 999988887777/0001 CABW 1'}
        resposta = self.client.post('/api/parse_ocr_text', 
                                    data=json.dumps(payload),
                                    content_type='application/json')
        
        self.assertEqual(resposta.status_code, 200)
        data = json.loads(resposta.data.decode('utf-8'))
        
        self.assertEqual(data['dados_manifesto']['numero_manifesto'], '999988887777')
        self.assertEqual(len(data['volumes']), 1)
        self.assertEqual(data['volumes'][0]['numero_volume'], '999988887777/0001')

    def test_seguranca_magic_bytes_e_tipo_imagem(self):
        """SEC-01: Testa se o backend rejeita arquivos maliciosos e arquivos com MIME-types inválidos."""
        manifesto_dados = {
            'numero_manifesto': '111122223333',
            'terminal_origem': 'PCAN-DF',
            'terminal_destino': 'TCTL-LS',
            'missao': 'TEST-SEC',
            'aeronave': 'C-105'
        }
        volumes = [
            {'numero_volume': '111122223333/0001', 'remetente': 'CABW', 'quantidade_expedida': 1}
        ]

        # 1. Arquivo malicioso: SVG renomeado para .jpg -> Deve rejeitar pelos Magic Bytes
        img_falsa = io.BytesIO(b'<svg onload="alert(1)">Text</svg>')
        payload_malicioso = {
            'manifesto_dados': json.dumps(manifesto_dados),
            'volumes': json.dumps(volumes),
            'imagens': (img_falsa, 'perigoso.jpg', 'image/jpeg')
        }
        
        resposta = self.client.post('/api/importar_manifesto_ocr', data=payload_malicioso)
        
        if resposta.status_code != 400:
            print("DEBUG BAD JPEG response:", resposta.data.decode('utf-8'))
        self.assertEqual(resposta.status_code, 400)
        data = json.loads(resposta.data.decode('utf-8'))
        mensagem = data['msg'].lower()
        self.assertTrue(any(x in mensagem for x in ["cabeçalho", "invalido", "inválido", "magic", "assinatura", "imagem"]))

        # 2. Enviar com MIME-type inválido (ex: .exe) -> Deve rejeitar
        img_jpeg = io.BytesIO(b'\xff\xd8\xff\xe0\x00\x10JFIF\x00...')
        payload_mime_invalido = {
            'manifesto_dados': json.dumps(manifesto_dados),
            'volumes': json.dumps(volumes),
            'imagens': (img_jpeg, 'executavel.exe', 'application/octet-stream')
        }
        
        resposta = self.client.post('/api/importar_manifesto_ocr', data=payload_mime_invalido)
        
        if resposta.status_code != 400:
            print("DEBUG BAD MIME response:", resposta.data.decode('utf-8'))
        self.assertEqual(resposta.status_code, 400)
        data = json.loads(resposta.data.decode('utf-8'))
        self.assertIn("mime-type", data['msg'].lower())

    def test_importacao_ocr_fluxo_completo_e_auditoria(self):
        """RF-07, RF-08: Verifica a persistência correta, o arquivamento de imagens e o log de auditoria."""
        img_jpeg = io.BytesIO(b'\xff\xd8\xff\xe0\x00\x10JFIF\x00...')
        
        manifesto_dados = {
            'numero_manifesto': '123412341234',
            'terminal_origem': 'PCAN-DF',
            'terminal_destino': 'TCTL-LS',
            'missao': 'OP-OCR',
            'aeronave': 'C-105'
        }
        volumes = [
            {'numero_volume': '123412341234/0001', 'remetente': 'CABW', 'quantidade_expedida': 2, 'prioridade': '02'}
        ]

        payload = {
            'manifesto_dados': json.dumps(manifesto_dados),
            'volumes': json.dumps(volumes),
            'imagens': (img_jpeg, 'pagina_1.jpg', 'image/jpeg')
        }
        
        resposta = self.client.post('/api/importar_manifesto_ocr', data=payload)
        
        if resposta.status_code != 200:
            print("DEBUG FULL FLOW response:", resposta.data.decode('utf-8'))
        self.assertEqual(resposta.status_code, 200)

        # Verificar se o manifesto foi inserido no banco
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM manifestos WHERE numero_manifesto = '123412341234'")
        m_row = cursor.fetchone()
        
        self.assertIsNotNone(m_row)
        self.assertEqual(m_row['origem'], 'OCR_MOBILE')
        
        # Verificar se as imagens estão salvas e listadas
        mid = m_row['id']
        imagens_salvas = obter_imagens_manifesto_ocr(mid)
        self.assertEqual(len(imagens_salvas), 1)
        self.assertTrue(imagens_salvas[0].endswith('.jpg'))
        
        # Verificar se o diretório de destino é o pdf_path salvo
        self.assertEqual(m_row['pdf_path'], str(Path(UPLOAD_FOLDER) / "manifestos_escaneados" / str(mid)))
        
        # Verificar log de auditoria
        cursor.execute("SELECT * FROM logs WHERE acao = 'IMPORTAR_OCR' AND manifesto_id = ?", (mid,))
        log_row = cursor.fetchone()
        self.assertIsNotNone(log_row)
        detalhes = json.loads(log_row['estado_posterior'])
        self.assertEqual(detalhes['numero_manifesto'], '123412341234')
        self.assertEqual(detalhes['paginas'], 1)

    def test_rate_limiting_upload(self):
        """SEC-04: Testa se o rate limit bloqueia após 10 requisições consecutivas."""
        manifesto_dados = {'numero_manifesto': '123456789012'}
        volumes = []

        # Realizar 10 requisições reconstruindo o arquivo e payload a cada iteração
        for i in range(10):
            img_jpeg = io.BytesIO(b'\xff\xd8\xff\xe0\x00\x10JFIF\x00...')
            payload = {
                'manifesto_dados': json.dumps(manifesto_dados),
                'volumes': json.dumps(volumes),
                'imagens': (img_jpeg, f'foto_{i}.jpg', 'image/jpeg')
            }
            resposta = self.client.post('/api/importar_manifesto_ocr', data=payload)
            self.assertNotEqual(resposta.status_code, 429)

        # A 11ª requisição na mesma sessão/minuto deve retornar 429
        img_jpeg = io.BytesIO(b'\xff\xd8\xff\xe0\x00\x10JFIF\x00...')
        payload_bloqueado = {
            'manifesto_dados': json.dumps(manifesto_dados),
            'volumes': json.dumps(volumes),
            'imagens': (img_jpeg, 'foto_bloqueada.jpg', 'image/jpeg')
        }
        resposta_bloqueada = self.client.post('/api/importar_manifesto_ocr', data=payload_bloqueado)
        self.assertEqual(resposta_bloqueada.status_code, 429)
