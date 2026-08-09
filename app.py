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
)
from pdf_extractor import extrair_manifesto_pdf
from ocr_parser import parse_ocr_text

app = Flask(__name__)
app.secret_key = os.environ.get('CONCAN_SECRET_KEY', 'chave_secreta_can_mobile_v3')

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
                user_data['nome_completo'], user_data['role']
            )
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


# ═══════════════════════════════════════════════════
# ROTAS DE GESTÃO DE USUÁRIOS
# ═══════════════════════════════════════════════════

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
    if current_user.role != 'admin':
        return redirect(url_for('index'))
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


@app.route('/escanear', methods=['GET'])
@login_required
def escanear_manifesto():
    """Renderiza a página com o fluxo de escaneamento por câmera e OCR client-side."""
    return render_template('escanear.html')


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
            dados, volumes, erros = extrair_manifesto_pdf(filepath)

            if not dados or not dados.get('numero_manifesto'):
                flash('Falha ao ler PDF.', 'danger')
                return redirect(url_for('novo_manifesto'))

            data_man = datetime.now(BRT).strftime("%d/%m/%Y")

            mid = criar_manifesto(
                dados['numero_manifesto'], data_man,
                dados.get('terminal_origem', 'DESC'),
                dados.get('terminal_destino', 'DESC'),
                dados.get('missao'), dados.get('aeronave'), filepath
            )

            for vol in volumes:
                adicionar_volume(
                    mid, vol['remetente'], vol['destinatario'],
                    vol['numero_volume'], vol['quantidade_expedida'],
                    peso=vol.get('peso_total'), cubagem=vol.get('cubagem'),
                    prioridade=vol.get('prioridade'),
                    tipo_material=vol.get('tipo_material'),
                    embalagem=vol.get('embalagem')
                )

            flash(f'Importado! {len(volumes)} volumes.', 'success')
            return redirect(url_for('index'))
        except Exception as e:
            flash(f'Erro: {str(e)}', 'danger')
            return redirect(url_for('novo_manifesto'))


@app.route('/api/importar_manifesto_ocr', methods=['POST'])
@login_required
def api_importar_manifesto_ocr():
    """Valida, cria e persiste o manifesto e volumes gerados via OCR Mobile, além de arquivar as fotos."""
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
    if current_user.role != 'admin':
        flash("Apenas administradores podem excluir.", "danger")
        return redirect(url_for('index'))

    senha = request.form.get('senha')
    if senha == "pitaco":
        if excluir_manifesto(id):
            flash("Excluído com sucesso!", "success")
        else:
            flash("Erro ao excluir.", "danger")
    else:
        flash("Senha de confirmação incorreta!", "danger")
    return redirect(url_for('index'))


# ═══════════════════════════════════════════════════
# APIs (AJAX)
# ═══════════════════════════════════════════════════

@app.route('/api/busca/manifestos', methods=['POST'])
@login_required
def api_busca_manifestos():
    data = request.json
    res = listar_manifestos(
        data.get('numero'), data.get('status'),
        data.get('data_ini'), data.get('data_fim')
    )
    return jsonify(res)


@app.route('/api/busca/volumes', methods=['POST'])
@login_required
def api_busca_volumes():
    data = request.json
    res = buscar_volumes_geral(data.get('termo', ''))
    return jsonify(res)


@app.route('/api/parse_ocr_text', methods=['POST'])
@login_required
def api_parse_ocr_text():
    """Recebe texto bruto de OCR do cliente e retorna a estrutura de dados identificada."""
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
    if receber_todos_volumes_web(data.get('manifesto_id'), current_user.nome):
        return jsonify({'status': 'ok'})
    return jsonify({'status': 'erro'}), 500


@app.route('/api/receber_rapido_volume', methods=['POST'])
@login_required
def api_receber_rapido_volume():
    """Recebe TODAS as caixas de um único volume (atalho)."""
    data = request.json
    if marcar_recebido_web(data['volume_id'], current_user.nome):
        return jsonify({'status': 'ok'})
    return jsonify({'status': 'erro'}), 500


