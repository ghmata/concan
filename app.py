from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
import os
import sys
from werkzeug.utils import secure_filename
from datetime import datetime, timezone, timedelta
import dateutil.parser
from dotenv import load_dotenv

# Carrega variáveis de ambiente do arquivo .env
load_dotenv() 

# Configuração de caminho para módulos locais
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

# --- IMPORTAÇÃO CORRIGIDA (COM VÍRGULAS EXPLÍCITAS) ---
from database import (
    init_database, 
    listar_manifestos, 
    criar_manifesto, 
    adicionar_volume,
    obter_manifesto, 
    obter_estatisticas_manifesto, 
    marcar_recebido_web,
    excluir_manifesto,
    listar_volumes_detalhado,
    desfazer_recebimento_web,
    obter_caixas_por_volume,
    marcar_caixa_recebida_web,
    desfazer_caixa_web,
    buscar_volumes_geral,
    receber_todos_volumes_web,
    verificar_login,
    obter_usuario_por_id,
    salvar_observacao,          # Vírgula aqui
    listar_todos_usuarios,      # Vírgula aqui
    atualizar_senha,            # Vírgula aqui
    excluir_usuario_db,         # Vírgula aqui
    verificar_senha_atual_db,   # Vírgula aqui
    criar_usuario
)
from pdf_extractor import extrair_manifesto_pdf

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'chave_desenvolvimento_insegura_mude_isso') 

# --- FLASK LOGIN CONFIG ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login' 

class User(UserMixin):
    def __init__(self, id, username, nome, role):
        self.id = id
        self.username = username
        self.nome = nome
        self.role = role

@login_manager.user_loader
def load_user(user_id):
    dados = obter_usuario_por_id(user_id)
    if dados:
        return User(dados['id'], dados['username'], dados['nome_completo'], dados['role'])
    return None

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Inicializa banco
init_database()
BRT = timezone(timedelta(hours=-3))

@app.template_filter('datetimeformat')
def datetimeformat(value, format='%d/%m/%Y'):
    if not value: return "-"
    try:
        if isinstance(value, str): dt = dateutil.parser.parse(value)
        else: dt = value
        return dt.strftime(format)
    except: return value

# --- ROTAS DE AUTENTICAÇÃO ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user_data = verificar_login(username, password)
        if user_data:
            user_obj = User(user_data['id'], user_data['username'], user_data['nome_completo'], user_data['role'])
            login_user(user_obj)
            return redirect(url_for('index'))
        else:
            flash('Usuário ou senha incorretos.', 'danger')
            
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# --- ROTAS DE GESTÃO DE USUÁRIOS ---

@app.route('/usuarios', methods=['GET', 'POST'])
@login_required
def gerenciar_usuarios():
    if current_user.role != 'admin':
        flash("Acesso negado.", "danger")
        return redirect(url_for('index'))

    if request.method == 'POST':
        nome = request.form.get('nome')
        user = request.form.get('username')
        pwd = request.form.get('password')
        role = request.form.get('role')

        if criar_usuario(user, pwd, nome, role):
            flash(f"Usuário {nome} criado com sucesso!", "success")
        else:
            flash("Erro: Nome de usuário já existe.", "danger")
        return redirect(url_for('gerenciar_usuarios'))

    usuarios = listar_todos_usuarios()
    return render_template('usuarios.html', usuarios=usuarios)

@app.route('/usuarios/excluir/<int:id>', methods=['POST'])
@login_required
def excluir_usuario_rota(id):
    if current_user.role != 'admin': return redirect(url_for('index'))
    if id == current_user.id:
        flash("Você não pode excluir sua própria conta.", "warning")
        return redirect(url_for('gerenciar_usuarios'))

    excluir_usuario_db(id)
    flash("Usuário removido.", "success")
    return redirect(url_for('gerenciar_usuarios'))

