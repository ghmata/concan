"""
Módulo de Parser de Texto de OCR — ConCAN
Arquivo: src/ocr_parser.py

Extrai dados de manifesto e volumes a partir de texto bruto gerado por OCR (Tesseract.js).
Implementa tolerância a falhas e ruídos típicos de reconhecimento ótico de caracteres.
"""

import re
from typing import List, Dict, Tuple

class OCRManifestoParser:
    """Classe responsável por analisar texto bruto de OCR e extrair informações estruturadas."""

    def __init__(self, texto: str):
        self.texto = texto
        self.dados_manifesto = {}
        self.volumes = []

    def parse(self) -> Tuple[Dict, List[Dict], List[str]]:
        """
        Processa o texto bruto de OCR.
        Retorna uma tupla: (dados_cabecalho, lista_volumes, lista_erros)
        """
        erros = []
        
        # 1. Extrair Dados do Cabeçalho
        self.dados_manifesto = self._extrair_cabecalho()
        
        # 2. Extrair Volumes
        self.volumes = self._extrair_volumes()

        if not self.dados_manifesto.get('numero_manifesto'):
            erros.append("Número do manifesto não identificado no texto do OCR.")

        return self.dados_manifesto, self.volumes, erros

    def _padronizar_remetente(self, remetente: str) -> str:
        """Padroniza o nome do remetente com base em palavras-chave conhecidas."""
        rem = remetente.upper().strip()
        regras = ['CABW', 'CABE', 'BACO', 'BACG', 'GAC-PAC', 'GACPAC', 'BAGL', 'CTLA', 'CLTA', 'BAAN', 'BASP', 'BANT']
        
        for palavra in regras:
            if palavra in rem:
                return palavra
        
        partes = rem.split()
        if partes:
            return partes[0]
        return rem

    def _e_destinatario_pamals(self, texto: str) -> bool:
        """Verifica se o texto contém alguma indicação de destinatário ser o PAMALS."""
        if not texto:
            return False
        t = texto.upper().strip()
        palavras_chave = ['PAMALS', 'PAMA-LS', 'PAMA LS', 'LAGOA SANTA', 'LS PAMA', 'PARQUE DE MATERIAL']
        for p in palavras_chave:
            if p in t:
                return True
        return False

    def _extrair_cabecalho(self) -> Dict:
        """Extrai informações gerais do cabeçalho do manifesto com regex tolerante a ruídos."""
        dados = {
            'numero_manifesto': None,
            'data_manifesto': None,
            'terminal_origem': None,
            'terminal_destino': None,
            'missao': None,
            'aeronave': None
        }

        # Busca número do manifesto: 12 dígitos isolados (que não fazem parte de um volume com barra)
        match = re.search(r'\b(\d{12})\b(?!\s*/\s*\d{4})', self.texto)
        if match:
            dados['numero_manifesto'] = match.group(1)
        else:
            # Fallback tolerando espaços entre os dígitos
            match_espacos = re.search(r'\b(\d{3}\s*\d{3}\s*\d{3}\s*\d{3})\b', self.texto)
            if match_espacos:
                numero_limpo = re.sub(r'\s+', '', match_espacos.group(1))
                if len(numero_limpo) == 12:
                    dados['numero_manifesto'] = numero_limpo

        # Terminal Origem (procura formatos como PCAN-DF, TCTL-LS etc.)
        match_origem = re.search(r'ORIGEM:\s*([A-Z\-0-9]+)', self.texto, re.IGNORECASE)
        if match_origem:
            dados['terminal_origem'] = match_origem.group(1).strip()
        else:
            matches_pcan = re.findall(r'((?:PCAN|TCTL)-[A-Z]{2})', self.texto)
            if matches_pcan:
                dados['terminal_origem'] = matches_pcan[0]

        # Terminal Destino
        match_destino = re.search(r'DESTINO:\s*([A-Z\-0-9]+)', self.texto, re.IGNORECASE)
        if match_destino:
            dados['terminal_destino'] = match_destino.group(1).strip()
        else:
            matches_pcan = re.findall(r'((?:PCAN|TCTL)-[A-Z]{2})', self.texto)
            if len(matches_pcan) >= 2:
                dados['terminal_destino'] = matches_pcan[1]

        # Missão
        match_missao = re.search(r'MISS[ÃA]O:\s*([A-Z0-9\s]+?)(?:\n|V\.)', self.texto, re.IGNORECASE)
        if match_missao:
            dados['missao'] = match_missao.group(1).strip()

        # Aeronave (e busca de padrões comuns)
        match_aeronave = re.search(r'AERONAVE:\s*([A-Z0-9\-]+)', self.texto, re.IGNORECASE)
        if match_aeronave:
            dados['aeronave'] = match_aeronave.group(1).strip()
        else:
            # Busca direta por modelos conhecidos
            modelos = ['C-105', 'C-130', 'KC-390', 'C-95', 'C-97', 'C-98', 'H-60', 'H-36']
            for mod in modelos:
                if mod in self.texto.upper():
                    dados['aeronave'] = mod
                    break

        return dados

    def _extrair_volumes(self) -> List[Dict]:
        """Extrai volumes identificados no texto do OCR."""
        volumes = []
        linhas = self.texto.split('\n')
        
        # Regex para identificar número do volume com ou sem hífen (ex: 240101010101/0001 ou 240101010101/0001-0004)
        padrao_volume = re.compile(r'(\d{12})\s*/\s*(\d{4})(?:\s*-\s*(\d{4}))?')
        
        for linha in linhas:
            # Ignora linhas de cabeçalhos evidentes
            if any(p in linha.upper() for p in ['MANIFESTO', 'PÁGINA', 'TOTAIS', 'ENTREGUE', 'RECEBIDO']):
                continue
                
            match = padrao_volume.search(linha)
            if match:
                man_id_vol = match.group(1)
                num_seq = match.group(2)
                num_fim = match.group(3)
                
                # Monta a string do volume no padrão correto sem espaços
                if num_fim:
                    numero_volume = f"{man_id_vol}/{num_seq}-{num_fim}"
                else:
                    numero_volume = f"{man_id_vol}/{num_seq}"
                
                partes = linha.split()
                if len(partes) < 2:
                    continue

                remetente = "DESCONHECIDO"
                destinatario = "PAMALS" # Padrão no ConCAN
                quantidade_exp = 1
                peso = 0.0
                cubagem = 0.0
                prioridade = "00"
                tipo_material = "Geral"

                # 1. Identificar Remetente
                # Varre a linha para ver se contém alguma das siglas de remetentes conhecidos
                for p in partes:
                    sigla = self._padronizar_remetente(p)
                    if sigla in ['CABW', 'CABE', 'BACO', 'BACG', 'BAGL', 'CTLA', 'CLTA', 'BAAN', 'BASP', 'BANT']:
                        remetente = sigla
                        break

                # 2. Identificar Quantidade Expedida
                # Procura por números inteiros após a identificação do volume
                tokens_apos_vol = []
                encontrou_vol = False
                for token in partes:
                    if re.search(r'\d{12}/\d{4}', token) or '/' in token:
                        encontrou_vol = True
                        continue
                    if encontrou_vol:
                        tokens_apos_vol.append(token)

                # Busca quantidade (geralmente um inteiro isolado e curto)
                for t in tokens_apos_vol:
                    if re.match(r'^\d+$', t) and len(t) <= 3:
                        quantidade_exp = int(t)
                        break

                # 3. Identificar Peso e Cubagem
                valores_decimais = []
                for t in tokens_apos_vol:
                    if re.match(r'^\d+[,\.]\d+$', t):
                        valores_decimais.append(float(t.replace(',', '.')))
                
                if len(valores_decimais) >= 1:
                    peso = valores_decimais[0]
                if len(valores_decimais) >= 2:
                    cubagem = valores_decimais[1]

                # 4. Prioridade
                # Geralmente o último número de 2 dígitos na linha
                for t in reversed(partes):
                    if re.match(r'^\d{2}$', t):
                        prioridade = t
                        break

                # 5. Tipo Material
                if 'AERON' in linha.upper():
                    tipo_material = 'Aeronáutico'
                elif 'GÁS' in linha.upper() or 'GAS' in linha.upper():
                    tipo_material = 'Gás Comprimido'

                # No ConCAN, filtramos volumes cujo destinatário é o PAMALS.
                # Como no OCR as palavras podem vir truncadas, se a linha tiver qualquer indício de ser do PAMALS
                # ou se a busca geral de destinatário for favorável, adicionamos.
                # Para evitar falsos negativos severos que impeçam a importação de volumes válidos,
                # assumiremos destinatário PAMALS por padrão se o formato do volume bater,
                # deixando que a revisão humana confirme ou descarte o volume.
                volumes.append({
                    'remetente': remetente,
                    'destinatario': destinatario,
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

def parse_ocr_text(texto: str) -> Tuple[Dict, List[Dict], List[str]]:
    """Função de conveniência para instanciar o parser e extrair os dados."""
    parser = OCRManifestoParser(texto)
    return parser.parse()
