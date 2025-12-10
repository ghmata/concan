# 📦 CONCAN - Sistema de Gestão de Manifestos de Carga

Sistema web desenvolvido em Flask para gerenciamento e conferência de manifestos de carga aérea, com sincronização automática com Google Sheets.

## 🚀 Funcionalidades

- ✅ **Importação automática de PDFs** de manifestos
- 📊 **Dashboard de conferência** com status em tempo real
- 🔄 **Sincronização com Google Sheets** para acompanhamento colaborativo
- 👥 **Sistema de autenticação** com diferentes níveis de acesso
- 📱 **Interface responsiva** com Bootstrap 5
- 🔍 **Busca avançada** de volumes e manifestos
- 📝 **Sistema de observações** por volume
- ✏️ **Gestão de usuários** (admin)

## 📋 Pré-requisitos

- Python 3.8 ou superior
- pip (gerenciador de pacotes Python)
- Conta Google Cloud com API do Google Sheets habilitada

## 🔧 Instalação

### 1. Clone o repositório

```bash
git clone https://github.com/seu-usuario/concan.git
cd concan
```

### 2. Crie um ambiente virtual

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate
```

### 3. Instale as dependências

```bash
pip install -r requirements.txt
```

### 4. Configure as variáveis de ambiente

Copie o arquivo `.env.example` para `.env` e preencha com suas configurações:

```bash
cp .env.example .env
```

Edite o arquivo `.env` e configure:
- `FLASK_SECRET_KEY`: Uma chave secreta aleatória para o Flask
- `ADMIN_DELETE_PASSWORD`: Senha para confirmação de exclusão de manifestos
- `GOOGLE_SPREADSHEET_ID`: ID da sua planilha do Google Sheets
- Credenciais dos usuários iniciais

### 5. Configure as credenciais do Google Sheets

1. Acesse o [Google Cloud Console](https://console.cloud.google.com/)
2. Crie um novo projeto ou selecione um existente
3. Habilite a **Google Sheets API** e **Google Drive API**
4. Crie uma **Service Account**
5. Baixe o arquivo JSON de credenciais
6. Renomeie para `credentials.json` e coloque na raiz do projeto
7. Compartilhe sua planilha do Google Sheets com o email da Service Account

### 6. Inicialize o banco de dados

```bash
python criar_admin.py
```

Este comando irá:
- Criar o banco de dados SQLite
- Criar as tabelas necessárias
- Criar o usuário administrador inicial

## ▶️ Executando a aplicação

### Modo de desenvolvimento

```bash
python app.py
```

A aplicação estará disponível em `http://localhost:5000`

### Credenciais padrão

Após executar `criar_admin.py`, você pode fazer login com:
- **Usuário**: admin
- **Senha**: admin123

⚠️ **IMPORTANTE**: Altere a senha padrão imediatamente após o primeiro login!

## 📁 Estrutura do Projeto

```
concan/
├── app.py                 # Aplicação principal Flask
├── criar_admin.py         # Script de inicialização do banco
├── requirements.txt       # Dependências Python
├── .env.example          # Exemplo de variáveis de ambiente
├── .gitignore            # Arquivos ignorados pelo Git
├── credentials.json      # Credenciais Google (NÃO COMMITAR)
├── data/
│   └── database.db       # Banco de dados SQLite
├── src/
│   ├── database.py       # Funções de banco de dados
│   ├── pdf_extractor.py  # Extração de dados de PDFs
│   └── sheets_sync.py    # Sincronização com Google Sheets
├── static/
│   ├── css/
│   └── js/
├── templates/            # Templates HTML (Jinja2)
└── uploads/             # PDFs enviados pelos usuários
```

## 🔐 Segurança

- **Nunca commite** o arquivo `credentials.json`
- **Nunca commite** o arquivo `.env`
- **Nunca commite** o banco de dados `database.db`
- Altere todas as senhas padrão em produção
- Use HTTPS em produção
- Mantenha as dependências atualizadas

## 🌐 Deploy (PythonAnywhere)

1. Faça upload dos arquivos para o PythonAnywhere
2. Configure o arquivo `.env` com as variáveis de produção
3. Instale as dependências: `pip install -r requirements.txt`
4. Configure o WSGI file apontando para `app.py`
5. Recarregue a aplicação

## 🛠️ Tecnologias Utilizadas

- **Backend**: Flask 2.x
- **Banco de Dados**: SQLite com SQLAlchemy
- **Frontend**: Bootstrap 5, JavaScript
- **Autenticação**: Flask-Login
- **PDF Processing**: PyPDF2, pdfplumber
- **Google Sheets**: gspread, oauth2client

## 📝 Licença

Este projeto é de uso privado.

## 👨‍💻 Autor

Desenvolvido para gestão de manifestos de carga aérea.

## 🤝 Contribuindo

Este é um projeto privado. Para sugestões ou melhorias, entre em contato com o desenvolvedor.

## 📞 Suporte

Para questões ou problemas, abra uma issue no repositório.

---

**Nota**: Este sistema foi desenvolvido especificamente para gestão de manifestos de carga aérea e pode requerer customizações para outros casos de uso.