@app.route('/perfil', methods=['GET', 'POST'])
@login_required
def perfil():
    if request.method == 'POST':
        senha_atual = request.form.get('senha_atual')
        nova_senha = request.form.get('nova_senha')
        confirmar_senha = request.form.get('confirmar_senha')

        if not verificar_senha_atual_db(current_user.id, senha_atual):
            flash("Senha atual incorreta.", "danger")
            return redirect(url_for('perfil'))

        if nova_senha != confirmar_senha:
            flash("A nova senha e a confirmação não conferem.", "warning")
            return redirect(url_for('perfil'))

        atualizar_senha(current_user.id, nova_senha)
        flash("Senha alterada com sucesso!", "success")
        return redirect(url_for('index'))

    return render_template('perfil.html')

# --- ROTAS PRINCIPAIS ---

@app.route('/')
@login_required
def index():
    manifestos = listar_manifestos()
    return render_template('index.html', manifestos=manifestos)

@app.route('/busca')
@login_required
def busca_avancada():
    return render_template('busca.html')

@app.route('/novo', methods=['GET'])
@login_required
def novo_manifesto():
    return render_template('novo.html')

@app.route('/conferencia/<int:manifesto_id>')
@login_required
def conferencia(manifesto_id):
    manifesto = obter_manifesto(manifesto_id)
    if not manifesto:
        return redirect(url_for('index'))
    stats = obter_estatisticas_manifesto(manifesto_id)
    todos_volumes = listar_volumes_detalhado(manifesto_id)
    return render_template('conferencia.html', m=manifesto, stats=stats, volumes=todos_volumes)

@app.route('/upload', methods=['POST'])
@login_required
def upload_file():
    if 'pdf_file' not in request.files: return redirect(url_for('novo_manifesto'))
    file = request.files['pdf_file']
    if file.filename == '': return redirect(url_for('novo_manifesto'))

    if file:
        try:
            filename = secure_filename(file.filename)
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            file.save(filepath)
            dados, volumes, erros = extrair_manifesto_pdf(filepath)

            if not dados or not dados.get('numero_manifesto'):
                flash('Falha ao ler PDF.', 'danger')
                return redirect(url_for('novo_manifesto'))

            data_man = datetime.now(BRT).strftime("%d/%m/%Y")
            
            mid = criar_manifesto(dados['numero_manifesto'], data_man, 
                                  dados.get('terminal_origem', 'DESC'), 
                                  dados.get('terminal_destino', 'DESC'), 
                                  dados.get('missao'), dados.get('aeronave'), filepath)

            for vol in volumes:
                adicionar_volume(mid, vol['remetente'], vol['destinatario'], vol['numero_volume'],
                                vol['quantidade_expedida'], peso=vol.get('peso_total'), 
                                cubagem=vol.get('cubagem'), prioridade=vol.get('prioridade'), 
                                tipo_material=vol.get('tipo_material'), embalagem=vol.get('embalagem'))

            flash(f'Importado! {len(volumes)} volumes.', 'success')
            return redirect(url_for('index'))
        except Exception as e:
            flash(f'Erro: {str(e)}', 'danger')
            return redirect(url_for('novo_manifesto'))

@app.route('/excluir/<int:id>', methods=['POST'])
@login_required
def excluir(id):
    if current_user.role != 'admin':
        flash("Apenas administradores podem excluir.", "danger")
        return redirect(url_for('index'))
        
    senha = request.form.get('senha')
    senha_correta = os.getenv('ADMIN_DELETE_PASSWORD', 'pitaco')
    if senha == senha_correta: 
        if excluir_manifesto(id): flash("Excluído com sucesso!", "success")
        else: flash("Erro ao excluir.", "danger")
    else: flash("Senha de confirmação incorreta!", "danger")
    return redirect(url_for('index'))

# --- APIS (AJAX) ---

@app.route('/api/busca/manifestos', methods=['POST'])
@login_required
def api_busca_manifestos():
    data = request.json
    res = listar_manifestos(data.get('numero'), data.get('status'), data.get('data_ini'), data.get('data_fim'))
    return jsonify(res)

@app.route('/api/busca/volumes', methods=['POST'])
@login_required
def api_busca_volumes():
    data = request.json
    res = buscar_volumes_geral(data.get('termo', ''))
    return jsonify(res)

@app.route('/api/receber_tudo_manifesto', methods=['POST'])
@login_required
def api_receber_tudo():
    """Recebe TODOS os volumes de um manifesto inteiro"""
    data = request.json
    if receber_todos_volumes_web(data.get('manifesto_id'), current_user.nome):
        return jsonify({'status': 'ok'})
    return jsonify({'status': 'erro'}), 500

