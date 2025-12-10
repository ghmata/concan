# 🔒 Guia de Preparação para GitHub

Este documento explica as mudanças feitas para tornar o projeto seguro para publicação no GitHub.

## ✅ O que foi feito

### 1. Arquivos de Segurança Criados

- **`.gitignore`**: Protege arquivos sensíveis de serem commitados
- **`.env.example`**: Documenta as variáveis de ambiente necessárias
- **`credentials.json.example`**: Exemplo da estrutura do arquivo de credenciais do Google

### 2. Código Atualizado

Todos os valores hardcoded foram substituídos por variáveis de ambiente:

#### `app.py`
- ✅ `app.secret_key` agora usa `FLASK_SECRET_KEY` do .env
- ✅ Senha de exclusão agora usa `ADMIN_DELETE_PASSWORD` do .env

#### `criar_admin.py`
- ✅ Credenciais de admin agora usam variáveis do .env
- ✅ Credenciais de operador agora usam variáveis do .env

#### `src/sheets_sync.py`
- ✅ ID da planilha agora usa `GOOGLE_SPREADSHEET_ID` do .env

### 3. Arquivos que NÃO serão commitados

Os seguintes arquivos estão protegidos pelo `.gitignore`:

- ❌ `.env` - Suas configurações locais
- ❌ `credentials.json` - Credenciais do Google
- ❌ `data/*.db` - Banco de dados
- ❌ `uploads/*.pdf` - PDFs enviados
- ❌ `__pycache__/` - Cache do Python

## 📝 Próximos Passos

### Antes de fazer o primeiro commit:

1. **Crie o arquivo `.env`** na raiz do projeto:
   ```bash
   cp .env.example .env
   ```

2. **Edite o `.env`** com suas configurações reais:
   - Copie os valores do `.env.example`
   - Preencha com suas credenciais atuais
   - **NUNCA commite este arquivo!**

3. **Verifique o `credentials.json`**:
   - Certifique-se de que está na raiz do projeto
   - Verifique se está listado no `.gitignore`
   - **NUNCA commite este arquivo!**

4. **Teste a aplicação localmente**:
   ```bash
   # Instale a nova dependência
   pip install python-dotenv
   
   # Teste se tudo funciona
   python app.py
   ```

### Para publicar no GitHub:

1. **Inicialize o repositório Git** (se ainda não fez):
   ```bash
   git init
   ```

2. **Adicione os arquivos**:
   ```bash
   git add .
   ```

3. **Verifique o que será commitado**:
   ```bash
   git status
   ```
   
   ⚠️ **IMPORTANTE**: Certifique-se de que NÃO aparecem:
   - `.env`
   - `credentials.json`
   - `database.db`
   - Arquivos em `uploads/`

4. **Faça o primeiro commit**:
   ```bash
   git commit -m "Initial commit - Sistema CONCAN"
   ```

5. **Conecte ao GitHub**:
   ```bash
   git remote add origin https://github.com/seu-usuario/concan.git
   git branch -M main
   git push -u origin main
   ```

## 🔐 Checklist de Segurança

Antes de fazer push, verifique:

- [ ] Arquivo `.env` está no `.gitignore`
- [ ] Arquivo `credentials.json` está no `.gitignore`
- [ ] Banco de dados `data/*.db` está no `.gitignore`
- [ ] Não há senhas hardcoded no código
- [ ] Arquivo `.env.example` está documentado
- [ ] README.md tem instruções claras de setup
- [ ] `git status` não mostra arquivos sensíveis

## 🚀 Para Colaboradores

Se alguém clonar o repositório, precisará:

1. Copiar `.env.example` para `.env`
2. Preencher as variáveis no `.env`
3. Obter o arquivo `credentials.json` (não está no repo)
4. Executar `pip install -r requirements.txt`
5. Executar `python criar_admin.py`

## 📞 Suporte

Se tiver dúvidas sobre a configuração, consulte o `README.md` principal.

---

**Última atualização**: 2025-12-10
