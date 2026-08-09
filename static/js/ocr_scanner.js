/**
 * Módulo de Controle do Scanner OCR — ConCAN Mobile Client-Side
 * Arquivo: static/js/ocr_scanner.js
 */

// Estado Global do Scanner
let paginasTexto = [];
let paginasImagens = [];
let confiancaAcumulada = 0;
let tesseractWorker = null;
let volumeIdCounter = 0;

// Elementos DOM
const cameraInput = document.getElementById('cameraInput');
const btnCapturar = document.getElementById('btnCapturar');
const imgPreview = document.getElementById('imgPreview');
const scanActions = document.getElementById('scanActions');
const btnProximaPagina = document.getElementById('btnProximaPagina');
const btnFinalizar = document.getElementById('btnFinalizar');
const pageBadge = document.getElementById('pageBadge');
const lblPageNum = document.getElementById('lblPageNum');
const ocrLoading = document.getElementById('ocrLoading');
const ocrStatusTxt = document.getElementById('ocrStatusTxt');
const progressContainer = document.getElementById('progressOCRContainer');
const progressBar = document.getElementById('progressOCRBar');
const progressPercent = document.getElementById('ocrProgressPercent');

// Elementos de Revisão
const secaoCaptura = document.getElementById('secao-captura');
const secaoRevisao = document.getElementById('secao-revisao');
const lowConfidenceAlert = document.getElementById('lowConfidenceAlert');
const lblTotalPaginas = document.getElementById('lblTotalPaginasCapturadas');
const volumesReviewList = document.getElementById('volumesReviewList');

// Inicialização de Handlers
btnCapturar.addEventListener('click', () => cameraInput.click());
cameraInput.addEventListener('change', tratarUploadImagem);
btnProximaPagina.addEventListener('click', prepararProximaPagina);
btnFinalizar.addEventListener('click', finalizarEscaneamento);
document.getElementById('btnSalvarManifesto').addEventListener('click', validarEConfirmar);
document.getElementById('btnConfirmarSalvar').addEventListener('click', enviarDadosManifesto);

/**
 * Inicializa o Tesseract Worker (Lazy Load) com timeout e feedback detalhado
 */
async function obterWorker() {
    if (tesseractWorker) return tesseractWorker;
    
    ocrStatusTxt.textContent = "Carregando motor OCR...";
    ocrLoading.classList.remove('d-none');
    
    const workerPromise = Tesseract.createWorker('por', 1, {
        logger: m => {
            if (!m) return;
            if (m.status === 'loading tesseract core') {
                ocrStatusTxt.textContent = "Carregando motor OCR...";
            } else if (m.status === 'loading language traineddata') {
                const prog = Math.round((m.progress || 0) * 100);
                ocrStatusTxt.textContent = `Baixando modelo de texto (${prog}%)...`;
            } else if (m.status === 'initializing api') {
                ocrStatusTxt.textContent = "Preparando reconhecedor...";
            } else if (m.status === 'recognizing text') {
                const progresso = Math.round((m.progress || 0) * 100);
                progressBar.style.width = `${progresso}%`;
                progressPercent.textContent = `${progresso}%`;
                ocrStatusTxt.textContent = `Lendo texto: ${progresso}%`;
            }
        }
    });

    const timeoutPromise = new Promise((_, reject) => {
        setTimeout(() => reject(new Error("Tempo limite excedido ao carregar motor OCR. Verifique sua conexão com a internet.")), 25000);
    });

    try {
        tesseractWorker = await Promise.race([workerPromise, timeoutPromise]);
        return tesseractWorker;
    } catch (err) {
        tesseractWorker = null;
        throw err;
    } finally {
        ocrLoading.classList.add('d-none');
    }
}

/**
 * Trata o arquivo capturado/carregado pela câmera
 */