@app.route('/api/manifesto/<int:id>/volumes', methods=['GET'])
@login_required
def api_listar_volumes_manifesto(id):
    volumes = listar_volumes_detalhado(id)
    return jsonify([dict(v) for v in volumes])


@app.route('/api/adicionar_extra_conferencia', methods=['POST'])
@login_required
def api_adicionar_extra_conferencia():
    """Adiciona volume extra (Extramanifesto) durante conferência."""
    data = request.json
    try:
        adicionar_volume(
            manifesto_id=data['manifesto_id'],
            remetente=data.get('remetente', 'DESCONHECIDO'),
            destinatario="PAMALS",
            numero_volume=data['numero_volume'],
            quantidade_exp=int(data['quantidade']),
            peso=0.0, cubagem=0.0, prioridade="EXTRA",
            tipo_material="VOLUME EXTRA", embalagem="CAIXA"
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
        vol_id = adicionar_volume(
            data['manifesto_id'], data['remetente'], "PAMALS",
            data['numero_volume'], int(data['quantidade']),
            peso=0.0, cubagem=0.0, prioridade="EXTRA",
            tipo_material="VOLUME EXTRA", embalagem="CAIXA"
        )
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
    if desfazer_recebimento_web(data['volume_id'], current_user.nome):
        return jsonify({'status': 'ok'})
    return jsonify({'status': 'erro'}), 500


@app.route('/api/obter_caixas', methods=['POST'])
@login_required
def api_obter_caixas():
    """Retorna caixas com dados completos de conferente individual (REQ-02)."""
    data = request.json
    try:
        caixas = obter_caixas_por_volume(data['volume_id'])
        return jsonify([dict(c) for c in caixas])
    except Exception:
        return jsonify([]), 500


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
    if desfazer_caixa_web(data['volume_id'], data['numero_caixa'], current_user.nome):
        return jsonify({'status': 'ok'})
    return jsonify({'status': 'erro'}), 500


@app.route('/api/observacao', methods=['POST'])
@login_required
def api_observacao():
    data = request.json
    if salvar_observacao(data['volume_id'], data['texto']):
        return jsonify({'status': 'ok'})
    return jsonify({'status': 'erro'}), 500


# ═══════════════════════════════════════════════════
# REQ-01: APIs de Status Especial
# ═══════════════════════════════════════════════════

@app.route('/api/status_especial', methods=['POST'])
@login_required
def api_status_especial():
    """Marca volume/caixa como RETIRADO POR OUTRA PESSOA ou NÃO RECEBIDO."""
    data = request.json

    volume_id = int(data['volume_id'])
    numero_caixa = data.get('numero_caixa')
    if numero_caixa == '':
        numero_caixa = None
    novo_status = data.get('status', '')
    retirado_por_raw = data.get('retirado_por', '')
    motivo_nao_recebido_raw = data.get('motivo_nao_recebido', '')

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
            current_user.nome, retirado_por or None, motivo_nao_recebido or None
        )
    else:
        resultado = marcar_status_especial_volume(
            volume_id, novo_status, current_user.nome,
            retirado_por or None, motivo_nao_recebido or None
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
    comentarios = listar_observacoes_manuais(vol_id)
    info_fixas = obter_info_fixas_volume(vol_id)
    caixas = obter_caixas_por_volume(vol_id)
    
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
        
    if adicionar_observacao_manual(vol_id, texto, current_user.nome):
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

    # Validação rígida com senha de bypass do admin
    if senha_admin not in ["pitaco", "admin123"]:
        return jsonify({'status': 'erro', 'msg': 'Senha de administrador incorreta.'}), 403

    if atualizar_info_fixas_volume(vol_id, retirado_por or None, motivo or None, current_user.nome):
        return jsonify({'status': 'ok'})
    return jsonify({'status': 'erro', 'msg': 'Falha ao atualizar dados de controle.'}), 500


# Importação para garantir que o sync rode se necessário ao iniciar
try:
    import sheets_sync
except Exception:
    pass

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)