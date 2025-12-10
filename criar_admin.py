"""
Script para criar o primeiro usuário ADMIN
Rode isso UMA VEZ no console: python criar_admin.py
"""
import sys
import os
from dotenv import load_dotenv

# Carrega variáveis de ambiente
load_dotenv()

sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))
from database import init_database, criar_usuario

if __name__ == "__main__":
    print("--- INICIALIZANDO BANCO v2.0 ---")

    # 1. Cria as tabelas novas
    init_database()
    print("Tabelas criadas/atualizadas.")

    # 2. Cria o usuário Admin
    admin_user = os.getenv('ADMIN_USERNAME', 'admin')
    admin_pass = os.getenv('ADMIN_PASSWORD', 'admin123')
    admin_name = os.getenv('ADMIN_FULLNAME', 'Administrador Geral')
    
    if criar_usuario(admin_user, admin_pass, admin_name, 'admin'):
        print("\n✅ SUCESSO! Usuário ADMIN criado:")
        print(f"User: {admin_user}")
        print(f"Pass: {admin_pass}")
        print("\n⚠️  IMPORTANTE: Altere a senha após o primeiro login!")
    else:
        print(f"\n⚠️ O usuário '{admin_user}' já existe.")

    # 3. Cria um operador de teste (opcional)
    op_user = os.getenv('OPERADOR_USERNAME', 'operador')
    op_pass = os.getenv('OPERADOR_PASSWORD', '1234')
    op_name = os.getenv('OPERADOR_FULLNAME', 'Operador Padrão')
    
    if criar_usuario(op_user, op_pass, op_name, 'operador'):
        print(f"\n✅ Operador '{op_user}' / '{op_pass}' criado para testes.")
    else:
        print(f"\n⚠️ O usuário '{op_user}' já existe.")