import { AudioRecorder } from '/static/js/components/audio_recorder.js';
import { TranscriptionService } from '/static/js/components/transcription_service.js';
import { ApiClient } from '/static/js/components/api_client.js';
import { AudioPlayer } from '/static/js/components/audio_player.js';
import { UIManager } from '/static/js/components/ui_manager.js';

class VoiceAssistantApp {
    constructor() {
        this.audioRecorder = new AudioRecorder(this);
        this.transcriptionService = new TranscriptionService();
        this.apiClient = new ApiClient('pt');
        this.audioPlayer = new AudioPlayer();
        this.uiManager = new UIManager();
        this.currentLanguage = 'pt';
        this.currentVoice = 'pt-BR-YaraNeural';
        this.isInitialized = false;
        this.hasRequestedPermission = false;
        this.isRecording = false;
        this.isStarting = false;

        this.languageToVoice = {
            'PT-BR': 'pt-BR-YaraNeural',
            'EN-US': 'en-US-JennyNeural',
            'ES-US': 'es-AR-DaniaNeural',
            'ES-ES': 'es-AR-DaniaNeural',
            'FR-FR': 'fr-FR-DeniseNeural',
            'IT-IT': 'it-IT-IsabellaNeural'
        };

        window.addEventListener('beforeunload', () => {
            this.isRecording = false;
            this.isStarting = false;
            this.isInitialized = false;
            this.hasRequestedPermission = false;
        });

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
            this.isRecording = false;
            this.isStarting = false;
            this.isInitialized = false;
            this.hasRequestedPermission = false;
            this.uiManager.init(this.currentLanguage);
            this.uiManager.agregarMensaje('sistema', {
                'pt': 'Aperta o botón vermelho e solta',
                'en': 'Press the red button and release',
                'es': 'Presiona el botón rojo y suelta',
                'fr': 'Appuyez sur le bouton rouge et relâchez',
                'it': 'Premi il pulsante rosso e rilascia'
            }[this.currentLanguage]);
        } catch (error) {
            console.error('Error al inicializar:', error);
            this.uiManager.mostrarError('Error al inicializar: ' + error.message);
        }
    }

    async requestMicrophonePermission() {
        if (this.hasRequestedPermission) {
            console.log('Permiso ya solicitado, omitiendo...');
            return this.isInitialized;
        }
        try {
            console.log('Solicitando permiso para el micrófono...');
            const permissionStatus = await navigator.permissions.query({ name: 'microphone' });
            console.log('Estado del permiso del micrófono:', permissionStatus.state);
            if (permissionStatus.state === 'denied') {
                throw new Error('Permiso del micrófono denegado. Por favor, habilita el micrófono en la configuración del navegador.');
            }
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            console.log('Permiso para el micrófono concedido');
            stream.getTracks().forEach(track => track.stop());
            this.hasRequestedPermission = true;
            await this.audioRecorder.initMediaRecorder();
            this.isInitialized = true;
            console.log('MediaRecorder inicializado');
            return true;
        } catch (error) {
            if (error.name === 'NotFoundError') {
                console.error('No se encontró un dispositivo de micrófono:', error);
                this.uiManager.mostrarError('No se encontró un micrófono. Por favor, conecta un micrófono y recarga la página.');
            } else {
                console.error('Error al solicitar permiso para el micrófono:', error);
                this.uiManager.mostrarError('Error al solicitar el micrófono: ' + error.message);
            }
            return false;
        }
    }

    updateSphereState(state) {
        const sphere = document.getElementById('sphere');
        if (sphere) {
            sphere.classList.remove('recording', 'releasing', 'responding');
            if (state) {
                sphere.classList.add(state);
                console.log(`Clase ${state} aplicada a esfera`);
            }
        } else {
            console.error('Esfera no encontrada al actualizar estado');
        }
    }

    async startRecording() {
        if (this.isRecording) {
            console.log('Grabación ya en curso, ignorando nuevo intento...');
            return;
        }
        if (this.isStarting) {
            console.log('Inicialización de grabación en curso, ignorando nuevo intento...');
            return;
        }
        this.isStarting = true;
        this.updateSphereState('recording');
        try {
            if (!this.isInitialized) {
                const initialized = await this.requestMicrophonePermission();
                if (!initialized) {
                    console.error('No se puede iniciar grabación: VoiceAssistant no inicializado');
                    this.uiManager.mostrarError('Por favor, permite el acceso al micrófono y recarga la página');
                    this.isStarting = false;
                    this.updateSphereState(null);
                    return;
                }
            }
            console.log('Iniciando grabación...');
            await this.audioRecorder.startRecording();
            this.isRecording = true;
        } catch (error) {
            console.error('Error al iniciar grabación:', error);
            this.uiManager.mostrarError('Error al iniciar grabación: ' + error.message);
            this.isRecording = false;
            this.isStarting = false;
            this.updateSphereState(null);
        } finally {
            this.isStarting = false;
        }
    }

    async stopRecording() {
        if (!this.isRecording) {
            console.log('No hay grabación activa para detener...');
            return;
        }
        if (!this.isInitialized) {
            console.error('No se puede detener grabación: VoiceAssistant no inicializado');
            this.uiManager.mostrarError('Por favor, permite el acceso al micrófono y recarga la página');
            return;
        }
        try {
            console.log('Deteniendo grabación...');
            await this.audioRecorder.stopRecording();
            this.isRecording = false;
            this.updateSphereState('releasing');
        } catch (error) {
            console.error('Error al detener grabación:', error);
            this.uiManager.mostrarError('Error al detener grabación: ' + error.message);
            this.isRecording = false;
        }
    }

    async procesarGrabacion(audioBlob) {
        try {
            if (!audioBlob) {
                throw new Error('No se capturó audio, intenta de nuevo');
            }
            console.log('Procesando audioBlob:', audioBlob);
            const result = await this.transcriptionService.transcribe(audioBlob);
            const texto = result.text;
            const languageCode = (result.language_code || 'PT-BR').toUpperCase();
            console.log('Texto transcrito recibido:', texto, 'Idioma detectado:', languageCode);

            this.currentVoice = this.languageToVoice[languageCode] || 'pt-BR-YaraNeural';
            this.currentLanguage = {
                'pt-BR-YaraNeural': 'pt',
                'en-US-JennyNeural': 'en',
                'es-AR-DaniaNeural': 'es',
                'fr-FR-DeniseNeural': 'fr',
                'it-IT-IsabellaNeural': 'it'
            }[this.currentVoice] || 'pt';
            console.log('Asistente cambiada a:', this.currentVoice, 'Idioma:', this.currentLanguage);

            if (!texto) {
                throw new Error('No se transcribió texto, intenta hablar más claro');
            }

            this.uiManager.agregarMensaje('usuario', texto);
            this.uiManager.updateUI();

            this.updateSphereState('responding');
            const position = await this.obtenerUbicacion();
            console.log('Ubicación obtenida:', position.coords.latitude, position.coords.longitude);
            const respuesta = await this.apiClient.obtenerRespuestaIA(texto, position.coords.latitude, position.coords.longitude, this.currentVoice);
            console.log('Respuesta de IA:', respuesta);
            this.uiManager.agregarMensaje('asistente', respuesta);

            console.log('Generando audio para respuesta:', respuesta, 'con voz:', this.currentVoice);
            const audioBlobRespuesta = await this.apiClient.generarAudio(respuesta, this.currentVoice);
            console.log('AudioBlob recibido:', audioBlobRespuesta);
            await this.audioPlayer.reproducirAudio(audioBlobRespuesta);
            console.log('Audio enviado para reproducción');
        } catch (error) {
            console.error('Error al procesar grabación:', error);
            this.uiManager.mostrarError('Error al procesar grabación: ' + error.message);
        } finally {
            this.isRecording = false;
            this.isStarting = false;
            this.updateSphereState(null);
        }
    }

    async obtenerUbicacion() {
        return new Promise((resolve, reject) => {
            navigator.geolocation.getCurrentPosition(resolve, reject, { timeout: 10000 });
        });
    }
}

const app = new VoiceAssistantApp();
window.app = app;