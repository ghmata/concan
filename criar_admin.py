"""
Script para criar o primeiro usuário ADMIN
Rode isso UMA VEZ no console: python criar_admin.py
"""
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))
from database import init_database, criar_usuario

if __name__ == "__main__":
    print("--- INICIALIZANDO BANCO v2.0 ---")

    # 1. Cria as tabelas novas
    init_database()
    print("Tabelas criadas/atualizadas.")

    # 2. Cria o usuário Admin
    if criar_usuario('admin', 'admin123', 'Administrador Geral', 'admin'):
        print("\n✅ SUCESSO! Usuário criado:")
        print("User: admin")
        print("Pass: admin123")
    else:
        print("\n⚠️ O usuário 'admin' já existe.")

    # 3. Cria um operador de teste
    criar_usuario('operador', '1234', 'Operador Padrão', 'operador')
    print("Operador 'operador' / '1234' criado para testes.")