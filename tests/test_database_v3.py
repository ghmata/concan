"""
Testes Unitarios - ConCAN v3
Arquivo: tests/test_database_v3.py

Cobre:
- REQ-01: Status especial (RETIRADO POR OUTRA PESSOA)
- REQ-02: Rastreabilidade individual de conferentes por caixa
- REQ-03: Timestamps BRT
- Auditoria (logs)
"""
import unittest
import sqlite3
import os
import sys
import json
from pathlib import Path

# Ajustar path para importar modulos src
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

# Override DB_PATH para banco de teste in-memory
import database
TEST_DB = Path(__file__).parent / "test_database.db"
database.DB_PATH = TEST_DB
# Desabilitar sheets para testes com um Mock
class MockSheets:
    def sincronizar_manifesto(self, *args, **kwargs): pass
    def sincronizar_volume(self, *args, **kwargs): pass
    def atualizar_status_cabecalho(self, *args, **kwargs): pass
    def agendar_tarefa(self, func, *args): pass

database.SHEETS_ENABLED = True
database.sheets = MockSheets()

from database import (
    init_database, get_connection,
    criar_manifesto, adicionar_volume,
    marcar_recebido_web, marcar_caixa_recebida_web,
    desfazer_recebimento_web, desfazer_caixa_web,
    obter_caixas_por_volume, obter_manifesto,
    listar_volumes_detalhado,
    marcar_status_especial_caixa, marcar_status_especial_volume,
    receber_todos_volumes_web,
)


class TestBase(unittest.TestCase):
    """Base class que recria o banco antes de cada teste."""

    def setUp(self):
        init_database()
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM logs")
            cursor.execute("DELETE FROM caixas_individuais")
            cursor.execute("DELETE FROM volumes")
            cursor.execute("DELETE FROM manifestos")
            cursor.execute("DELETE FROM users")
            cursor.execute("DELETE FROM volume_observacoes")
            cursor.execute("DELETE FROM historico_edicoes_extra")
            cursor.execute("DELETE FROM sqlite_sequence")
            conn.commit()
        except sqlite3.OperationalError:
            pass
        finally:
            conn.close()

        # Criar manifesto de teste
        self.mid = criar_manifesto("MAN-TEST-001", "09/07/2026", "ORIG", "DEST", "M001", "A001", None)

    def tearDown(self):
        pass

    def _criar_volume(self, qtd_caixas=4, num="VOL-001"):
        return adicionar_volume(self.mid, "REMETENTE_A", "DEST_A", num, qtd_caixas)


class TestREQ02ConferenteIndividual(TestBase):
    """REQ-02: Rastreabilidade individual de conferentes por caixa."""

    def test_caixa_individual_preserva_conferente(self):
        """Cada caixa deve manter seu conferente original."""
        vid = self._criar_volume(4)

        # Usuario A recebe caixas 1, 2, 3
        marcar_caixa_recebida_web(vid, 1, "USUARIO_A")
        marcar_caixa_recebida_web(vid, 2, "USUARIO_A")
        marcar_caixa_recebida_web(vid, 3, "USUARIO_A")

        # Usuario B recebe caixa 4
        marcar_caixa_recebida_web(vid, 4, "USUARIO_B")

        caixas = obter_caixas_por_volume(vid)
        conferentes = {c['numero_caixa']: c['usuario_conferente'] for c in caixas}

        self.assertEqual(conferentes[1], "USUARIO_A")
        self.assertEqual(conferentes[2], "USUARIO_A")
        self.assertEqual(conferentes[3], "USUARIO_A")
        self.assertEqual(conferentes[4], "USUARIO_B")

    def test_receber_tudo_nao_sobrescreve_conferente(self):
        """marcar_recebido_web nao deve sobrescrever caixas ja recebidas."""
        vid = self._criar_volume(4)

        # Usuario A recebe caixa 1
        marcar_caixa_recebida_web(vid, 1, "USUARIO_A")

        # Usuario B clica "Receber Tudo"
        marcar_recebido_web(vid, "USUARIO_B")

        caixas = obter_caixas_por_volume(vid)
        conferentes = {c['numero_caixa']: c['usuario_conferente'] for c in caixas}

        # Caixa 1 deve manter USUARIO_A
        self.assertEqual(conferentes[1], "USUARIO_A")
        # Caixas 2-4 devem ser USUARIO_B
        self.assertEqual(conferentes[2], "USUARIO_B")
        self.assertEqual(conferentes[3], "USUARIO_B")
        self.assertEqual(conferentes[4], "USUARIO_B")

    def test_receber_todos_volumes_nao_sobrescreve(self):
        """receber_todos_volumes_web nao deve sobrescrever caixas ja recebidas."""
        vid = self._criar_volume(3)

        # Usuario A recebe caixa 1
        marcar_caixa_recebida_web(vid, 1, "USUARIO_A")

        # Usuario B recebe todo o manifesto
        receber_todos_volumes_web(self.mid, "USUARIO_B")

        caixas = obter_caixas_por_volume(vid)
        conferentes = {c['numero_caixa']: c['usuario_conferente'] for c in caixas}

        self.assertEqual(conferentes[1], "USUARIO_A")
        self.assertEqual(conferentes[2], "USUARIO_B")
        self.assertEqual(conferentes[3], "USUARIO_B")