async function tratarUploadImagem(e) {
    const arquivo = e.target.files[0];
    if (!arquivo) return;

    btnCapturar.disabled = true;
    ocrLoading.classList.remove('d-none');
    progressContainer.classList.remove('d-none');
    progressBar.style.width = '0%';
    progressPercent.textContent = '0%';
    ocrStatusTxt.textContent = "Processando imagem...";

    try {
        // 1. Comprimir Imagem no Cliente
        const blobComprimido = await comprimirImagem(arquivo);
        paginasImagens.push(blobComprimido);
        
        // Exibir Preview local
        imgPreview.src = URL.createObjectURL(blobComprimido);
        imgPreview.classList.remove('opacity-25');
        pageBadge.classList.remove('d-none');
        lblPageNum.textContent = paginasImagens.length;

        // 2. Rodar OCR
        const worker = await obterWorker();
        ocrLoading.classList.remove('d-none');
        
        const resultado = await worker.recognize(blobComprimido);
        const texto = resultado.data.text;
        const confianca = resultado.data.confidence;
        
        paginasTexto.push(texto);
        confiancaAcumulada += confianca;
        
        // Exibe opções de sequência
        scanActions.classList.remove('d-none');
        btnCapturar.innerHTML = '<i class="bi bi-arrow-repeat me-2"></i>Tirar Foto Novamente';
    } catch (err) {
        alert("Erro ao processar OCR: " + err.message);
        console.error(err);
    } finally {
        ocrLoading.classList.add('d-none');
        progressContainer.classList.add('d-none');
        btnCapturar.disabled = false;
    }
}

/**
 * Comprime a imagem tirada com a câmera usando HTML5 Canvas (resolução max 1920px, JPEG 0.7)
 */
function comprimirImagem(arquivo) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = function(e) {
            const img = new Image();
            img.onload = function() {
                const canvas = document.createElement('canvas');
                let width = img.width;
                let height = img.height;
                const max_size = 1920;

                // Redimensionamento proporcional
                if (width > height) {
                    if (width > max_size) {
                        height *= max_size / width;
                        width = max_size;
                    }
                } else {
                    if (height > max_size) {
                        width *= max_size / height;
                        height = max_size;
                    }
                }

                canvas.width = width;
                canvas.height = height;
                const ctx = canvas.getContext('2d');
                ctx.drawImage(img, 0, 0, width, height);

                canvas.toBlob(blob => {
                    if (blob) resolve(blob);
                    else reject(new Error("Erro ao compactar imagem."));
                }, 'image/jpeg', 0.7);
            };
            img.src = e.target.result;
        };
        reader.onerror = err => reject(err);
        reader.readAsDataURL(arquivo);
    });
}

function prepararProximaPagina() {
    cameraInput.value = '';
    imgPreview.src = "/static/images/icon-192.png";
    imgPreview.classList.add('opacity-25');
    scanActions.classList.add('d-none');
    btnCapturar.innerHTML = '<i class="bi bi-camera-fill me-2"></i>Tirar Foto / Carregar Página';
    cameraInput.click();
}

/**
 * Finaliza o escaneamento e chama o parser do backend via AJAX
 */
async function finalizarEscaneamento() {
    if (paginasTexto.length === 0) return;
    
    ocrStatusTxt.textContent = "Estruturando dados...";
    ocrLoading.classList.remove('d-none');
    
    const textoConsolidado = paginasTexto.join('\n');
    
    try {
        const resposta = await fetch('/api/parse_ocr_text', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ texto: textoConsolidado })
        });
        
        if (!resposta.ok) throw new Error("Erro no parser do backend.");
        
        const parseResult = await resposta.json();
        
        // Transição de Telas
        secaoCaptura.classList.add('d-none');
        secaoRevisao.classList.remove('d-none');
        
        // Confiança Média
        const confiancaMedia = confiancaAcumulada / paginasTexto.length;
        if (confiancaMedia < 60) {
            lowConfidenceAlert.classList.remove('d-none');
            document.querySelectorAll('#secao-revisao input').forEach(el => el.classList.add('campo-nao-identificado'));
        }
        
        lblTotalPaginas.textContent = paginasTexto.length;
        
        // Preencher Campos de Cabeçalho
        preencherCabecalho(parseResult.dados_manifesto);
        
        // Listar Volumes
        volumesReviewList.innerHTML = '';
        parseResult.volumes.forEach(vol => adicionarCardVolume(vol));
        
        if (parseResult.volumes.length === 0) {
            document.getElementById('fallbackManualAlert').classList.remove('d-none');
        }
    } catch (err) {
        alert("Falha ao estruturar manifesto: " + err.message);
    } finally {
        ocrLoading.classList.add('d-none');
    }
}

