from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, abort
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
import os
import sys
import re
import time
import json
import uuid
from werkzeug.utils import secure_filename
from datetime import datetime, timezone, timedelta
import dateutil.parser
import bleach

# Configuração de caminho para módulos locais
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

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
    salvar_observacao,
    listar_todos_usuarios,
    listar_usuarios_ativos,
    atualizar_senha,
    excluir_usuario_db,
    verificar_senha_atual_db,
    validar_senha_admin_secao,
    manifesto_conferencia_finalizada,
    criar_usuario,
    marcar_status_especial_caixa,
    marcar_status_especial_volume,
    adicionar_observacao_manual,
    excluir_observacao_manual,
    listar_observacoes_manuais,
    obter_info_fixas_volume,
    atualizar_info_fixas_volume,
    registrar_log,
    get_connection,
    obter_imagens_manifesto_ocr,
    autorizar_manifesto,
    negar_manifesto,
    listar_manifestos_pendentes,
    obter_info_manifesto_secao,
    obter_manifesto_por_numero,
    obter_status_conferencia_cruzada,
    excluir_manifesto_secao,
    listar_logs,
)
from pdf_extractor import extrair_manifesto_pdf
from ocr_parser import parse_ocr_text

app = Flask(__name__)
_secret_key = os.environ.get('CONCAN_SECRET_KEY')
if not _secret_key:
    import logging
    logging.warning("AVISO DE SEGURANÇA: CONCAN_SECRET_KEY não definida no ambiente. Usando chave padrão para desenvolvimento/testes.")
    _secret_key = 'chave_secreta_can_mobile_v3'
app.secret_key = _secret_key
app.config['REMEMBER_COOKIE_DURATION'] = timedelta(days=30)
app.config['REMEMBER_COOKIE_HTTPONLY'] = True
app.config['REMEMBER_COOKIE_SAMESITE'] = 'Lax'

# --- FLASK LOGIN CONFIG ---
from functools import wraps

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'


class User(UserMixin):
    def __init__(self, id, username, nome, role, secao='TSRE'):
        self.id = id
        self.username = username
        self.nome = nome
        self.role = role
        self.secao = secao or 'TSRE'


@login_manager.user_loader
def load_user(user_id):
    dados = obter_usuario_por_id(user_id)
    if dados:
        return User(dados['id'], dados['username'], dados['nome_completo'], dados['role'], dados.get('secao', 'TSRE'))
    return None


# ═══════════════════════════════════════════════════
# HELPERS DE ROLES E PERMISSÕES (FASE 1)
# ═══════════════════════════════════════════════════

def is_super_admin(user):
    return user.is_authenticated and user.role == 'super_admin'


def is_admin_secao(user, secao=None):
    if not user.is_authenticated:
        return False
    if user.role == 'super_admin':
        return True
    if secao:
        return user.role == f"admin_{secao.lower()}"
    return user.role in ['admin', 'admin_tsre', 'admin_can']


def pode_operar(user, secao):
    if not user.is_authenticated:
        return False
    if user.role == 'super_admin':
        return True
    return user.secao == secao


def pode_visualizar(user, secao):
    return user.is_authenticated


def pode_gerenciar_usuarios(user, secao=None):
    if not user.is_authenticated:
        return False
    if user.role == 'super_admin':
        return True
    if secao:
        return user.role == f"admin_{secao.lower()}"
    return user.role in ['admin', 'admin_tsre', 'admin_can']


def pode_deletar_usuarios(user):
    return user.is_authenticated and user.role == 'super_admin'


def requer_secao(secao):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('login'))
            if not pode_operar(current_user, secao):
                flash("Acesso não permitido para sua seção.", "danger")
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator


@app.context_processor
def inject_user_permissions():
    return dict(
        is_super_admin=is_super_admin,
        is_admin_secao=is_admin_secao,
        pode_gerenciar_usuarios=pode_gerenciar_usuarios,
        pode_deletar_usuarios=pode_deletar_usuarios
    )


UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Inicializa banco
init_database()
BRT = timezone(timedelta(hours=-3))


# ═══════════════════════════════════════════════════
# FILTROS JINJA (REQ-03)
# ═══════════════════════════════════════════════════

@app.template_filter('formatarbrt')
def formatar_brt(value):
    """Formata datetime para dd/mm/aa - hh:mm no fuso BRT."""
    if not value:
        return "-"
    try:
        if isinstance(value, str):
            dt = dateutil.parser.parse(value)
        else:
            dt = value
        # Se não tem timezone, assume BRT
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=BRT)
        # Converte para BRT
        dt_brt = dt.astimezone(BRT)
        return dt_brt.strftime("%d/%m/%y - %H:%M")
    except Exception:
        return str(value)


@app.template_filter('datetimeformat')
def datetimeformat(value, format='%d/%m/%Y'):
    """Filtro legado mantido para compatibilidade."""
    if not value:
        return "-"
    try:
        if isinstance(value, str):
            dt = dateutil.parser.parse(value)
        else:
            dt = value
        return dt.strftime(format)
    except Exception:
        return value