@app.route('/api/receber_rapido_volume', methods=['POST'])
@login_required
def api_receber_rapido_volume():
    """Recebe TODAS as caixas de um único volume (atalho do botão Receber Tudo)"""
    data = request.json
    if marcar_recebido_web(data['volume_id'], current_user.nome):
        return jsonify({'status': 'ok'})
    return jsonify({'status': 'erro'}), 500

@app.route('/api/manifesto/<int:id>/volumes', methods=['GET'])
@login_required
def api_listar_volumes_manifesto(id):
    volumes = listar_volumes_detalhado(id)
    return jsonify([dict(v) for v in volumes])

# Rota para o Extramanifesto
@app.route('/api/adicionar_extra_conferencia', methods=['POST'])
@login_required
def api_adicionar_extra_conferencia():
    data = request.json
    try:
        vol_id = adicionar_volume(
            manifesto_id=data['manifesto_id'],
            remetente=data.get('remetente', 'DESCONHECIDO'),
            destinatario="PAMALS",
            numero_volume=data['numero_volume'],
            quantidade_exp=int(data['quantidade']),
            peso=0.0, 
            cubagem=0.0, 
            prioridade="EXTRA",
            tipo_material="VOLUME EXTRA",
            embalagem="CAIXA"
        )
        return jsonify({'status': 'ok', 'msg': 'Volume adicionado!'})
    except Exception as e:
        return jsonify({'status': 'erro', 'msg': str(e)}), 500

# Rota legada (mantida para compatibilidade)
@app.route('/api/adicionar_extra', methods=['POST'])
@login_required
def api_adicionar_extra():
    data = request.json
    try:
        vol_id = adicionar_volume(data['manifesto_id'], data['remetente'], "PAMALS", 
                                 data['numero_volume'], int(data['quantidade']),
                                 peso=0.0, cubagem=0.0, prioridade="EXTRA",
                                 tipo_material="VOLUME EXTRA", embalagem="CAIXA")
        marcar_recebido_web(vol_id, current_user.nome)
        return jsonify({'status': 'ok', 'msg': 'Adicionado e recebido!'})
    except Exception as e:
        return jsonify({'status': 'erro', 'msg': str(e)}), 500

@app.route('/api/receber', methods=['POST'])
@login_required
def api_receber():
    data = request.json
    if marcar_recebido_web(data['volume_id'], current_user.nome):
        return jsonify({'status': 'ok'})
    return jsonify({'status': 'erro'}), 500

@app.route('/api/desfazer', methods=['POST'])
@login_required
def api_desfazer():
    data = request.json
    if desfazer_recebimento_web(data['volume_id']):
        return jsonify({'status': 'ok'})
    return jsonify({'status': 'erro'}), 500

@app.route('/api/obter_caixas', methods=['POST'])
@login_required
def api_obter_caixas():
    data = request.json
    try:
        caixas = obter_caixas_por_volume(data['volume_id'])
        return jsonify([dict(c) for c in caixas])
    except: return jsonify([]), 500

@app.route('/api/receber_caixa', methods=['POST'])
@login_required
def api_receber_caixa():
    data = request.json
    if marcar_caixa_recebida_web(data['volume_id'], data['numero_caixa'], current_user.nome):
        return jsonify({'status': 'ok'})
    return jsonify({'status': 'erro'}), 500

@app.route('/api/desfazer_caixa', methods=['POST'])
@login_required
def api_desfazer_caixa():
    data = request.json
    if desfazer_caixa_web(data['volume_id'], data['numero_caixa']):
        return jsonify({'status': 'ok'})
    return jsonify({'status': 'erro'}), 500

@app.route('/api/observacao', methods=['POST'])
@login_required
def api_observacao():
    data = request.json
    if salvar_observacao(data['volume_id'], data['texto']):
        return jsonify({'status': 'ok'})
    return jsonify({'status': 'erro'}), 500

# Importação para garantir que o sync rode se necessário ao iniciar
try:
    import sheets_sync
except: pass

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)