function preencherCabecalho(dados) {
    const numMan = document.getElementById('revNumeroManifesto');
    numMan.value = dados.numero_manifesto || '';
    if (!dados.numero_manifesto) {
        numMan.classList.add('campo-nao-identificado');
    } else {
        numMan.classList.remove('campo-nao-identificado');
    }
    
    document.getElementById('revOrigem').value = dados.terminal_origem || '';
    document.getElementById('revDestino').value = dados.terminal_destino || '';
    document.getElementById('revMissao').value = dados.missao || '';
    document.getElementById('revAeronave').value = dados.aeronave || '';
}

function adicionarCardVolume(vol = {}) {
    const id = ++volumeIdCounter;
    const card = document.createElement('div');
    card.className = `card vol-review-card p-3 mb-2 id-vol-card-${id}`;
    card.innerHTML = `
        <div class="row g-2 align-items-center">
            <div class="col-md-4 col-12">
                <label class="form-label small fw-bold text-muted mb-1">Volume (Número)</label>
                <input type="text" class="form-control form-control-sm val-num-vol fw-bold" value="${vol.numero_volume || ''}" placeholder="Ex: 240101010101/0001">
            </div>
            <div class="col-md-3 col-6">
                <label class="form-label small fw-bold text-muted mb-1">Remetente</label>
                <select class="form-select form-select-sm val-remetente">
                    <option value="DESCONHECIDO" ${vol.remetente === 'DESCONHECIDO' ? 'selected' : ''}>DESCONHECIDO</option>
                    <option value="CABW" ${vol.remetente === 'CABW' ? 'selected' : ''}>CABW</option>
                    <option value="CABE" ${vol.remetente === 'CABE' ? 'selected' : ''}>CABE</option>
                    <option value="BACO" ${vol.remetente === 'BACO' ? 'selected' : ''}>BACO</option>
                    <option value="BACG" ${vol.remetente === 'BACG' ? 'selected' : ''}>BACG</option>
                    <option value="BAGL" ${vol.remetente === 'BAGL' ? 'selected' : ''}>BAGL</option>
                    <option value="CTLA" ${vol.remetente === 'CTLA' ? 'selected' : ''}>CTLA</option>
                    <option value="CLTA" ${vol.remetente === 'CLTA' ? 'selected' : ''}>CLTA</option>
                    <option value="BAAN" ${vol.remetente === 'BAAN' ? 'selected' : ''}>BAAN</option>
                    <option value="BASP" ${vol.remetente === 'BASP' ? 'selected' : ''}>BASP</option>
                    <option value="BANT" ${vol.remetente === 'BANT' ? 'selected' : ''}>BANT</option>
                </select>
            </div>
            <div class="col-md-2 col-4">
                <label class="form-label small fw-bold text-muted mb-1">Caixas</label>
                <input type="number" class="form-control form-control-sm val-qtd" min="1" value="${vol.quantidade_expedida || 1}">
            </div>
            <div class="col-md-2 col-4 d-none d-md-block">
                <label class="form-label small fw-bold text-muted mb-1">Prioridade</label>
                <input type="text" class="form-control form-control-sm val-prioridade" maxlength="2" value="${vol.prioridade || '00'}">
            </div>
            <div class="col-md-1 col-2 text-end">
                <label class="form-label d-block mb-1">&nbsp;</label>
                <button type="button" class="btn btn-outline-danger btn-sm border-0" onclick="removerCardVolume(${id})" title="Remover volume">
                    <i class="bi bi-trash-fill fs-5"></i>
                </button>
            </div>
        </div>
    `;
    volumesReviewList.appendChild(card);
    
    const numVolInput = card.querySelector('.val-num-vol');
    if (!vol.numero_volume || vol.remetente === 'DESCONHECIDO') {
        card.classList.add('campo-nao-identificado');
    }
    
    numVolInput.addEventListener('input', e => {
        if (/^\d{12}\/\d{4}$/.test(e.target.value)) {
            card.classList.remove('campo-nao-identificado');
        } else {
            card.classList.add('campo-nao-identificado');
        }
    });
}

function adicionarVolumeManual() {
    adicionarCardVolume({
        numero_volume: '',
        remetente: 'DESCONHECIDO',
        quantidade_expedida: 1,
        prioridade: '00'
    });
}