# ═══════════════════════════════════════════════════
# ROTAS DE AUTENTICAÇÃO
# ═══════════════════════════════════════════════════

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        user_data = verificar_login(username, password)
        if user_data:
            user_obj = User(
                user_data['id'], user_data['username'],
                user_data['nome_completo'], user_data['role'],
                user_data.get('secao', 'TSRE')
            )
            lembrar = request.form.get('remember') == 'on'
            login_user(user_obj, remember=lembrar)
            return redirect(url_for('index'))
        else:
            flash('Usuário ou senha incorretos.', 'danger')

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


# ═══════════════════════════════════════════════════
# ROTAS DE GESTÃO DE USUÁRIOS
# ═══════════════════════════════════════════════════

@app.route('/usuarios', methods=['GET', 'POST'])
@login_required
def gerenciar_usuarios():
    if not pode_gerenciar_usuarios(current_user):
        flash("Acesso negado.", "danger")
        return redirect(url_for('index'))

    if request.method == 'POST':
        nome = request.form.get('nome', '').strip()
        user = request.form.get('username', '').strip()
        pwd = request.form.get('password', '')
        role = request.form.get('role', 'operador_tsre')
        secao = request.form.get('secao', 'TSRE')

        if not is_super_admin(current_user):
            secao = current_user.secao
            if current_user.secao == 'TSRE' and role not in ['operador_tsre', 'admin_tsre']:
                role = 'operador_tsre'
            elif current_user.secao == 'CAN' and role not in ['operador_can', 'admin_can']:
                role = 'operador_can'

        if criar_usuario(user, pwd, nome, role, secao):
            flash(f"Usuário {nome} criado com sucesso!", "success")
        else:
            flash("Erro: Nome de usuário já existe.", "danger")
        return redirect(url_for('gerenciar_usuarios'))

    if is_super_admin(current_user):
        usuarios = listar_todos_usuarios()
    else:
        usuarios = listar_todos_usuarios(secao_filtro=current_user.secao)

    return render_template('usuarios.html', usuarios=usuarios)


@app.route('/usuarios/excluir/<int:id>', methods=['POST'])
@login_required
def excluir_usuario_rota(id):
    if not pode_deletar_usuarios(current_user):
        flash("Apenas o Super-Admin pode excluir usuários.", "danger")
        return redirect(url_for('gerenciar_usuarios'))
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


# ═══════════════════════════════════════════════════
# ROTAS PRINCIPAIS
# ═══════════════════════════════════════════════════

@app.route('/')
@login_required
def index():
    return redirect(url_for('dashboard_secao', secao=current_user.secao))


@app.route('/dashboard/<secao>')
@login_required
def dashboard_secao(secao):
    secao_exibida = secao.upper()
    if secao_exibida not in ['TSRE', 'CAN']:
        return redirect(url_for('dashboard_secao', secao=current_user.secao))

    if is_super_admin(current_user):
        is_readonly = False
    else:
        is_readonly = (secao_exibida != current_user.secao)

    manifestos = listar_manifestos(secao=secao_exibida)
    pendentes = listar_manifestos_pendentes(secao_exibida) if not is_readonly else []

    return render_template(
        'index.html',
        manifestos=manifestos,
        pendentes=pendentes,
        secao_exibida=secao_exibida,
        is_readonly=is_readonly
    )


@app.route('/busca')
@login_required
def busca_avancada():
    secao_ativa = request.args.get('secao', current_user.secao).upper()
    if secao_ativa not in ['TSRE', 'CAN']:
        secao_ativa = current_user.secao
    return render_template('busca.html', secao_ativa=secao_ativa)


# ═══════════════════════════════════════════════════
# APIs (AJAX)
# ═══════════════════════════════════════════════════

@app.route('/api/busca/manifestos', methods=['POST'])
@login_required
def api_busca_manifestos():
    data = request.json or {}
    secao_req = data.get('secao', current_user.secao).upper()
    res = listar_manifestos(
        filtro_num=data.get('numero'),
        filtro_status=data.get('status'),
        data_ini=data.get('data_ini'),
        data_fim=data.get('data_fim'),
        secao=secao_req
    )
    return jsonify(res)


@app.route('/api/busca/volumes', methods=['POST'])
@login_required
def api_busca_volumes():
    data = request.json or {}
    secao_req = data.get('secao', current_user.secao).upper()
    res = buscar_volumes_geral(data.get('termo', ''), secao=secao_req)
    
    # Se o usuário logado não for super_admin e pesquisar outra seção diferente da sua própria, pode_operar = False
    if not (is_super_admin(current_user) or current_user.secao == secao_req):
        for v in res:
            v['pode_operar'] = False

    return jsonify(res)


@app.route('/novo', methods=['GET'])
@login_required
def novo_manifesto():
    return render_template('novo.html')


@app.route('/escanear', methods=['GET'])
@login_required
def escanear_manifesto():
    """Renderiza a página com o fluxo de escaneamento por câmera e OCR client-side."""
    if current_user.secao == 'CAN':
        flash('Funcionalidade de escaneamento por câmera/OCR não está disponível para a seção CAN.', 'warning')
        return redirect(url_for('index'))
    return render_template('escanear.html')


