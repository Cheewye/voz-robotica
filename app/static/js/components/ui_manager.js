export class UIManager {
    constructor() {
        this.currentLanguage = 'pt';
    }

    init(language) {
        this.currentLanguage = language;
        const recordButton = document.getElementById('btnGrabar');
        if (recordButton) {
            recordButton.addEventListener('mousedown', () => window.app.startRecording());
            recordButton.addEventListener('mouseup', () => window.app.stopRecording());
            recordButton.addEventListener('touchstart', (e) => {
                e.preventDefault();
                window.app.startRecording();
            }, { passive: false });
            recordButton.addEventListener('touchend', (e) => {
                e.preventDefault();
                window.app.stopRecording();
            }, { passive: false });
        }
        this.updateUI();
    }

    updateUI() {
        const translations = {
            'pt': { 'initial_message': 'Aperta o botão vermelho e solta' },
            'en': { 'initial_message': 'Press the red button and release' },
            'es': { 'initial_message': 'Presiona el botón rojo y suelta' },
            'fr': { 'initial_message': 'Appuyez sur le bouton rouge et relâchez' },
            'it': { 'initial_message': 'Premi il pulsante rosso e rilascia' }
        };
        const mensajeSistema = document.querySelector('.mensaje.sistema');
        if (mensajeSistema) {
            mensajeSistema.textContent = translations[this.currentLanguage].initial_message;
        }
    }

    agregarMensaje(remitente, mensaje, id = null) {
        const historial = document.getElementById('historial');
        if (!historial) return;
        const mensajeDiv = document.createElement('div');
        mensajeDiv.classList.add('mensaje', remitente);
        if (id) mensajeDiv.id = id;
        mensajeDiv.textContent = mensaje;
        historial.appendChild(mensajeDiv);
        historial.scrollTop = historial.scrollHeight;
    }

    mostrarError(error) {
        this.agregarMensaje('error', error.message || error.toString());
    }
}