"""
Sistema de Conferência de Manifestos - Extrator de PDF
Arquivo: src/pdf_extractor.py
"""

import re
import pdfplumber
from typing import List, Dict, Optional, Tuple
from pathlib import Path
from datetime import datetime

class ManifestoExtractor:
    """Classe para extrair dados de manifestos em PDF"""
    
    def __init__(self, pdf_path: str):
        self.pdf_path = Path(pdf_path)
        self.dados_manifesto = {}
        self.volumes = []
        
    def extrair(self) -> Tuple[Dict, List[Dict]]:
        """
        Extrai dados do manifesto
        Retorna: (dados_cabecalho, lista_volumes)
        """
        if not self.pdf_path.exists():
            raise FileNotFoundError(f"Arquivo não encontrado: {self.pdf_path}")
        
        with pdfplumber.open(self.pdf_path) as pdf:
            texto_completo = ""
            
            # Extrair texto de todas as páginas
            for pagina in pdf.pages:
                texto_completo += pagina.extract_text() + "\n"
            
            # Extrair dados do cabeçalho
            self.dados_manifesto = self._extrair_cabecalho(texto_completo)
            
            # Extrair volumes (destinatário PAMALS e variações)
            self.volumes = self._extrair_volumes(texto_completo)
        
        return self.dados_manifesto, self.volumes
    
    def _extrair_cabecalho(self, texto: str) -> Dict:
        """Extrai informações do cabeçalho do manifesto"""
        dados = {
            'numero_manifesto': None,
            'data_manifesto': None,
            'terminal_origem': None,
            'terminal_destino': None,
            'missao': None,
            'aeronave': None
        }
        
        # Número do manifesto
        match = re.search(r'Manifesto:\s*(?:Página\s*)?(\d{12})', texto, re.IGNORECASE)
        if match:
            dados['numero_manifesto'] = match.group(1)
        else:
            match = re.search(r'^(\d{12})', texto, re.MULTILINE)
            if match:
                dados['numero_manifesto'] = match.group(1)
        
        # Terminal Origem
        match = re.search(r'TERMINAL DE ORIGEM:\s*([A-Z\-]+)', texto, re.IGNORECASE)
        if match:
            dados['terminal_origem'] = match.group(1).strip()
        else:
            match = re.search(r'((?:PCAN|TCTL)-[A-Z]{2})', texto)
            if match:
                dados['terminal_origem'] = match.group(1)
        
        # Terminal Destino
        match = re.search(r'TERMINAL DE DESTINO:\s*([A-Z\-]+)', texto, re.IGNORECASE)
        if match:
            dados['terminal_destino'] = match.group(1).strip()
        else:
            matches = re.findall(r'((?:PCAN|TCTL)-[A-Z]{2})', texto)
            if len(matches) >= 2:
                dados['terminal_destino'] = matches[1]
        
        # Missão
        match = re.search(r'MISSÃO:\s*([A-Z0-9\s]+?)(?:\n|V\.)', texto, re.IGNORECASE)
        if match:
            dados['missao'] = match.group(1).strip()
        
        # Aeronave
        match = re.search(r'AERONAVE:\s*([A-Z0-9\-]+)', texto, re.IGNORECASE)
        if match:
            dados['aeronave'] = match.group(1).strip()
        
        return dados
    
    def _padronizar_remetente(self, remetente: str) -> str:
        """Padroniza o nome do remetente"""
        rem = remetente.upper().strip()
        regras = ['CABW', 'CABE', 'BACO', 'BACG', 'GAC-PAC', 'GACPAC', 'BAGL', 'CTLA', 'CLTA', 'BAAN', 'BASP', 'BANT']
        
        for palavra in regras:
            if palavra in rem:
                return palavra
        
        partes = rem.split()
        if partes: return partes[0]
        return rem
    
    def _e_destinatario_pamals(self, destinatario: str) -> bool:
        """
        Verifica se o destinatário é PAMALS ou suas variações.
        """
        if not destinatario: return False
        dest = destinatario.upper().strip()
        
        # Palavras-chave que indicam Lagoa Santa
        palavras_chave = ['PAMALS', 'PAMA-LS', 'PAMA LS', 'LAGOA SANTA', 'LS PAMA', 'PARQUE DE MATERIAL']
        
        for p in palavras_chave:
            if p in dest:
                return True
                
        return False
    
    def _extrair_volumes(self, texto: str) -> List[Dict]:
        volumes = []
        linhas = texto.split('\n')
        
        for i, linha in enumerate(linhas):
            # Ignora cabeçalhos
            if any(p in linha.upper() for p in ['MANIFESTO', 'PÁGINA', 'TOTAIS', 'ENTREGUE', 'RECEBIDO']):
                continue
            
            # Padrão: Volume XXX/XXXX
            if re.search(r'\d{12}/\d{4}', linha):
                partes = linha.split()
                if len(partes) < 3: continue
                
                remetente = None
                destinatario = None
                numero_volume = None
                peso = None
                cubagem = None
                quantidade_exp = 1
                prioridade = None
                tipo_material = None
                
                # Procura a coluna do número do volume
                for j, parte in enumerate(partes):
                    if re.match(r'\d{12}/\d{4}', parte):
                        numero_volume = parte
                        # Verifica se tem intervalo (ex: -0004)
                        if j < len(partes) - 1 and partes[j+1].startswith('-'):
                            numero_volume += partes[j+1]
                        
                        # --- 1. Extração de Quantidade ---
                        # Tenta achar um número inteiro isolado à direita
                        for k in range(j + 1, len(partes)):
                            token = partes[k]
                            if re.match(r'^\d+$', token) and not re.match(r'\d{12}', token):
                                # Evita confundir com prioridade (geralmente 2 digitos no final)
                                # A qtd geralmente vem antes do peso ou antes da prioridade
                                quantidade_exp = int(token)
                                break

                        # --- 2. Extração de Destinatário (Inteligente) ---
                        # O destinatário está à esquerda do número do volume.
                        # Pode ser "PAMALS", "PAMALS - PAMA", "PARQUE DE MATERIAL", etc.
                        # Vamos pegar os tokens anteriores e ver se algum contém as palavras-chave.
                        
                        if j > 0:
                            # Reconstrói uma string com os 4 tokens anteriores para análise
                            inicio_busca = max(0, j - 5)
                            texto_anterior = " ".join(partes[inicio_busca:j])
                            
                            # Verifica se é PAMALS
                            if self._e_destinatario_pamals(texto_anterior):
                                destinatario = "PAMALS"
                                
                                # Se achou PAMALS, o remetente é o que vem antes disso.
                                # Essa lógica é complexa pois o PDF pode quebrar palavras.
                                # Vamos assumir o primeiro token da linha como remetente se for PAMALS
                                if j > 1:
                                    # Pega tudo antes do j, remove o que parece ser destino
                                    # Simplificação: O remetente geralmente é o primeiro token da linha
                                    remetente_bruto = partes[0]
                                    if j > 1 and not self._e_destinatario_pamals(partes[0]):
                                         remetente_bruto = partes[0] + " " + partes[1]
                                    
                                    remetente = self._padronizar_remetente(remetente_bruto)
                            else:
                                # Não é PAMALS, ignora
                                destinatario = "OUTROS"

                        # --- 3. Peso e Cubagem ---
                        for m in range(j + 1, min(j + 8, len(partes))):
                            valor = partes[m]
                            if re.match(r'^\d+[,\.]\d+$', valor):
                                val_float = float(valor.replace(',', '.'))
                                if peso is None: peso = val_float
                                elif cubagem is None: cubagem = val_float

                        # --- 4. Outros ---
                        tipo_material = 'Geral'
                        if 'Aeronáutico' in linha: tipo_material = 'Aeronáutico'
                        elif 'Gás' in linha: tipo_material = 'Gás Comprimido'
                        
                        # A prioridade é geralmente o último número de 2 dígitos
                        for p in reversed(partes):
                            if re.match(r'^\d{2}$', p):
                                prioridade = p
                                break
                        
                        break # Sai do loop das partes
                
                # Validação Final
                if destinatario == "PAMALS" and numero_volume:
                    if not remetente: remetente = "DESCONHECIDO"
                    
                    volumes.append({
                        'remetente': remetente,
                        'destinatario': 'PAMALS',
                        'numero_volume': numero_volume,
                        'quantidade_expedida': quantidade_exp,
                        'quantidade_recebida': 0,
                        'peso_total': peso,
                        'cubagem': cubagem,
                        'prioridade': prioridade,
                        'tipo_material': tipo_material,
                        'embalagem': 'CAIXA'
                    })
        
        return volumes

# ==================== FUNÇÕES AUXILIARES ====================

def extrair_manifesto_pdf(pdf_path: str) -> Tuple[Dict, List[Dict], List[str]]:
    try:
        extractor = ManifestoExtractor(pdf_path)
        dados_manifesto, volumes = extractor.extrair()
        
        erros = []
        if not dados_manifesto.get('numero_manifesto'):
            erros.append("Número do manifesto não encontrado")
        
        return dados_manifesto, volumes, erros
    
    except Exception as e:
        # Retorna erro limpo para o app.py exibir
        print(f"Erro Extrator: {e}")
        return {}, [], [f"Erro ao processar PDF: {str(e)}"]