@app.route('/conferencia/<int:manifesto_id>')
@login_required
def conferencia(manifesto_id):
    manifesto = obter_manifesto(manifesto_id)
    if not manifesto:
        return redirect(url_for('index'))

    secao_param = request.args.get('secao', current_user.secao).upper()
    if secao_param not in ['TSRE', 'CAN']:
        secao_param = current_user.secao

    if is_super_admin(current_user):
        is_readonly = False
    else:
        is_readonly = (secao_param != current_user.secao)

    stats = obter_estatisticas_manifesto(manifesto_id, secao=secao_param)
    todos_volumes = listar_volumes_detalhado(manifesto_id, secao=secao_param)
    return render_template(
        'conferencia.html',
        m=manifesto,
        stats=stats,
        volumes=todos_volumes,
        is_readonly=is_readonly,
        secao_exibida=secao_param
    )


@app.route('/upload', methods=['POST'])
@login_required
def upload_file():
    if 'pdf_file' not in request.files:
        return redirect(url_for('novo_manifesto'))
    file = request.files['pdf_file']
    if file.filename == '':
        return redirect(url_for('novo_manifesto'))

    if file:
        try:
            filename = secure_filename(file.filename)
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            file.save(filepath)

            secao_uploader = current_user.secao
            if secao_uploader == 'TSRE':
                dados, volumes, erros = extrair_manifesto_pdf(filepath, filtro_destinatario='PAMALS')
            else:
                dados, volumes, erros = extrair_manifesto_pdf(filepath, filtro_destinatario=None)

            if not dados or not dados.get('numero_manifesto'):
                msg_erro = f"Falha ao ler PDF. {', '.join(erros)}" if erros else "Falha ao ler PDF."
                flash(msg_erro, 'danger')
                return redirect(url_for('novo_manifesto'))

            numero_man = dados['numero_manifesto']
            # Verificar se o manifesto já existe no sistema para esta seção
            man_existente = obter_manifesto_por_numero(numero_man, secao=secao_uploader)
            if man_existente:
                flash(f'O manifesto {numero_man} já está cadastrado nesta seção.', 'info')
                return redirect(url_for('dashboard_secao', secao=secao_uploader))

            data_man = datetime.now(BRT).strftime("%d/%m/%Y")

            mid = criar_manifesto(
                dados['numero_manifesto'], data_man,
                dados.get('terminal_origem', 'DESC'),
                dados.get('terminal_destino', 'DESC'),
                dados.get('missao'), dados.get('aeronave'), filepath,
                origem_registro='PDF_DIGITAL',
                usuario=current_user.nome or current_user.username,
                secao_origem=secao_uploader
            )

            for vol in volumes:
                adicionar_volume(
                    mid, vol['remetente'], vol['destinatario'],
                    vol['numero_volume'], vol['quantidade_expedida'],
                    secao_origem=secao_uploader,
                    peso=vol.get('peso_total'), cubagem=vol.get('cubagem'),
                    prioridade=vol.get('prioridade'),
                    tipo_material=vol.get('tipo_material'),
                    embalagem=vol.get('embalagem')
                )
            flash(f'Importado com sucesso! {len(volumes)} volumes cadastrados por {secao_uploader}.', 'success')
            return redirect(url_for('dashboard_secao', secao=secao_uploader))
        except Exception as e:
            flash(f'Erro ao importar manifesto: {str(e)}', 'danger')
            return redirect(url_for('novo_manifesto'))


@app.route('/api/manifesto/<int:manifesto_id>/autorizar', methods=['POST'])
@login_required
def api_autorizar_manifesto(manifesto_id):
    """Autoriza o manifesto para a seção do usuário logado."""
    sucesso = autorizar_manifesto(
        manifesto_id,
        current_user.secao,
        current_user.nome or current_user.username
    )
    if sucesso:
        return jsonify({'status': 'sucesso', 'msg': 'Manifesto autorizado com sucesso.'})
    else:
        return jsonify({'status': 'erro', 'msg': 'Falha ao autorizar manifesto.'}), 500


@app.route('/api/manifesto/<int:manifesto_id>/negar', methods=['POST'])
@login_required
def api_negar_manifesto(manifesto_id):
    """Nega o manifesto para a seção do usuário logado."""
    sucesso = negar_manifesto(
        manifesto_id,
        current_user.secao,
        current_user.nome or current_user.username
    )
    if sucesso:
        return jsonify({'status': 'sucesso', 'msg': 'Manifesto negado com sucesso.'})
    else:
        return jsonify({'status': 'erro', 'msg': 'Falha ao negar manifesto.'}), 500


@app.route('/api/manifestos/pendentes', methods=['GET'])
@login_required
def api_listar_manifestos_pendentes():
    """Retorna lista em JSON de manifestos pendentes de autorização para a seção do usuário."""
    pendentes = listar_manifestos_pendentes(current_user.secao)
    return jsonify({'status': 'sucesso', 'pendentes': pendentes})


