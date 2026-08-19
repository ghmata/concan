"""
Teste de Integração da FASE 5 — Expansion ConCAN
Verifica:
- Soft-delete por seção (R23)
- Extramanifesto isolado por seção (R26)
- Rastreabilidade cruzada de logs (R06)
"""
import sys
import os
import unittest
from pathlib import Path

# Ajustar caminho para os módulos do projeto
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR / "src"))
sys.path.append(str(BASE_DIR))

import database as db

class TestFase5(unittest.TestCase):
    def setUp(self):
        db.init_database()
        self.conn = db.get_connection()
        self.cursor = self.conn.cursor()
        
        # Limpar dados de teste prévios
        self.cursor.execute("DELETE FROM logs WHERE usuario LIKE 'TEST_FASE5%'")
        self.cursor.execute("DELETE FROM manifesto_secao WHERE manifesto_id IN (SELECT id FROM manifestos WHERE numero_manifesto LIKE 'F5%')")
        self.cursor.execute("DELETE FROM volume_observacoes WHERE volume_id IN (SELECT id FROM volumes WHERE manifesto_id IN (SELECT id FROM manifestos WHERE numero_manifesto LIKE 'F5%'))")
        self.cursor.execute("DELETE FROM conferencia_caixa WHERE volume_id IN (SELECT id FROM volumes WHERE manifesto_id IN (SELECT id FROM manifestos WHERE numero_manifesto LIKE 'F5%'))")
        self.cursor.execute("DELETE FROM conferencia_volume WHERE volume_id IN (SELECT id FROM volumes WHERE manifesto_id IN (SELECT id FROM manifestos WHERE numero_manifesto LIKE 'F5%'))")
        self.cursor.execute("DELETE FROM caixas_individuais WHERE volume_id IN (SELECT id FROM volumes WHERE manifesto_id IN (SELECT id FROM manifestos WHERE numero_manifesto LIKE 'F5%'))")
        self.cursor.execute("DELETE FROM volumes WHERE manifesto_id IN (SELECT id FROM manifestos WHERE numero_manifesto LIKE 'F5%')")
        self.cursor.execute("DELETE FROM manifestos WHERE numero_manifesto LIKE 'F5%'")
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def test_soft_delete_por_secao(self):
        """R23: Exclusão de manifesto é soft-delete por seção (Opção A)"""
        mid = db.criar_manifesto(
            numero="F50000000001",
            data="11/08/2026",
            origem_terminal="SBGL",
            destino="SBLS",
            missao="TESTE_F5",
            aeronave="C-105",
            pdf_path="/dummy/path",
            usuario="TEST_FASE5_USER",
            secao_origem="TSRE"
        )
        
        db.adicionar_volume(mid, "REMETENTE_1", "PAMALS", "F50000000001/0001", 1, secao_origem="TSRE")
        
        # Verificar que o manifesto aparece em ambas as seções inicialmente
        tsre_list = db.listar_manifestos(secao='TSRE')
        can_list = db.listar_manifestos(secao='CAN')
        
        self.assertTrue(any(m['id'] == mid for m in tsre_list), "Manifesto deve aparecer na TSRE")
        self.assertTrue(any(m['id'] == mid for m in can_list), "Manifesto deve aparecer no CAN")
        
        # 1. TSRE exclui o manifesto
        res = db.excluir_manifesto_secao(mid, 'TSRE', usuario="TEST_FASE5_ADMIN_TSRE")
        self.assertTrue(res, "Exclusão por seção deve retornar True")
        
        # 2. Verificar que sumiu da TSRE, mas CONTINUA no CAN
        tsre_list_pos = db.listar_manifestos(secao='TSRE')
        can_list_pos = db.listar_manifestos(secao='CAN')
        
        self.assertFalse(any(m['id'] == mid for m in tsre_list_pos), "Manifesto DEVE ter sumido da TSRE")
        self.assertTrue(any(m['id'] == mid for m in can_list_pos), "Manifesto DEVE continuar visível no CAN")
        
        # 3. CAN exclui o manifesto
        res_can = db.excluir_manifesto_secao(mid, 'CAN', usuario="TEST_FASE5_ADMIN_CAN")
        self.assertTrue(res_can)
        
        can_list_final = db.listar_manifestos(secao='CAN')
        self.assertFalse(any(m['id'] == mid for m in can_list_final), "Manifesto DEVE ter sumido também do CAN")

    def test_extramanifesto_isolado(self):
        """R26: Extramanifesto gravado com secao_extra e permissões isoladas + filtro por destino_extra"""
        mid = db.criar_manifesto(
            numero="F50000000002",
            data="11/08/2026",
            origem_terminal="SBGL",
            destino="SBLS",
            missao="TESTE_F5_EXTRA",
            aeronave="C-130",
            pdf_path="/dummy/path2",
            usuario="TEST_FASE5_USER",
            secao_origem="CAN"
        )
        
        # Volume normal CAN (não PAMALS)
        vid_norm = db.adicionar_volume(mid, "REM_NORMAL", "PAMA-SP", "F50000000002/0001", 1, secao_origem="CAN")
        
        # Volume EXTRA CAN com destino PAMA-LS → deve aparecer na TSRE
        vid_extra_can_pamals = db.adicionar_volume(
            mid, "REM_EXTRA_CAN_PAMALS", "PAMALS", "F50000000002/9001", 1,
            secao_origem="CAN", prioridade="EXTRA", secao_extra="CAN", destino_extra="PAMA-LS"
        )

        # Volume EXTRA CAN com destino OUTRO → NÃO deve aparecer na TSRE
        vid_extra_can_outro = db.adicionar_volume(
            mid, "REM_EXTRA_CAN_OUTRO", "PAMA-SP", "F50000000002/9002", 1,
            secao_origem="CAN", prioridade="EXTRA", secao_extra="CAN", destino_extra="OUTRO:PAMA-SP"
        )
        
        # Volume EXTRA adicionado pela TSRE (aparece sempre na TSRE)
        vid_extra_tsre = db.adicionar_volume(
            mid, "REM_EXTRA_TSRE", "PAMALS", "F50000000002/9003", 1,
            secao_origem="TSRE", prioridade="EXTRA", secao_extra="TSRE"
        )
        
        vols_tsre = db.listar_volumes_detalhado(mid, secao='TSRE')
        vols_can = db.listar_volumes_detalhado(mid, secao='CAN')
        
        # Extra CAN com PAMA-LS → deve aparecer na TSRE e TSRE PODE operar/receber
        vol_can_pamals_em_tsre = next((v for v in vols_tsre if v['id'] == vid_extra_can_pamals), None)
        self.assertIsNotNone(vol_can_pamals_em_tsre, "TSRE deve visualizar o volume extra do CAN com destino PAMA-LS")
        self.assertTrue(vol_can_pamals_em_tsre['pode_operar'], "TSRE PODE operar/receber no volume extra do CAN destinado ao PAMA-LS")
        
        # Extra CAN com OUTRO → NÃO deve aparecer na TSRE
        vol_can_outro_em_tsre = next((v for v in vols_tsre if v['id'] == vid_extra_can_outro), None)
        self.assertIsNone(vol_can_outro_em_tsre, "TSRE NÃO deve visualizar volume extra do CAN com destino OUTRO")
        
        # Extra TSRE → deve aparecer na TSRE (e TSRE pode operar)
        vol_tsre_em_tsre = next((v for v in vols_tsre if v['id'] == vid_extra_tsre), None)
        self.assertIsNotNone(vol_tsre_em_tsre, "TSRE deve visualizar seu próprio volume extra")
        self.assertTrue(vol_tsre_em_tsre['pode_operar'], "TSRE PODE operar em seu próprio volume extra")
        
        # CAN vê todos os seus volumes extras (PAMA-LS e OUTRO)
        vol_can_pamals_em_can = next((v for v in vols_can if v['id'] == vid_extra_can_pamals), None)
        vol_can_outro_em_can = next((v for v in vols_can if v['id'] == vid_extra_can_outro), None)
        vol_tsre_em_can = next((v for v in vols_can if v['id'] == vid_extra_tsre), None)
        
        self.assertIsNotNone(vol_can_pamals_em_can, "CAN deve visualizar seu volume extra com destino PAMA-LS")
        self.assertTrue(vol_can_pamals_em_can['pode_operar'], "CAN PODE operar em seu próprio volume extra PAMA-LS")

        self.assertIsNotNone(vol_can_outro_em_can, "CAN deve visualizar seu volume extra com destino OUTRO")
        self.assertTrue(vol_can_outro_em_can['pode_operar'], "CAN PODE operar em seu próprio volume extra OUTRO")
        
        self.assertIsNotNone(vol_tsre_em_can, "CAN deve visualizar o volume extra da TSRE")
        self.assertFalse(vol_tsre_em_can['pode_operar'], "CAN NÃO pode operar no volume extra da TSRE")

    def test_rastreabilidade_logs(self):
        """R06: Logs imutáveis com filtro por seção e consulta imutável"""
        mid = db.criar_manifesto(
            numero="F50000000003",
            data="11/08/2026",
            origem_terminal="SBGL",
            destino="SBLS",
            missao="TESTE_F5_LOGS",
            aeronave="KC-390",
            pdf_path="/dummy/path3",
            usuario="TEST_FASE5_USER",
            secao_origem="TSRE"
        )
        
        # Registrar ação manual da TSRE e do CAN
        self.cursor.execute("""
            INSERT INTO logs (manifesto_id, acao, usuario, secao)
            VALUES (?, 'ACAO_TESTE_TSRE', 'OPERADOR_TSRE_1', 'TSRE')
        """, (mid,))
        self.cursor.execute("""
            INSERT INTO logs (manifesto_id, acao, usuario, secao)
            VALUES (?, 'ACAO_TESTE_CAN', 'OPERADOR_CAN_1', 'CAN')
        """, (mid,))
        self.conn.commit()
        
        todos_logs = db.listar_logs(mid)
        tsre_logs = db.listar_logs(mid, secao='TSRE')
        can_logs = db.listar_logs(mid, secao='CAN')
        
        self.assertTrue(len(todos_logs) >= 2, "Deve retornar logs de ambas as seções")
        self.assertTrue(all(l['secao'] == 'TSRE' for l in tsre_logs), "Filtro TSRE deve retornar apenas logs TSRE")
        self.assertTrue(all(l['secao'] == 'CAN' for l in can_logs), "Filtro CAN deve retornar apenas logs CAN")

    def test_excluir_e_reincluir_manifesto(self):
        """MANTENDO A SEPARAÇÃO: Exclusão total quando ambas as seções excluem e capacidade de reinclusão limpa"""
        num_man = "F50000000099"
        mid = db.criar_manifesto(
            numero=num_man, data="11/08/2026", origem_terminal="SBGL",
            destino="SBLS", missao="TESTE_REINCLUSAO", aeronave="C-105",
            pdf_path="/dummy/path99", usuario="TEST_FASE5_USER", secao_origem="TSRE"
        )
        db.adicionar_volume(mid, "REM99", "PAMALS", f"{num_man}/0001", 1, secao_origem="TSRE")
        
        # 1. TSRE exclui
        db.excluir_manifesto_secao(mid, 'TSRE', usuario="ADMIN_TSRE")
        
        # TSRE tenta obter por numero -> deve retornar None (não está ativo para TSRE)
        man_tsre = db.obter_manifesto_por_numero(num_man, secao='TSRE')
        self.assertIsNone(man_tsre, "Manifesto não deve aparecer como ativo para a TSRE")
        
        # 2. CAN exclui -> como era a última seção ativa, deve fazer Hard Delete no banco
        db.excluir_manifesto_secao(mid, 'CAN', usuario="ADMIN_CAN")
        
        man_banco = db.obter_manifesto_por_numero(num_man)
        self.assertIsNone(man_banco, "Manifesto deve ter sido completamente removido do banco")

        # 3. Reincluir o mesmo número de manifesto deve funcionar sem qualquer erro de duplicação
        novo_mid = db.criar_manifesto(
            numero=num_man, data="11/08/2026", origem_terminal="SBGL",
            destino="SBLS", missao="TESTE_REINCLUIR_SUCESSO", aeronave="C-105",
            pdf_path="/dummy/path99_novo", usuario="TEST_FASE5_USER", secao_origem="TSRE"
        )
        self.assertIsNotNone(novo_mid, "Deve permitir a reinclusão limpa do manifesto")
        
        man_reincluido = db.obter_manifesto_por_numero(num_man, secao='TSRE')
        self.assertIsNotNone(man_reincluido, "Manifesto reincluído deve estar visível e ativo para a TSRE")

    def test_busca_isolada_por_secao(self):
        """Valida que a busca em cada seção retorna estritamente os status e conferentes daquela seção"""
        num_man = "F50000000088"
        mid = db.criar_manifesto(
            numero=num_man, data="11/08/2026", origem_terminal="SBGL",
            destino="SBLS", missao="TESTE_BUSCA_SECAO", aeronave="C-130",
            pdf_path="/dummy/path88", usuario="TEST_FASE5_USER", secao_origem="TSRE"
        )
        vid = db.adicionar_volume(mid, "REM88", "PAMALS", f"{num_man}/0001", 1, secao_origem="TSRE")
        
        # CAN recebe a caixa 1 do volume
        db.marcar_caixa_recebida_web(vid, 1, usuario="CONFERENTE_CAN_88", secao="CAN")
        
        # 1. Busca na seção CAN: deve indicar RECEBIDO / COMPLETO e conferente CAN
        res_can = db.buscar_volumes_geral(f"{num_man}/0001", secao='CAN')
        self.assertEqual(len(res_can), 1)
        vol_can = res_can[0]
        self.assertIn(vol_can['status'], ['COMPLETO', 'RECEBIDA', 'TOTALMENTE RECEBIDO'])
        self.assertIn('CONFERENTE_CAN_88', vol_can['usuario_recepcao'])
        
        # 2. Busca na seção TSRE: deve indicar PENDENTE e conferente '-' (TSRE ainda não recebeu)
        res_tsre = db.buscar_volumes_geral(f"{num_man}/0001", secao='TSRE')
        self.assertEqual(len(res_tsre), 1)
        vol_tsre = res_tsre[0]
        self.assertEqual(vol_tsre['status'], 'PENDENTE')
        self.assertEqual(vol_tsre['usuario_recepcao'], '-')


if __name__ == '__main__':
    unittest.main()
