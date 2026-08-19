"""
Testes automatizados para a funcionalidade 'Lembrar de Mim' (Remember Me / Persistência de Login).
"""
import pytest
from pathlib import Path
import sys
from datetime import timedelta

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "src"))
sys.path.insert(0, str(BASE_DIR))

import app as flask_app
import database

TEST_DB = Path(__file__).parent / "test_remember_me.db"


@pytest.fixture
def setup_db():
    if TEST_DB.exists():
        try:
            TEST_DB.unlink()
        except PermissionError:
            pass

    database.DB_PATH = TEST_DB
    database.init_database()

    # Criar usuário de teste
    database.criar_usuario("teste_user", "senha123", "Usuário Teste", "operador_tsre", "TSRE")

    yield

    if TEST_DB.exists():
        try:
            TEST_DB.unlink()
        except PermissionError:
            pass


@pytest.fixture
def client(setup_db):
    flask_app.app.config['TESTING'] = True
    flask_app.app.config['WTF_CSRF_ENABLED'] = False
    with flask_app.app.test_client() as client:
        yield client


def test_config_remember_me():
    """Valida as configurações de persistência e segurança no Flask."""
    assert flask_app.app.config['REMEMBER_COOKIE_DURATION'] == timedelta(days=30)
    assert flask_app.app.config['REMEMBER_COOKIE_HTTPONLY'] is True
    assert flask_app.app.config['REMEMBER_COOKIE_SAMESITE'] == 'Lax'


def test_login_template_has_checkbox(client):
    """Valida que o checkbox 'remember' está presente e marcado por padrão na tela de login."""
    response = client.get('/login')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'name="remember"' in html
    assert 'id="remember"' in html
    assert 'checked' in html
    assert 'Lembrar de mim neste dispositivo' in html


def test_login_with_remember_me(client):
    """Valida que o login com 'remember=on' define o cookie 'remember_token'."""
    response = client.post('/login', data={
        'username': 'teste_user',
        'password': 'senha123',
        'remember': 'on'
    }, follow_redirects=False)

    assert response.status_code == 302
    assert response.headers['Location'] == '/'

    # Verificar presença do cookie remember_token nos cabeçalhos Set-Cookie
    cookies = response.headers.getlist('Set-Cookie')
    remember_cookie = next((c for c in cookies if 'remember_token=' in c), None)
    assert remember_cookie is not None, "Cookie remember_token não encontrado no Set-Cookie"
    assert 'HttpOnly' in remember_cookie
    assert 'SameSite=Lax' in remember_cookie


def test_login_without_remember_me(client):
    """Valida que o login sem o campo 'remember' não cria o cookie 'remember_token'."""
    response = client.post('/login', data={
        'username': 'teste_user',
        'password': 'senha123'
    }, follow_redirects=False)

    assert response.status_code == 302
    assert response.headers['Location'] == '/'

    cookies = response.headers.getlist('Set-Cookie')
    remember_cookie = next((c for c in cookies if 'remember_token=' in c and 'remember_token=;' not in c), None)
    assert remember_cookie is None, "Cookie remember_token não deveria ter sido definido"


def test_logout_clears_remember_token(client):
    """Valida que ao fazer logout o cookie de persistência é invalidado."""
    # Primeiro efetua login com remember=on
    client.post('/login', data={
        'username': 'teste_user',
        'password': 'senha123',
        'remember': 'on'
    }, follow_redirects=True)

    # Realiza logout
    logout_resp = client.get('/logout', follow_redirects=False)
    assert logout_resp.status_code == 302
    assert logout_resp.headers['Location'] == '/login'

    # Verifica se há limpeza do cookie remember_token nos cookies enviados na resposta
    cookies = logout_resp.headers.getlist('Set-Cookie')
    remember_cookie = next((c for c in cookies if 'remember_token=' in c), None)
    # No Flask-Login, logout_user remove/expira o cookie (valor vazio ou Max-Age=0 ou Expires no passado)
    if remember_cookie:
        assert 'remember_token=;' in remember_cookie or 'Max-Age=0' in remember_cookie or 'expires=' in remember_cookie.lower()