@app.route('/api/importar_manifesto_ocr', methods=['POST'])
@login_required
def api_importar_manifesto_ocr():
    """Valida, cria e persiste o manifesto e volumes gerados via OCR Mobile, além de arquivar as fotos."""
    if current_user.secao == 'CAN':
        return jsonify({'status': 'erro', 'msg': 'Funcionalidade de escaneamento por câmera/OCR não está disponível para a seção CAN.'}), 403

    # Rate Limiting (SEC-04): máx 10 envios por minuto
    agora = time.time()
    tempos = session.get('ocr_upload_timestamps', [])
    tempos = [t for t in tempos if agora - t < 60]
    if len(tempos) >= 10:
        return jsonify({'status': 'erro', 'msg': 'Limite de requisições excedido. Aguarde um minuto antes de reenviar.'}), 429
    tempos.append(agora)
    session['ocr_upload_timestamps'] = tempos

    # Coleta os metadados do form
    manifesto_dados_raw = request.form.get('manifesto_dados')
    volumes_raw = request.form.get('volumes')

    if not manifesto_dados_raw or not volumes_raw:
        return jsonify({'status': 'erro', 'msg': 'Dados do manifesto ou volumes ausentes.'}), 400

    try:
        dados = json.loads(manifesto_dados_raw)
        volumes = json.loads(volumes_raw)
    except Exception:
        return jsonify({'status': 'erro', 'msg': 'Dados JSON com formato inválido.'}), 400

    numero_manifesto = dados.get('numero_manifesto', '').strip()
    if not re.match(r'^\d{12}$', numero_manifesto):
        return jsonify({'status': 'erro', 'msg': 'Número do manifesto inválido. Deve conter exatamente 12 dígitos.'}), 400

    # Sanitização com bleach.clean (SEC-02)
    numero_manifesto = bleach.clean(numero_manifesto)
    terminal_origem = bleach.clean(dados.get('terminal_origem', 'DESC').strip() or 'DESC')[:50]
    terminal_destino = bleach.clean(dados.get('terminal_destino', 'DESC').strip() or 'DESC')[:50]
    missao = bleach.clean(dados.get('missao', '').strip() or '')[:50]
    aeronave = bleach.clean(dados.get('aeronave', '').strip() or '')[:50]

    # Validação e Processamento das Imagens (SEC-01)
    imagens = request.files.getlist('imagens')
    if not imagens or len(imagens) == 0 or (len(imagens) == 1 and imagens[0].filename == ''):
        return jsonify({'status': 'erro', 'msg': 'Pelo menos uma imagem do manifesto escaneado deve ser enviada como evidência física.'}), 400

    arquivos_validos = []
    for file in imagens:
        # Validar MIME type
        content_type = file.content_type
        if content_type not in ['image/jpeg', 'image/png']:
            return jsonify({'status': 'erro', 'msg': f'MIME-type não permitido: {content_type}. Apenas JPEG e PNG são aceitos.'}), 400

        # Validar Magic Bytes
        magic = file.read(8)
        file.seek(0)
        is_jpeg = magic.startswith(b'\xff\xd8\xff')
        is_png = magic.startswith(b'\x89PNG\r\n\x1a\n')

        if not (is_jpeg or is_png):
            return jsonify({'status': 'erro', 'msg': 'Cabeçalho do arquivo inválido. Apenas imagens reais são permitidas.'}), 400
        
        ext = '.jpg' if is_jpeg else '.png'
        secure_name = f"{uuid.uuid4()}{ext}"
        arquivos_validos.append((file, secure_name))

    # Persistência
    try:
        data_man = datetime.now(BRT).strftime("%d/%m/%Y")
        
        # Cria manifesto provisório para obter o ID
        pdf_path_provisorio = os.path.join(UPLOAD_FOLDER, 'manifestos_escaneados', 'temp_' + str(uuid.uuid4()))
        
        mid = criar_manifesto(
            numero_manifesto, data_man, terminal_origem, terminal_destino,
            missao, aeronave, pdf_path_provisorio,
            origem_registro='OCR_MOBILE', usuario=current_user.nome
        )
        
        # Atualiza para pasta definitiva baseada no ID
        dir_definitivo = os.path.join(UPLOAD_FOLDER, 'manifestos_escaneados', str(mid))
        os.makedirs(dir_definitivo, exist_ok=True)
        
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE manifestos SET pdf_path = ? WHERE id = ?", (dir_definitivo, mid))
        conn.commit()
        conn.close()
        
        # Salva arquivos na pasta
        for file, secure_name in arquivos_validos:
            filepath = os.path.join(dir_definitivo, secure_name)
            file.save(filepath)

        # Cadastra volumes
        volumes_adicionados = 0
        for vol in volumes:
            num_vol = bleach.clean(vol.get('numero_volume', '').strip())
            remetente = bleach.clean(vol.get('remetente', 'DESCONHECIDO').strip())
            qtd = int(vol.get('quantidade_expedida', 1))
            prioridade = bleach.clean(vol.get('prioridade', '00').strip() or '00')
            
            if not re.match(r'^\d{12}/\d{4}$', num_vol):
                raise ValueError(f"Formato de volume inválido: {num_vol}")

            adicionar_volume(
                mid, remetente, 'PAMALS', num_vol, qtd,
                peso=0.0, cubagem=0.0, prioridade=prioridade,
                tipo_material='Geral', embalagem='CAIXA'
            )
            volumes_adicionados += 1

        # Auditoria
        conn = get_connection()
        cursor = conn.cursor()
        registrar_log(
            cursor, mid, None, None,
            'IMPORTAR_OCR', current_user.nome,
            None, {'numero_manifesto': numero_manifesto, 'paginas': len(arquivos_validos), 'volumes': volumes_adicionados}
        )
        conn.commit()
        conn.close()

        # Adiciona mensagem de sucesso via flash
        flash(f'Manifesto {numero_manifesto} importado com sucesso via OCR! {volumes_adicionados} volumes cadastrados.', 'success')
        return jsonify({'status': 'ok'})

    except Exception as e:
        if 'mid' in locals() and os.path.exists(dir_definitivo):
            import shutil
            try:
                shutil.rmtree(dir_definitivo)
            except Exception:
                pass
        return jsonify({'status': 'erro', 'msg': f'Erro ao salvar manifesto no banco: {str(e)}'}), 500


