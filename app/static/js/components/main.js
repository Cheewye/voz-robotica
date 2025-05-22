import { VoiceRecorder } from './voice_recorder.js';
import { ApiClient } from './api_client.js';
import { UIManager } from './ui_manager.js';

export class VoiceAssistantApp {
    constructor() {
        this.recorder = new VoiceRecorder();
        this.apiClient = new ApiClient();
        this.uiManager = new UIManager();
        this.isResponding = false;
        this.transcriptionInterval = null;

        document.addEventListener('DOMContentLoaded', () => {
            console.log('DOM cargado, iniciando VoiceAssistant...');
            if (window.appInitialized) return;
            window.appInitialized = true;
            this.init();
        });
    }

    async init() {
        console.log('Inicializando VoiceAssistant...');
        try {
            this.uiManager.initUI(
                () => this.startRecording(),
                () => this.stopRecording()
            );
            await this.recorder.initMediaRecorder();
            const recordButton = document.getElementById('btnGrabar');
            if (this.recorder && recordButton) {
                recordButton.disabled = false;
                recordButton.title = '';
                console.log('Botón habilitado después de inicialización exitosa');
            }
            const historial = document.getElementById('historial');
            if (historial && !historial.querySelector('.mensaje.sistema')) {
                this.uiManager.agregarMensajeInicial();
            }
        } catch (error) {
            console.error('Error al inicializar VoiceAssistant:', error);
            this.uiManager.mostrarError('Error al inicializar la aplicación: ' + error.message);
        }
    }

    async startRecording() {
        try {
            await this.recorder.startRecording();
            const recordButton = document.getElementById('btnGrabar');
            recordButton.classList.remove('respuesta');
            recordButton.classList.add('grabando');
        } catch (error) {
            this.uiManager.mostrarError(error);
        }
    }

    async stopRecording() {
        try {
            this.recorder.stopRecording();
            const recordButton = document.getElementById('btnGrabar');
            recordButton.classList.remove('grabando');
            recordButton.classList.add('respuesta');

            setTimeout(async () => {
                await this.procesarGrabacion();
                recordButton.disabled = false;
                console.log('Botón habilitado después de 500ms');
            }, 500);
        } catch (error) {
            this.uiManager.mostrarError(error);
            const recordButton = document.getElementById('btnGrabar');
            recordButton.classList.remove('grabando', 'respuesta');
        }
    }

    async procesarGrabacion() {
        try {
            const audioBlob = this.recorder.getAudioBlob();
            const transcription = await this.apiClient.procesarGrabacion(audioBlob, this.uiManager.currentLanguage);
            this.uiManager.agregarMensaje('usuario', transcription);

            const position = await this.apiClient.obtenerUbicacion();
            console.log('Geolocalización exitosa:', position);
            const lat = position.coords.latitude;
            const lon = position.coords.longitude;
            console.log('Ubicación obtenida: lat=' + lat + ', lon=' + lon);

            const tempMessageId = 'temp-' + Date.now();
            this.uiManager.agregarMensaje('asistente', {
                'pt': 'Processando...',
                'en': 'Processing...',
                'es': 'Procesando...',
                'fr': 'Traitement...',
                'it': 'Elaborazione...'
            }[this.uiManager.currentLanguage], tempMessageId);

            console.log('Enviando a /ask-ai: texto=' + transcription + ', lat=' + lat + ', lon=' + lon);
            const respuesta = await this.apiClient.obtenerRespuestaIA(transcription, lat, lon, this.uiManager.currentLanguage);
            console.log('Respuesta de /ask-ai:', respuesta);

            await this.uiManager.mostrarRespuestaProgresiva(respuesta, tempMessageId);

            const tempMessageElement = document.getElementById(tempMessageId);
            if (tempMessageElement) {
                tempMessageElement.id = '';
            }

            const recordButton = document.getElementById('btnGrabar');
            recordButton.classList.remove('respuesta', 'grabando');

            await this.apiClient.reproducirAudio(respuesta, this.uiManager.currentLanguage);
        } catch (error) {
            console.error('Error al procesar grabación:', error);
            this.uiManager.mostrarError(error);
            const recordButton = document.getElementById('btnGrabar');
            recordButton.classList.remove('grabando', 'respuesta');
        }
    }
}

// Inicializar la aplicación
const app = new VoiceAssistantApp();