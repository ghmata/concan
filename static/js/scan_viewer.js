/**
 * Módulo de Visualização das Páginas Escaneadas (Galeria com Zoom e Swipe) — ConCAN
 * Arquivo: static/js/scan_viewer.js
 */

// Estado Global do Visualizador
let ocrManifestoId = null;
let ocrImagensList = [];
let ocrIndiceAtual = 0;
let ocrZoomScale = 1;
let ocrTranslateX = 0;
let ocrTranslateY = 0;

// Estado do Drag/Swipe
let isDragging = false;
let startX = 0;
let startY = 0;
let initialTranslateX = 0;
let initialTranslateY = 0;
let touchStartX = 0;
let touchEndDate = 0;

// Elementos DOM
const modalGaleriaOCR = document.getElementById('modalGaleriaOCR');
const galeriaLoading = document.getElementById('galeriaLoading');
const galeriaConteudo = document.getElementById('galeriaConteudo');
const galeriaImagem = document.getElementById('galeriaImagem');
const galeriaPaginaIndicador = document.getElementById('galeriaPaginaIndicador');

/**
 * Abre o visualizador de imagens do manifesto escaneado
 */
async function abrirGaleriaEscaneada(manifestoId) {
    ocrManifestoId = manifestoId;
    ocrImagensList = [];
    ocrIndiceAtual = 0;
    
    // Abre o modal do Bootstrap
    const modal = new bootstrap.Modal(modalGaleriaOCR);
    modal.show();
    
    // Exibe loader
    galeriaLoading.classList.remove('d-none');
    galeriaConteudo.classList.add('d-none');
    
    try {
        const resposta = await fetch(`/api/manifesto/${manifestoId}/imagens_escaneadas`);
        if (!resposta.ok) throw new Error("Não foi possível carregar as imagens do manifesto.");
        
        ocrImagensList = await resposta.json();
        if (ocrImagensList.length === 0) {
            alert("Nenhuma imagem arquivada para este manifesto.");
            modal.hide();
            return;
        }
        
        // Exibe a primeira imagem
        carregarImagemIndex(0);
        
        galeriaLoading.classList.add('d-none');
        galeriaConteudo.classList.remove('d-none');
    } catch (err) {
        alert("Erro: " + err.message);
        modal.hide();
    }
}

/**
 * Carrega a imagem no índice especificado
 */
function carregarImagemIndex(index) {
    if (index < 0 || index >= ocrImagensList.length) return;
    
    ocrIndiceAtual = index;
    resetZoom();
    
    const filename = ocrImagensList[index];
    galeriaImagem.src = `/api/manifesto/${ocrManifestoId}/imagem/${filename}`;
    galeriaPaginaIndicador.textContent = `Página ${index + 1} de ${ocrImagensList.length}`;
}

function proximaPagina() {
    if (ocrIndiceAtual < ocrImagensList.length - 1) {
        carregarImagemIndex(ocrIndiceAtual + 1);
    }
}

function paginaAnterior() {
    if (ocrIndiceAtual > 0) {
        carregarImagemIndex(ocrIndiceAtual - 1);
    }
}

/**
 * Funções de Zoom
 */
function zoomImagem(delta) {
    ocrZoomScale = Math.max(0.5, Math.min(3.0, ocrZoomScale + delta));
    aplicarTransformacoes();
}

function resetZoom() {
    ocrZoomScale = 1;
    ocrTranslateX = 0;
    ocrTranslateY = 0;
    aplicarTransformacoes();
}

function aplicarTransformacoes() {
    galeriaImagem.style.transform = `scale(${ocrZoomScale}) translate(${ocrTranslateX}px, ${ocrTranslateY}px)`;
    if (ocrZoomScale > 1) {
        galeriaImagem.style.cursor = 'grab';
    } else {
        galeriaImagem.style.cursor = 'default';
    }
}

/**
 * Eventos de Mouse e Touch para Drag e Swipe
 */
galeriaImagem.addEventListener('mousedown', iniciarDrag);
window.addEventListener('mousemove', realizarDrag);
window.addEventListener('mouseup', finalizarDrag);

galeriaImagem.addEventListener('touchstart', e => {
    if (e.touches.length === 1) {
        touchStartX = e.touches[0].clientX;
        iniciarDrag(e.touches[0]);
    }
});

galeriaImagem.addEventListener('touchmove', e => {
    if (e.touches.length === 1) {
        realizarDrag(e.touches[0]);
    }
});

galeriaImagem.addEventListener('touchend', e => {
    finalizarDrag();
    
    // Swipe Mobile (só funciona se não houver zoom)
    if (ocrZoomScale === 1 && e.changedTouches.length === 1) {
        const touchEndX = e.changedTouches[0].clientX;
        const diffX = touchEndX - touchStartX;
        
        if (Math.abs(diffX) > 60) { // Threshold de 60px para swipe
            if (diffX < 0) {
                proximaPagina();
            } else {
                paginaAnterior();
            }
        }
    }
});

function iniciarDrag(e) {
    if (ocrZoomScale <= 1) return;
    isDragging = true;
    startX = e.clientX;
    startY = e.clientY;
    initialTranslateX = ocrTranslateX;
    initialTranslateY = ocrTranslateY;
    if (galeriaImagem.style.cursor === 'grab') {
        galeriaImagem.style.cursor = 'grabbing';
    }
}

function realizarDrag(e) {
    if (!isDragging) return;
    const dx = e.clientX - startX;
    const dy = e.clientY - startY;
    
    // Ajusta o deslocamento com base no fator de zoom
    ocrTranslateX = initialTranslateX + (dx / ocrZoomScale);
    ocrTranslateY = initialTranslateY + (dy / ocrZoomScale);
    aplicarTransformacoes();
}

function finalizarDrag() {
    isDragging = false;
    if (ocrZoomScale > 1) {
        galeriaImagem.style.cursor = 'grab';
    }
}
