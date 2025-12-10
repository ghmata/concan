# Comandos Git - Passo a Passo

# ============================================
# ANTES DE COMEÇAR
# ============================================

# 1. Certifique-se de ter criado o arquivo .env
# 2. Instale a nova dependência:
pip install python-dotenv

# 3. Teste se a aplicação funciona:
python app.py

# 4. Execute o verificador de segurança:
python verificar_seguranca.py


# ============================================
# INICIALIZAR REPOSITÓRIO GIT
# ============================================

# Inicializar Git (se ainda não fez)
git init

# Configurar seu nome e email (se ainda não fez)
git config user.name "Seu Nome"
git config user.email "seu.email@exemplo.com"


# ============================================
# ADICIONAR ARQUIVOS
# ============================================

# Adicionar todos os arquivos (o .gitignore protegerá os sensíveis)
git add .

# OU adicionar arquivos específicos:
# git add .gitignore
# git add .env.example
# git add README.md
# git add app.py
# git add criar_admin.py
# git add requirements.txt
# git add src/
# git add templates/
# git add static/


# ============================================
# VERIFICAR O QUE SERÁ COMMITADO
# ============================================

# MUITO IMPORTANTE: Verifique os arquivos que serão commitados
git status

# Certifique-se de que NÃO aparecem:
# - .env
# - credentials.json
# - data/database.db
# - uploads/*.pdf

# Se algum arquivo sensível aparecer, adicione-o ao .gitignore!


# ============================================
# FAZER O PRIMEIRO COMMIT
# ============================================

git commit -m "Initial commit - Sistema CONCAN de Gestão de Manifestos

- Sistema de gestão de manifestos de carga aérea
- Importação automática de PDFs
- Sincronização com Google Sheets
- Sistema de autenticação com Flask-Login
- Interface responsiva com Bootstrap 5
- Busca avançada de volumes
- Gestão de usuários (admin)"


# ============================================
# CRIAR REPOSITÓRIO NO GITHUB
# ============================================

# 1. Acesse: https://github.com/new
# 2. Nome do repositório: concan (ou outro nome)
# 3. Descrição: Sistema de Gestão de Manifestos de Carga Aérea
# 4. Escolha: Privado ou Público
# 5. NÃO adicione README, .gitignore ou licença (já temos)
# 6. Clique em "Create repository"


# ============================================
# CONECTAR AO GITHUB
# ============================================

# Substitua SEU-USUARIO pelo seu username do GitHub
git remote add origin https://github.com/SEU-USUARIO/concan.git

# Renomear branch para main (se necessário)
git branch -M main

# Fazer push pela primeira vez
git push -u origin main


# ============================================
# COMANDOS ÚTEIS PARA O FUTURO
# ============================================

# Ver status dos arquivos
git status

# Ver histórico de commits
git log --oneline

# Adicionar mudanças
git add .

# Fazer commit
git commit -m "Descrição das mudanças"

# Enviar para o GitHub
git push

# Baixar mudanças do GitHub
git pull

# Ver diferenças antes de commitar
git diff

# Desfazer mudanças não commitadas
git checkout -- arquivo.py

# Ver branches
git branch

# Criar nova branch
git checkout -b nome-da-branch


# ============================================
# EXEMPLO DE WORKFLOW DIÁRIO
# ============================================

# 1. Fazer mudanças no código
# 2. Verificar o que mudou:
git status

# 3. Adicionar arquivos modificados:
git add .

# 4. Fazer commit:
git commit -m "Descrição clara do que foi alterado"

# 5. Enviar para o GitHub:
git push


# ============================================
# DICAS DE SEGURANÇA
# ============================================

# SEMPRE verifique antes de fazer push:
git status

# Se acidentalmente adicionar arquivo sensível:
git reset HEAD arquivo-sensivel.txt
git checkout -- arquivo-sensivel.txt

# Para remover arquivo que já foi commitado (mas não enviado):
git reset --soft HEAD~1

# Para ver o que está no último commit:
git show


# ============================================
# MENSAGENS DE COMMIT RECOMENDADAS
# ============================================

# Exemplos de boas mensagens de commit:
# - "Adiciona validação de formulário de login"
# - "Corrige bug na importação de PDFs"
# - "Melhora performance da sincronização com Sheets"
# - "Atualiza documentação do README"
# - "Adiciona testes para módulo de database"
# - "Refatora código de extração de PDF"


# ============================================
# ARQUIVO .gitignore
# ============================================

# O .gitignore já está configurado para proteger:
# - .env (configurações locais)
# - credentials.json (credenciais Google)
# - *.db (banco de dados)
# - uploads/*.pdf (arquivos enviados)
# - __pycache__/ (cache Python)

# Se precisar adicionar mais arquivos ao .gitignore:
# echo "nome-do-arquivo.txt" >> .gitignore


# ============================================
# TROUBLESHOOTING
# ============================================

# Se der erro de autenticação no GitHub:
# 1. Use Personal Access Token ao invés de senha
# 2. Gere em: https://github.com/settings/tokens
# 3. Use o token como senha ao fazer push

# Se quiser usar SSH ao invés de HTTPS:
# 1. Gere chave SSH: ssh-keygen -t ed25519 -C "seu.email@exemplo.com"
# 2. Adicione ao GitHub: https://github.com/settings/keys
# 3. Mude a URL: git remote set-url origin git@github.com:SEU-USUARIO/concan.git
