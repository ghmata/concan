"""
Script de verificação de segurança antes do commit
Execute este script antes de fazer push para o GitHub
"""

import os
import sys
from pathlib import Path

def verificar_arquivo_existe(caminho, deve_existir=True):
    """Verifica se um arquivo existe ou não existe"""
    existe = Path(caminho).exists()
    if deve_existir:
        return existe, f"✅ {caminho} encontrado" if existe else f"❌ {caminho} NÃO encontrado"
    else:
        return not existe, f"✅ {caminho} não será commitado" if not existe else f"⚠️  {caminho} SERÁ commitado (PERIGO!)"

def verificar_conteudo_arquivo(caminho, termos_proibidos):
    """Verifica se um arquivo contém termos sensíveis"""
    if not Path(caminho).exists():
        return True, f"⏭️  {caminho} não existe, pulando verificação"
    
    try:
        with open(caminho, 'r', encoding='utf-8') as f:
            conteudo = f.read()
            
        encontrados = []
        for termo in termos_proibidos:
            if termo in conteudo and not termo.startswith('os.getenv'):
                encontrados.append(termo)
        
        if encontrados:
            return False, f"❌ {caminho} contém valores hardcoded: {', '.join(encontrados)}"
        return True, f"✅ {caminho} não contém valores hardcoded"
    except Exception as e:
        return False, f"⚠️  Erro ao verificar {caminho}: {e}"

def main():
    print("=" * 60)
    print("🔒 VERIFICAÇÃO DE SEGURANÇA PARA GITHUB")
    print("=" * 60)
    print()
    
    problemas = []
    avisos = []
    
    # 1. Verificar arquivos de configuração
    print("📁 Verificando arquivos de configuração...")
    checks = [
        (".gitignore", True),
        (".env.example", True),
        ("README.md", True),
        ("credentials.json.example", True),
    ]
    
    for arquivo, deve_existir in checks:
        ok, msg = verificar_arquivo_existe(arquivo, deve_existir)
        print(f"  {msg}")
        if not ok:
            problemas.append(msg)
    print()
    
    # 2. Verificar arquivos sensíveis (NÃO devem existir no Git)
    print("🔐 Verificando arquivos sensíveis...")
    arquivos_sensiveis = [
        ".env",
        "credentials.json",
        "data/database.db",
    ]
    
    for arquivo in arquivos_sensiveis:
        # Verifica se o arquivo existe localmente (ok) mas não será commitado
        if Path(arquivo).exists():
            print(f"  ℹ️  {arquivo} existe localmente (OK)")
        else:
            print(f"  ⚠️  {arquivo} não existe localmente")
    print()
    
    # 3. Verificar se há valores hardcoded no código
    print("🔍 Verificando código por valores hardcoded...")
    
    arquivos_codigo = [
        ("app.py", [
            '"chave_secreta_can_mobile_v2"',
            '"pitaco"',
        ]),
        ("criar_admin.py", [
            "'admin123'",
            "'1234'",
        ]),
        ("src/sheets_sync.py", [
            '"12WhWOgfWEzgy6nmpf0NVPHYL8mZsl3NH9fzuMrmErlc"',
        ]),
    ]
    
    for arquivo, termos in arquivos_codigo:
        ok, msg = verificar_conteudo_arquivo(arquivo, termos)
        print(f"  {msg}")
        if not ok:
            avisos.append(msg)
    print()
    
    # 4. Verificar .gitignore
    print("📋 Verificando .gitignore...")
    if Path(".gitignore").exists():
        with open(".gitignore", 'r', encoding='utf-8') as f:
            gitignore_content = f.read()
        
        itens_obrigatorios = [
            ".env",
            "credentials.json",
            "*.db",
            "__pycache__",
        ]
        
        for item in itens_obrigatorios:
            if item in gitignore_content:
                print(f"  ✅ {item} está no .gitignore")
            else:
                msg = f"❌ {item} NÃO está no .gitignore"
                print(f"  {msg}")
                problemas.append(msg)
    else:
        msg = "❌ .gitignore não encontrado!"
        print(f"  {msg}")
        problemas.append(msg)
    print()
    
    # 5. Verificar dependências
    print("📦 Verificando dependências...")
    if Path("requirements.txt").exists():
        with open("requirements.txt", 'r', encoding='utf-8') as f:
            deps = f.read()
        
        deps_obrigatorias = ["python-dotenv", "Flask", "gspread"]
        for dep in deps_obrigatorias:
            if dep in deps:
                print(f"  ✅ {dep} está no requirements.txt")
            else:
                msg = f"⚠️  {dep} não está no requirements.txt"
                print(f"  {msg}")
                avisos.append(msg)
    print()
    
    # Resumo
    print("=" * 60)
    print("📊 RESUMO")
    print("=" * 60)
    
    if not problemas and not avisos:
        print("✅ TUDO OK! Projeto pronto para ser publicado no GitHub!")
        print()
        print("Próximos passos:")
        print("  1. git add .")
        print("  2. git status (verifique os arquivos)")
        print("  3. git commit -m 'Initial commit'")
        print("  4. git push")
        return 0
    
    if problemas:
        print(f"\n❌ {len(problemas)} PROBLEMA(S) CRÍTICO(S) ENCONTRADO(S):")
        for p in problemas:
            print(f"  • {p}")
        print("\n⚠️  NÃO FAÇA PUSH ATÉ RESOLVER ESTES PROBLEMAS!")
    
    if avisos:
        print(f"\n⚠️  {len(avisos)} AVISO(S):")
        for a in avisos:
            print(f"  • {a}")
        print("\nVerifique se os valores estão usando variáveis de ambiente.")
    
    print()
    return 1 if problemas else 0

if __name__ == "__main__":
    sys.exit(main())