class TestREQ01StatusEspecial(TestBase):
    """REQ-01: Status RETIRADO POR OUTRA PESSOA e NaO RECEBIDO."""

    def test_marcar_caixa_retirada(self):
        """Marcar caixa individual como RETIRADO POR OUTRA PESSOA."""
        vid = self._criar_volume(2)

        resultado = marcar_status_especial_caixa(
            vid, 1, "RETIRADO POR OUTRA PESSOA",
            "OPERADOR_X", "Fulano de Tal"
        )
        self.assertTrue(resultado)

        caixas = obter_caixas_por_volume(vid)
        cx1 = next(c for c in caixas if c['numero_caixa'] == 1)
        self.assertEqual(cx1['status'], "RETIRADO POR OUTRA PESSOA")
        self.assertEqual(cx1['retirado_por'], "Fulano de Tal")

    def test_marcar_caixa_nao_recebida_com_motivo(self):
        """Marcar caixa individual como NÃO RECEBIDO com motivo obrigatório."""
        vid = self._criar_volume(2)
        resultado = marcar_status_especial_caixa(
            vid, 1, "NÃO RECEBIDO", "OPERADOR_X", None, "Avaria na embalagem"
        )
        self.assertTrue(resultado)
        caixas = obter_caixas_por_volume(vid)
        cx1 = next(c for c in caixas if c['numero_caixa'] == 1)
        self.assertEqual(cx1['status'], "NÃO RECEBIDA")
        self.assertEqual(cx1['motivo_nao_recebido'], "Avaria na embalagem")

    def test_marcar_volume_retirado(self):
        """Marcar volume inteiro como RETIRADO POR OUTRA PESSOA."""
        vid = self._criar_volume(3)

        resultado = marcar_status_especial_volume(
            vid, "RETIRADO POR OUTRA PESSOA",
            "OPERADOR_X", "Ciclano"
        )
        self.assertTrue(resultado)

        # Todas as caixas devem estar RETIRADO
        caixas = obter_caixas_por_volume(vid)
        for c in caixas:
            self.assertEqual(c['status'], "RETIRADO POR OUTRA PESSOA")
            self.assertEqual(c['retirado_por'], "Ciclano")

        # Volume deve estar RETIRADO
        volumes = listar_volumes_detalhado(self.mid)
        vol = next(v for v in volumes if v['id'] == vid)
        self.assertEqual(vol['status'], "RETIRADO POR OUTRA PESSOA")

    def test_desfazer_apos_retirado(self):
        """Desfazer deve limpar status RETIRADO e campos retirado_por."""
        vid = self._criar_volume(2)

        marcar_status_especial_caixa(
            vid, 1, "RETIRADO POR OUTRA PESSOA",
            "OPERADOR_X", "Fulano"
        )

        desfazer_caixa_web(vid, 1, "ADMIN")

        caixas = obter_caixas_por_volume(vid)
        cx1 = next(c for c in caixas if c['numero_caixa'] == 1)
        self.assertEqual(cx1['status'], "NÃO RECEBIDA")
        self.assertIsNone(cx1['retirado_por'])

    def test_volume_status_mix_recebido_retirado(self):
        """Volume com caixas RECEBIDA + RETIRADO deve ser PARCIAL ou COMPLETO."""
        vid = self._criar_volume(3)

        # Caixa 1 recebida
        marcar_caixa_recebida_web(vid, 1, "USUARIO_A")

        # Caixa 2 retirada
        marcar_status_especial_caixa(
            vid, 2, "RETIRADO POR OUTRA PESSOA",
            "OPERADOR_X", "Fulano"
        )

        # Volume deve ser PARCIAL (1 recebida + 1 retirada = 2/3 resolvidas)
        volumes = listar_volumes_detalhado(self.mid)
        vol = next(v for v in volumes if v['id'] == vid)
        self.assertEqual(vol['status'], "PARCIAL")


class TestAuditoria(TestBase):
    """Trilha de auditoria com estado anterior/posterior."""

    def test_log_receber_caixa(self):
        """Receber caixa deve gerar log com estado anterior e posterior."""
        vid = self._criar_volume(1)

        marcar_caixa_recebida_web(vid, 1, "OPERADOR_A")

        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM logs WHERE volume_id = ? AND acao = 'RECEBER_CAIXA'",
                (vid,)
            )
            log = cursor.fetchone()
            self.assertIsNotNone(log)
            self.assertEqual(log['usuario'], "OPERADOR_A")
            self.assertIsNotNone(log['timestamp_utc'])
            self.assertIsNotNone(log['timestamp_brt'])

            # Estado anterior deve mostrar NAO RECEBIDA
            ant = json.loads(log['estado_anterior'])
            self.assertEqual(ant['status'], "NÃO RECEBIDA")

            # Estado posterior deve mostrar RECEBIDA
            pos = json.loads(log['estado_posterior'])
            self.assertEqual(pos['status'], "RECEBIDA")
        finally:
            conn.close()

    def test_log_status_especial(self):
        """Status especial deve gerar log de auditoria."""
        vid = self._criar_volume(2)

        marcar_status_especial_caixa(
            vid, 1, "RETIRADO POR OUTRA PESSOA",
            "OPERADOR_X", "Fulano"
        )

        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM logs WHERE volume_id = ? AND acao LIKE 'STATUS_ESPECIAL%'",
                (vid,)
            )
            log = cursor.fetchone()
            self.assertIsNotNone(log)
            self.assertEqual(log['usuario'], "OPERADOR_X")
            self.assertEqual(log['caixa_numero'], 1)
        finally:
            conn.close()


class TestREQ03Timestamps(TestBase):
    """REQ-03: Timestamps em BRT."""

    def test_timestamp_brt_format(self):
        """Timestamps devem estar em formato ISO com offset -03:00."""
        vid = self._criar_volume(1)
        marcar_caixa_recebida_web(vid, 1, "OPERADOR_A")

        caixas = obter_caixas_por_volume(vid)
        ts = caixas[0]['data_hora_recepcao']
        self.assertIsNotNone(ts)
        # Deve conter offset BRT
        self.assertIn("-03:00", ts)


if __name__ == "__main__":
    unittest.main(verbosity=2)