function removerCardVolume(id) {
    const card = document.querySelector(`.id-vol-card-${id}`);
    if (card) card.remove();
}

function voltarParaCaptura() {
    secaoRevisao.classList.add('d-none');
    secaoCaptura.classList.remove('d-none');
}

/**
 * Valida o formulário antes de abrir a confirmação
 */
function validarEConfirmar() {
    const numeroMan = document.getElementById('revNumeroManifesto').value.trim();
    const infoError = document.getElementById('revNumeroManifestoInfo');
    
    if (!/^\d{12}$/.test(numeroMan)) {
        infoError.classList.remove('d-none');
        document.getElementById('revNumeroManifesto').focus();
        return;
    }
    infoError.classList.add('d-none');
    
    const cards = document.querySelectorAll('.vol-review-card');
    let erros = 0;
    
    cards.forEach(card => {
        const numVol = card.querySelector('.val-num-vol').value.trim();
        const qtd = parseInt(card.querySelector('.val-qtd').value) || 0;
        
        if (!/^\d{12}\/\d{4}$/.test(numVol) || qtd < 1) {
            card.classList.add('campo-nao-identificado');
            erros++;
        }
    });
    
    if (erros > 0) {
        alert("Corrija os volumes destacados em amarelo antes de prosseguir. O número do volume precisa estar no formato: 12digitos/4digitos (ex: 240101010101/0001).");
        return;
    }
    
    // Abre modal de confirmação
    const modal = new bootstrap.Modal(document.getElementById('modalConfirmarImportacao'));
    modal.show();
}

/**
 * Envia o payload multipart para a API de gravação do backend
 */
async function enviarDadosManifesto() {
    const btnConfirmar = document.getElementById('btnConfirmarSalvar');
    btnConfirmar.disabled = true;
    btnConfirmar.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Salvando...';

    const modalEl = document.getElementById('modalConfirmarImportacao');
    const modal = bootstrap.Modal.getInstance(modalEl);

    // Coleta Cabeçalho
    const manifesto_dados = {
        numero_manifesto: document.getElementById('revNumeroManifesto').value.trim(),
        terminal_origem: document.getElementById('revOrigem').value.trim() || 'DESC',
        terminal_destino: document.getElementById('revDestino').value.trim() || 'DESC',
        missao: document.getElementById('revMissao').value.trim() || '',
        aeronave: document.getElementById('revAeronave').value.trim() || '',
        total_paginas: paginasImagens.length
    };

    // Coleta Volumes
    const volumes = [];
    document.querySelectorAll('.vol-review-card').forEach(card => {
        volumes.push({
            numero_volume: card.querySelector('.val-num-vol').value.trim(),
            remetente: card.querySelector('.val-remetente').value,
            quantidade_expedida: parseInt(card.querySelector('.val-qtd').value) || 1,
            prioridade: card.querySelector('.val-prioridade') ? card.querySelector('.val-prioridade').value.trim() : '00'
        });
    });

    // Monta o FormData multipart
    const formData = new FormData();
    formData.append('manifesto_dados', JSON.stringify(manifesto_dados));
    formData.append('volumes', JSON.stringify(volumes));

    // Anexa fotos comprimidas
    paginasImagens.forEach((blob, index) => {
        formData.append('imagens', blob, `pagina_${index + 1}.jpg`);
    });

    try {
        const resposta = await fetch('/api/importar_manifesto_ocr', {
            method: 'POST',
            body: formData
        });

        const resJson = await resposta.json();
        
        if (resposta.ok) {
            modal.hide();
            // Salva feedback de sucesso para a tela principal
            sessionStorage.setItem('concan_flash_success', `Manifesto ${manifesto_dados.numero_manifesto} importado com sucesso! ${volumes.length} volume(s) cadastrado(s).`);
            window.location.href = '/';
        } else {
            alert("Erro ao importar manifesto: " + (resJson.msg || "Erro desconhecido"));
            btnConfirmar.disabled = false;
            btnConfirmar.textContent = 'Confirmar e Salvar';
        }
    } catch (err) {
        alert("Erro de conexão com o servidor: " + err.message);
        btnConfirmar.disabled = false;
        btnConfirmar.textContent = 'Confirmar e Salvar';
    }
}