@app.route('/api/manifesto/<int:id>/imagens_escaneadas', methods=['GET'])
@login_required
def api_imagens_escaneadas(id):
    """Retorna lista de nomes das imagens de evidência para um manifesto OCR específico."""
    manifesto = obter_manifesto(id)
    if not manifesto:
        return jsonify({'status': 'erro', 'msg': 'Manifesto não encontrado.'}), 404
        
    if manifesto.get('origem') != 'OCR_MOBILE':
        return jsonify({'status': 'erro', 'msg': 'Este manifesto não foi importado por OCR.'}), 400
        
    imagens = obter_imagens_manifesto_ocr(id)
    return jsonify(imagens)


@app.route('/api/manifesto/<int:id>/imagem/<filename>', methods=['GET'])
@login_required
def api_servir_imagem_manifesto(id, filename):
    """Serve um arquivo de imagem individual arquivado, validando autenticação e origem."""
    manifesto = obter_manifesto(id)
    if not manifesto:
        return abort(404)
        
    if manifesto.get('origem') != 'OCR_MOBILE':
        return abort(403)
        
    # Sanitização contra Directory Traversal
    filename = secure_filename(filename)
    dir_path = os.path.join(UPLOAD_FOLDER, 'manifestos_escaneados', str(id))
    
    filepath = os.path.join(dir_path, filename)
    if not os.path.exists(filepath):
        return abort(404)
        
    from flask import send_from_directory
    return send_from_directory(dir_path, filename)


@app.route('/excluir/<int:id>', methods=['POST'])
@login_required
def excluir(id):
    if not is_admin_secao(current_user, current_user.secao):
        flash("Apenas administradores podem excluir.", "danger")
        return redirect(url_for('dashboard_secao', secao=current_user.secao))

    senha = request.form.get('senha')
    if validar_senha_admin_secao(senha, current_user.secao):
        if excluir_manifesto_secao(id, current_user.secao, usuario=current_user.nome or current_user.username):
            flash(f"Manifesto removido da seção {current_user.secao} com sucesso!", "success")
        else:
            flash("Erro ao excluir manifesto.", "danger")
    else:
        flash("Senha de confirmação incorreta ou sem permissão!", "danger")
    return redirect(url_for('dashboard_secao', secao=current_user.secao))


@app.route('/api/manifesto/<int:id>/logs', methods=['GET'])
@login_required
def api_listar_logs_manifesto(id):
    """Retorna os logs de auditoria de um manifesto (R06)."""
    secao_param = request.args.get('secao')
    logs = listar_logs(manifesto_id=id, secao=secao_param)
    return jsonify(logs)


@app.route('/api/parse_ocr_text', methods=['POST'])
@login_required
def api_parse_ocr_text():
    """Recebe texto bruto de OCR do cliente e retorna a estrutura de dados identificada."""
    if current_user.secao == 'CAN':
        return jsonify({'status': 'erro', 'msg': 'Funcionalidade de escaneamento por câmera/OCR não está disponível para a seção CAN.'}), 403

    data = request.json or {}
    texto_bruto = data.get('texto', '')
    
    # Sanitização básica do texto para evitar XSS
    texto_sanitizado = bleach.clean(texto_bruto) if texto_bruto else ''
    
    dados, volumes, erros = parse_ocr_text(texto_sanitizado)
    
    return jsonify({
        'dados_manifesto': dados,
        'volumes': volumes,
        'erros': erros
    })


@app.route('/api/receber_tudo_manifesto', methods=['POST'])
@login_required
def api_receber_tudo():
    """Recebe TODOS os volumes de um manifesto inteiro."""
    data = request.json
    if receber_todos_volumes_web(data.get('manifesto_id'), current_user.nome, secao=current_user.secao):
        return jsonify({'status': 'ok'})
    return jsonify({'status': 'erro'}), 500


