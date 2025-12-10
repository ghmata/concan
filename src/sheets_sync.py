"""
Módulo de Sincronização com Google Sheets (CORRIGIDO PARA WEB)
Arquivo: src/sheets_sync.py
"""

import gspread
from oauth2client.service_account import ServiceAccountCredentials
from pathlib import Path
import queue
import threading
import time
import random
import warnings
from datetime import datetime
import os
from dotenv import load_dotenv

# Carrega variáveis de ambiente
load_dotenv()

# Limpa avisos
warnings.filterwarnings("ignore", category=UserWarning, module="gspread")

# ================= CONFIGURAÇÃO =================
# ID da Planilha (configure no arquivo .env)
SPREADSHEET_ID = os.getenv('GOOGLE_SPREADSHEET_ID', '')
CREDENTIALS_FILE = Path(__file__).resolve().parent.parent / "credentials.json"

SCOPE = [   
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

# Cores Profissionais (Idênticas ao Desktop)
COLOR_HEADER_BG = {'red': 0.12, 'green': 0.3, 'blue': 0.47} # Azul Petróleo
COLOR_HEADER_FG = {'red': 1.0, 'green': 1.0, 'blue': 1.0}   # Branco
COLOR_BORDER = {'red': 0.0, 'green': 0.0, 'blue': 0.0}      # Preto

# ================= VARIÁVEIS GLOBAIS =================
_client_instance = None
_task_queue = queue.Queue()
_worker_running = False

def _get_client():
    global _client_instance
    if _client_instance is None:
        if not CREDENTIALS_FILE.exists():
            # Tenta procurar no diretório atual se falhar
            local_creds = Path("credentials.json")
            if local_creds.exists():
                creds = ServiceAccountCredentials.from_json_keyfile_name(str(local_creds), SCOPE)
            else:
                raise FileNotFoundError(f"Arquivo {CREDENTIALS_FILE} não encontrado!")
        else:
            creds = ServiceAccountCredentials.from_json_keyfile_name(str(CREDENTIALS_FILE), SCOPE)
            
        _client_instance = gspread.authorize(creds)
    return _client_instance

# --- SISTEMA ANTI-CRASH (RETRY) ---
def api_retry(func):
    """Decorator para retry com backoff exponencial."""
    def wrapper(*args, **kwargs):
        max_retries = 8
        base_delay = 2.0
        
        for i in range(max_retries):
            try:
                return func(*args, **kwargs)
            except gspread.exceptions.APIError as e:
                status = e.response.status_code
                if status in [429, 500, 502, 503]:
                    sleep_time = (base_delay * (2 ** i)) + (random.randint(0, 1000) / 1000)
                    print(f"[Sheets] Erro API {status}. Aguardando {sleep_time:.2f}s...")
                    time.sleep(sleep_time)
                    if i > 3: 
                        global _client_instance
                        _client_instance = None 
                else:
                    print(f"[Sheets] Erro API não tratável: {e}")
                    raise e
            except Exception as e:
                print(f"[Sheets] Erro de execução: {e}. Retentando...")
                # Se for erro de argumentos, não adianta retentar, mas vamos logar
                if "unexpected keyword" in str(e):
                     print("ERRO CRÍTICO DE SINTAXE GSPREAD - VERIFIQUE A VERSÃO")
                     raise e
                time.sleep(2)
        
        print(f"[Sheets] CRÍTICO: Falha definitiva em {func.__name__}.")
    return wrapper

# --- WORKER ---
def _worker():
    print("[Sheets] Worker iniciado.")
    while True:
        try:
            task_func, args = _task_queue.get()
            try:
                task_func(*args)
                time.sleep(1.5) # Pausa para respeitar limite da API
            except Exception as e:
                print(f"[Sheets Erro na Tarefa] {e}")
            finally:
                _task_queue.task_done()
        except Exception as e:
            time.sleep(1)

def iniciar_worker():
    global _worker_running
    if not _worker_running:
        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        _worker_running = True

def agendar_tarefa(func, *args):
    iniciar_worker()
    _task_queue.put((func, args))

# ================= UTILITÁRIOS DE LAYOUT =================

def _formatar_data(data_iso):
    if not data_iso: return "-"
    try:
        dt = datetime.fromisoformat(data_iso)
        return dt.strftime("%d/%m/%y %H:%M")
    except ValueError:
        return data_iso

@api_retry
def _get_or_create_worksheet(client, title):
    # Garante que temos o ID correto
    # Se SPREADSHEET_ID estiver vazio, vai dar erro. Certifique-se de preencher lá em cima.
    sh = client.open_by_key(SPREADSHEET_ID)
    try:
        return sh.worksheet(title)
    except gspread.WorksheetNotFound:
        return sh.add_worksheet(title=title, rows=50, cols=8)

@api_retry
def _definir_layout_colunas(ws):
    """
    Define as larguras das colunas.
    Força tamanhos específicos para garantir que nada seja cortado.
    """
    requests = []

    # 1. Auto-resize geral (como fallback)
    requests.append({
        "autoResizeDimensions": {
            "dimensions": {
                "sheetId": ws.id,
                "dimension": "COLUMNS",
                "startIndex": 0,
                "endIndex": 8 # Garante até a coluna H se precisar
            }
        }
    })

    # --- DEFINIÇÕES DE LARGURA FIXA (Para evitar cortes) ---
    
    # Coluna B (Index 1): Remetente -> 230px
    requests.append({
        "updateDimensionProperties": {
            "range": {
                "sheetId": ws.id,
                "dimension": "COLUMNS",
                "startIndex": 1,
                "endIndex": 2
            },
            "properties": {"pixelSize": 230},
            "fields": "pixelSize"
        }
    })

    # Coluna C (Index 2): Destinatário -> 200px
    requests.append({
        "updateDimensionProperties": {
            "range": {
                "sheetId": ws.id,
                "dimension": "COLUMNS",
                "startIndex": 2,
                "endIndex": 3
            },
            "properties": {"pixelSize": 200},
            "fields": "pixelSize"
        }
    })

    # Coluna D (Index 3): VOLUME -> 220px (CORREÇÃO AQUI)
    # Aumentado para caber o número inteiro (Ex: 251381004311/0001)
    requests.append({
        "updateDimensionProperties": {
            "range": {
                "sheetId": ws.id,
                "dimension": "COLUMNS",
                "startIndex": 3,
                "endIndex": 4
            },
            "properties": {"pixelSize": 220}, 
            "fields": "pixelSize"
        }
    })

    # Coluna F (Index 5): Data Recebimento -> 140px (Para caber DD/MM/YY HH:MM)
    requests.append({
        "updateDimensionProperties": {
            "range": {
                "sheetId": ws.id,
                "dimension": "COLUMNS",
                "startIndex": 5,
                "endIndex": 6
            },
            "properties": {"pixelSize": 140},
            "fields": "pixelSize"
        }
    })
    
    # 2. AUTO-RESIZE para 'Recebido Por' (Coluna G -> Index 6)
    # Isso garante tamanho variável baseado no tamanho do nome
    requests.append({
        "autoResizeDimensions": {
            "dimensions": {
                "sheetId": ws.id,
                "dimension": "COLUMNS",
                "startIndex": 6,  # Coluna G
                "endIndex": 7
            }
        }
    })

    # Envia tudo em um único comando batch para ser rápido
    ws.spreadsheet.batch_update({'requests': requests})

@api_retry
def sincronizar_manifesto(manifesto_dados: dict):
    client = _get_client()
    num_manifesto = manifesto_dados['numero_manifesto']
    ws = _get_or_create_worksheet(client, num_manifesto)
    
    ws.clear()
    
    status_inicial = manifesto_dados.get('status', 'NÃO RECEBIDO')

    headers = [
        [f"CONFERÊNCIA DE MANIFESTO: {num_manifesto}", "", "", "", "", "", ""],
        ["STATUS GERAL:", status_inicial, "", "", "", "", ""],
        ["STATUS", "REMETENTE", "DESTINATÁRIO", "VOLUME", "QTD", "RECEBIDO EM", "RECEBIDO POR"]
    ]
    
    # CORREÇÃO PRINCIPAL: Uso de argumentos posicionais (compatível com todas versões)
    ws.update('A1:G3', headers)
    
    ws.merge_cells('A1:G1')
    
    # Formatação do Título
    ws.format('A1:G1', {
        'textFormat': {'bold': True, 'fontSize': 14, 'foregroundColor': COLOR_HEADER_FG},
        'backgroundColor': COLOR_HEADER_BG,
        'horizontalAlignment': 'CENTER',
        'verticalAlignment': 'MIDDLE'
    })

    # Formatação do Status
    ws.format('A2', {'textFormat': {'bold': True}, 'horizontalAlignment': 'RIGHT'})
    ws.format('B2', {'textFormat': {'bold': True}, 'horizontalAlignment': 'CENTER'})
    
    # Formatação do Cabeçalho da Tabela
    ws.format('A3:G3', {
        'textFormat': {'bold': True, 'foregroundColor': {'red': 0.0, 'green': 0.0, 'blue': 0.0}},
        'backgroundColor': {'red': 0.9, 'green': 0.9, 'blue': 0.9},
        'horizontalAlignment': 'CENTER',
        'verticalAlignment': 'MIDDLE',
        'borders': {'top': {'style': 'SOLID'}, 'bottom': {'style': 'SOLID'}, 'left': {'style': 'SOLID'}, 'right': {'style': 'SOLID'}}
    })
    
    ws.freeze(rows=3)
    
    atualizar_status_cabecalho(num_manifesto, status_inicial)
    _definir_layout_colunas(ws)

@api_retry
def sincronizar_volume(numero_manifesto: str, volume_dados: dict):
    client = _get_client()
    sh = client.open_by_key(SPREADSHEET_ID)
    ws = sh.worksheet(numero_manifesto)
    
    qtd_str = f"{volume_dados.get('quantidade_recebida', 0)} / {volume_dados.get('quantidade_expedida', 1)}"
    status = volume_dados.get('status', 'NÃO RECEBIDO')
    data_rec = _formatar_data(volume_dados.get('data_hora_ultima_recepcao'))
    user_rec = volume_dados.get('usuario_recepcao', '') or "-"
    
    row_data = [
        status,
        volume_dados.get('remetente', ''),
        volume_dados.get('destinatario', ''),
        volume_dados.get('numero_volume', ''),
        qtd_str,
        data_rec,
        user_rec
    ]
    
    col_volumes = ws.col_values(4)
    target_row = None
    num_vol_busca = volume_dados.get('numero_volume', '')
    
    if num_vol_busca in col_volumes:
        target_row = col_volumes.index(num_vol_busca) + 1
        # CORREÇÃO: Argumentos posicionais
        ws.update(f'A{target_row}:G{target_row}', [row_data])
    else:
        ws.append_row(row_data)
        target_row = len(col_volumes) + 1 if col_volumes else 1
        # Ajuste se for a primeira linha pós cabeçalho
        if target_row <= 3: target_row = len(ws.col_values(1)) 

    atualizar_status_visual(ws, target_row, status)
    # Não chamamos _definir_layout_colunas aqui para ganhar performance, 
    # pois já foi definido na criação

@api_retry
def atualizar_status_cabecalho(numero_manifesto: str, novo_status: str):
    if hasattr(numero_manifesto, 'update'):
        ws = numero_manifesto
    else:
        client = _get_client()
        sh = client.open_by_key(SPREADSHEET_ID)
        ws = sh.worksheet(numero_manifesto)
    
    # CORREÇÃO: Argumentos posicionais
    ws.update('B2', [[novo_status]])
    
    bg_color = {'red': 1.0, 'green': 1.0, 'blue': 1.0}
    fg_color = {'red': 0.0, 'green': 0.0, 'blue': 0.0}
    
    if novo_status == 'TOTALMENTE RECEBIDO':
        bg_color = {'red': 0.3, 'green': 0.7, 'blue': 0.3}
        fg_color = {'red': 1.0, 'green': 1.0, 'blue': 1.0}
    elif novo_status == 'PARCIALMENTE RECEBIDO':
        bg_color = {'red': 1.0, 'green': 0.8, 'blue': 0.0}
    elif novo_status == 'NÃO RECEBIDO':
        bg_color = {'red': 0.9, 'green': 0.9, 'blue': 0.9}
    
    ws.format('B2', {
        'textFormat': {'bold': True, 'foregroundColor': fg_color},
        'backgroundColor': bg_color,
        'horizontalAlignment': 'CENTER',
        'verticalAlignment': 'MIDDLE',
        'borders': {'top': {'style': 'SOLID'}, 'bottom': {'style': 'SOLID'}, 'left': {'style': 'SOLID'}, 'right': {'style': 'SOLID'}}
    })

@api_retry
def atualizar_status_visual(worksheet, row_num, status):
    bg_color = {'red': 1.0, 'green': 1.0, 'blue': 1.0}
    
    if status in ['COMPLETO', 'TOTALMENTE RECEBIDO']:
        bg_color = {'red': 0.85, 'green': 0.95, 'blue': 0.85}
    elif status == 'PARCIAL':
        bg_color = {'red': 1.0, 'green': 0.98, 'blue': 0.85}
    elif status == 'VOLUME EXTRA':
        bg_color = {'red': 0.9, 'green': 0.85, 'blue': 1.0}
    elif status == 'NÃO RECEBIDO':
        bg_color = {'red': 1.0, 'green': 0.95, 'blue': 0.95}
    
    worksheet.format(f'A{row_num}:G{row_num}', {
        'backgroundColor': bg_color,
        'textFormat': {'bold': False, 'foregroundColor': {'red': 0.0, 'green': 0.0, 'blue': 0.0}},
        'horizontalAlignment': 'CENTER',
        'verticalAlignment': 'MIDDLE',
        'borders': {'top': {'style': 'SOLID'}, 'bottom': {'style': 'SOLID'}, 'left': {'style': 'SOLID'}, 'right': {'style': 'SOLID'}}
    })
    
    worksheet.format(f'A{row_num}', {'textFormat': {'bold': True}})
    worksheet.format(f'D{row_num}', {'textFormat': {'bold': True}})