@app.route('/api/receber_rapido_volume', methods=['POST'])
@login_required
def api_receber_rapido_volume():
    """Recebe TODAS as caixas de um único volume (atalho)."""
    data = request.json or {}
    secao = data.get('secao') or current_user.secao
    if not pode_operar(current_user, secao):
        return jsonify({'status': 'erro', 'msg': 'Sem permissão para operar nesta seção.'}), 403
    if marcar_recebido_web(data['volume_id'], current_user.nome, secao=secao):
        return jsonify({'status': 'ok'})
    return jsonify({'status': 'erro', 'msg': 'Falha ao receber volume.'}), 500


@app.route('/api/manifesto/<int:id>/volumes', methods=['GET'])
@login_required
def api_listar_volumes_manifesto(id):
    secao_param = request.args.get('secao', current_user.secao).upper()
    volumes = listar_volumes_detalhado(id, secao=secao_param)
    return jsonify([dict(v) for v in volumes])


@app.route('/api/adicionar_extra_conferencia', methods=['POST'])
@login_required
def api_adicionar_extra_conferencia():
    """Adiciona volume extra (Extramanifesto) durante conferência."""
    data = request.json
    try:
        if not pode_operar(current_user, current_user.secao):
            return jsonify({'status': 'erro', 'msg': 'Sem permissão para adicionar extramanifesto nesta seção.'}), 403

        # Determinar destinatário e destino_extra
        if current_user.secao == 'TSRE':
            destinatario = 'PAMALS'
            destino_extra = None
        else:
            # CAN: destino escolhido pelo usuário no modal
            destino_raw = data.get('destino', 'PAMA-LS').strip().upper()
            if destino_raw == 'PAMA-LS':
                destinatario = 'PAMALS'
                destino_extra = 'PAMA-LS'
            else:
                # Destino OUTRO: não aparece para a TSRE
                outro_texto = data.get('destino_outro', 'OUTRO').strip() or 'OUTRO'
                destinatario = outro_texto.upper()
                destino_extra = f'OUTRO:{outro_texto}'

        adicionar_volume(
            manifesto_id=data['manifesto_id'],
            remetente=data.get('remetente', 'DESCONHECIDO'),
            destinatario=destinatario,
            numero_volume=data['numero_volume'],
            quantidade_exp=int(data['quantidade']),
            secao_origem=current_user.secao,
            peso=0.0, cubagem=0.0, prioridade="EXTRA",
            tipo_material="VOLUME EXTRA", embalagem="CAIXA",
            secao_extra=current_user.secao,
            destino_extra=destino_extra
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
        if not pode_operar(current_user, current_user.secao):
            return jsonify({'status': 'erro', 'msg': 'Sem permissão para adicionar extramanifesto.'}), 403

        vol_id = adicionar_volume(
            data['manifesto_id'], data['remetente'], "PAMALS" if current_user.secao == 'TSRE' else "GERAL",
            data['numero_volume'], int(data['quantidade']),
            secao_origem=current_user.secao,
            peso=0.0, cubagem=0.0, prioridade="EXTRA",
            tipo_material="VOLUME EXTRA", embalagem="CAIXA",
            secao_extra=current_user.secao
        )
        marcar_recebido_web(vol_id, current_user.nome, secao=current_user.secao)
        return jsonify({'status': 'ok', 'msg': 'Adicionado e recebido!'})
    except Exception as e:
        return jsonify({'status': 'erro', 'msg': str(e)}), 500


@app.route('/api/receber', methods=['POST'])
@login_required
def api_receber():
    data = request.json or {}
    secao = data.get('secao') or current_user.secao
    if not pode_operar(current_user, secao):
        return jsonify({'status': 'erro', 'msg': 'Sem permissão para operar nesta seção.'}), 403
    if marcar_recebido_web(data['volume_id'], current_user.nome, secao=secao):
        return jsonify({'status': 'ok'})
    return jsonify({'status': 'erro', 'msg': 'Falha ao receber volume.'}), 500


@app.route('/api/desfazer', methods=['POST'])
@login_required
def api_desfazer():
    data = request.json or {}
    vol_id = data.get('volume_id')
    senha = data.get('senha')
    secao = data.get('secao') or current_user.secao
    if not pode_operar(current_user, secao):
        return jsonify({'status': 'erro', 'msg': 'Sem permissão para operar nesta seção.'}), 403
    
    # Exige senha de admin se a conferência do manifesto já foi FINALIZADA para a seção
    finalizado = manifesto_conferencia_finalizada(vol_id, secao)
    
    if finalizado and not is_admin_secao(current_user, secao):
        if not senha or not validar_senha_admin_secao(senha, secao):
            return jsonify({
                'status': 'erro', 
                'msg': f'🔒 A conferência deste manifesto já foi finalizada pelo {secao}. Para desfazer, é necessária a senha de Administrador do {secao} ou Superadmin.'
            }), 403
    elif senha:
        if not validar_senha_admin_secao(senha, secao):
            return jsonify({'status': 'erro', 'msg': 'Senha de Administrador incorreta.'}), 403

    if desfazer_recebimento_web(vol_id, current_user.nome or current_user.username, secao=secao):
        return jsonify({'status': 'ok'})
    return jsonify({'status': 'erro', 'msg': 'Falha ao desfazer recebimento.'}), 500


@app.route('/api/obter_caixas', methods=['POST'])
@login_required
def api_obter_caixas():
    """Retorna caixas com dados completos de conferente individual (REQ-02)."""
    data = request.json or {}
    try:
        secao_param = data.get('secao') or current_user.secao
        caixas = obter_caixas_por_volume(data['volume_id'], secao=secao_param)
        return jsonify([dict(c) for c in caixas])
    except Exception:
        return jsonify([]), 500


@app.route('/api/receber_caixa', methods=['POST'])
@login_required
def api_receber_caixa():
    data = request.json or {}
    secao = data.get('secao') or current_user.secao
    if not pode_operar(current_user, secao):
        return jsonify({'status': 'erro', 'msg': 'Sem permissão para operar nesta seção.'}), 403
    if marcar_caixa_recebida_web(data['volume_id'], data['numero_caixa'], current_user.nome, secao=secao):
        return jsonify({'status': 'ok'})
    return jsonify({'status': 'erro', 'msg': 'Falha ao receber caixa.'}), 500


@app.route('/api/desfazer_caixa', methods=['POST'])
@login_required
def api_desfazer_caixa():
    data = request.json or {}
    vol_id = data.get('volume_id')
    num_caixa = data.get('numero_caixa')
    senha = data.get('senha')
    secao = data.get('secao') or current_user.secao
    if not pode_operar(current_user, secao):
        return jsonify({'status': 'erro', 'msg': 'Sem permissão para operar nesta seção.'}), 403
    
    finalizado = manifesto_conferencia_finalizada(vol_id, secao)
    
    if finalizado and not is_admin_secao(current_user, secao):
        if not senha or not validar_senha_admin_secao(senha, secao):
            return jsonify({
                'status': 'erro', 
                'msg': f'🔒 A conferência deste manifesto já foi finalizada pelo {secao}. Para desfazer, é necessária a senha de Administrador do {secao} ou Superadmin.'
            }), 403
    elif senha:
        if not validar_senha_admin_secao(senha, secao):
            return jsonify({'status': 'erro', 'msg': 'Senha de Administrador incorreta.'}), 403

    if desfazer_caixa_web(vol_id, num_caixa, current_user.nome or current_user.username, secao=secao):
        return jsonify({'status': 'ok'})
    return jsonify({'status': 'erro', 'msg': 'Falha ao desfazer caixa.'}), 500


@app.route('/api/observacao', methods=['POST'])
@login_required
def api_observacao():
    data = request.json or {}
    secao = data.get('secao') or current_user.secao
    if salvar_observacao(data['volume_id'], data['texto'], usuario=current_user.nome, secao=secao):
        return jsonify({'status': 'ok'})
    return jsonify({'status': 'erro'}), 500


# ═══════════════════════════════════════════════════
# REQ-01: APIs de Status Especial
# ═══════════════════════════════════════════════════

@app.route('/api/status_especial', methods=['POST'])
@login_required
def api_status_especial():
    """Marca volume/caixa como RETIRADO POR OUTRA PESSOA ou NÃO RECEBIDO."""
    data = request.json or {}

    volume_id = int(data['volume_id'])
    numero_caixa = data.get('numero_caixa')
    if numero_caixa == '' or numero_caixa is None:
        numero_caixa = None
    novo_status = data.get('status', '')
    retirado_por_raw = data.get('retirado_por', '')
    motivo_nao_recebido_raw = data.get('motivo_nao_recebido', '')
    secao = data.get('secao') or current_user.secao

    if not pode_operar(current_user, secao):
        return jsonify({'status': 'erro', 'msg': 'Sem permissão para operar nesta seção.'}), 403

    # Sanitização XSS
    retirado_por = bleach.clean(retirado_por_raw.strip())[:100] if retirado_por_raw else ''
    motivo_nao_recebido = bleach.clean(motivo_nao_recebido_raw.strip())[:255] if motivo_nao_recebido_raw else ''

    # Validação de status
    status_validos = ['NÃO RECEBIDO', 'RETIRADO POR OUTRA PESSOA']
    if novo_status not in status_validos:
        return jsonify({'status': 'erro', 'msg': 'Status inválido.'}), 400

    # Se RETIRADO, precisa do nome
    if novo_status == 'RETIRADO POR OUTRA PESSOA' and not retirado_por:
        return jsonify({'status': 'erro', 'msg': 'Informe quem retirou o material.'}), 400

    # Se NÃO RECEBIDO, precisa do motivo
    if novo_status == 'NÃO RECEBIDO' and not motivo_nao_recebido:
        return jsonify({'status': 'erro', 'msg': 'Informe o motivo do não recebimento.'}), 400

    if numero_caixa is not None:
        resultado = marcar_status_especial_caixa(
            volume_id, int(numero_caixa), novo_status,
            current_user.nome, retirado_por or None, motivo_nao_recebido or None, secao=secao
        )
    else:
        resultado = marcar_status_especial_volume(
            volume_id, novo_status, current_user.nome,
            retirado_por or None, motivo_nao_recebido or None, secao=secao
        )

    if resultado:
        return jsonify({'status': 'ok'})
    return jsonify({'status': 'erro', 'msg': 'Falha ao processar.'}), 500


@app.route('/api/usuarios_lista', methods=['GET'])
@login_required
def api_usuarios_lista():
    """Retorna lista de usuários para dropdown de 'Retirado por' (legado)."""
    return jsonify(listar_usuarios_ativos())


# ═══════════════════════════════════════════════════
# REQ-02 / Observações Manuais & Info Fixas (v4)
# ═══════════════════════════════════════════════════

@app.route('/api/volume/<int:vol_id>/observacoes', methods=['GET'])
@login_required
def api_listar_obs_manuais(vol_id):
    """Retorna os comentários manuais, info fixas e histórico de caixas do volume."""
    secao_req = request.args.get('secao', current_user.secao).upper()
    if secao_req not in ['TSRE', 'CAN']:
        secao_req = current_user.secao
    comentarios = listar_observacoes_manuais(vol_id)
    info_fixas = obter_info_fixas_volume(vol_id, secao=secao_req)
    caixas = obter_caixas_por_volume(vol_id, secao=secao_req)
    
    # Detalhar caixas para exibir na listagem
    caixas_detalhadas = []
    for cx in caixas:
        caixas_detalhadas.append({
            'numero_caixa': cx['numero_caixa'],
            'status': cx['status'],
            'usuario_conferente': cx['usuario_conferente'] or '-',
            'data_hora_recepcao': cx['data_hora_recepcao'] or '-',
            'retirado_por': cx['retirado_por'] or '',
            'motivo_nao_recebido': cx['motivo_nao_recebido'] or ''
        })
        
    # Formatar timestamps dos comentários para exibição (BRT)
    for c in comentarios:
        c['timestamp_formatado'] = formatar_brt(c['timestamp'])
        
    return jsonify({
        'comentarios': comentarios,
        'info_fixas': {
            'status': info_fixas['status'] if info_fixas else 'NÃO RECEBIDO',
            'retirado_por': (info_fixas['retirado_por'] if info_fixas else '') or '',
            'motivo_nao_recebido': (info_fixas['motivo_nao_recebido'] if info_fixas else '') or ''
        },
        'caixas': caixas_detalhadas
    })


@app.route('/api/observacao_manual/adicionar', methods=['POST'])
@login_required
def api_adicionar_obs_manual():
    """Adiciona um comentário manual do conferente logado."""
    data = request.json
    vol_id = int(data['volume_id'])
    texto = bleach.clean(data['texto'].strip())
    
    if not texto:
        return jsonify({'status': 'erro', 'msg': 'O texto do comentário não pode ser vazio.'}), 400
        
    usuario_nome = current_user.nome or current_user.username
    if adicionar_observacao_manual(vol_id, texto, usuario_nome, secao=current_user.secao):
        return jsonify({'status': 'ok'})
    return jsonify({'status': 'erro', 'msg': 'Falha ao salvar comentário.'}), 500


@app.route('/api/observacao_manual/excluir', methods=['POST'])
@login_required
def api_excluir_obs_manual():
    """Exclui um comentário. Apenas o autor ou admin têm permissão."""
    data = request.json
    obs_id = int(data['observacao_id'])
    
    sucesso, msg = excluir_observacao_manual(obs_id, current_user.nome, current_user.role)
    if sucesso:
        return jsonify({'status': 'ok'})
    return jsonify({'status': 'erro', 'msg': msg}), 403


@app.route('/api/volume/info_fixas/atualizar', methods=['POST'])
@login_required
def api_atualizar_info_fixas():
    """Edita dados de controle fixos. Requer validação de senha do administrador."""
    data = request.json
    vol_id = int(data['volume_id'])
    retirado_por = bleach.clean(data.get('retirado_por', '').strip())
    motivo = bleach.clean(data.get('motivo_nao_recebido', '').strip())
    senha_admin = data.get('senha_admin', '')

    # Validação com função de admin por seção
    if not validar_senha_admin_secao(senha_admin, current_user.secao):
        return jsonify({'status': 'erro', 'msg': 'Senha de administrador incorreta ou sem permissão.'}), 403

    if atualizar_info_fixas_volume(vol_id, retirado_por or None, motivo or None, current_user.nome, secao=current_user.secao):
        return jsonify({'status': 'ok'})
    return jsonify({'status': 'erro', 'msg': 'Falha ao atualizar dados de controle.'}), 500


# Importação para garantir que o sync rode se necessário ao iniciar
try:
    import sheets_sync
except Exception:
    pass

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)