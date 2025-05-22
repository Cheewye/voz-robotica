class VoiceAssistant {
    constructor() {
        this.recorder = null;
        this.stream = null;
        this.audioChunks = [];
        this.isRecording = false;
        this.init(); // Llamamos a un método de inicialización
    }

    async init() {
        try {
            await this.initMediaRecorder(); // Primero el micrófono
            this.initEventListeners();      // Luego los eventos
        } catch (error) {
            console.error('Error al inicializar:', error);
            alert('Error al iniciar el asistente: ' + error.message);
        }
    }

    async initMediaRecorder() {
        try {
            console.log('Solicitando acceso al micrófono...');
            this.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            console.log('Stream obtenido:', this.stream);
            this.recorder = new MediaRecorder(this.stream);
            console.log('MediaRecorder creado');
            this.recorder.ondataavailable = (event) => {
                console.log('Datos de audio recibidos, tamaño:', event.data.size);
                if (event.data.size > 0) this.audioChunks.push(event.data);
            };
            this.recorder.onstop = () => {
                console.log('Grabación detenida, enviando al servidor...');
                this.sendAudioToServer();
            };
        } catch (error) {
            console.error('Error al acceder al micrófono:', error);
            if (error.name === 'NotAllowedError') {
                alert('Por favor, permite el acceso al micrófono en tu navegador.');
            } else if (error.name === 'NotFoundError') {
                alert('No se detectó un micrófono disponible.');
            } else {
                alert('No se pudo acceder al micrófono: ' + error.message);
            }
        }
    }

    async startRecording() {
        if (this.isRecording) return;
        if (!this.stream || this.stream.getTracks().length === 0) {
            await this.initMediaRecorder();
        }
        console.log('Iniciando grabación...');
        this.audioChunks = [];
        this.recorder.start();
        this.isRecording = true;
        const sphere = document.getElementById('sphere');
        if (sphere) sphere.classList.add('grabando');
    }

    stopRecording() {
        if (!this.recorder || !this.isRecording) return;
        console.log('Deteniendo grabación...');
        this.recorder.stop();
        this.isRecording = false;
        const sphere = document.getElementById('sphere');
        if (sphere) sphere.classList.remove('grabando');
        // Detener el stream para liberar el micrófono
        this.stream.getTracks().forEach(track => track.stop());
    }

    async sendAudioToServer() {
        const audioBlob = new Blob(this.audioChunks, { type: 'audio/webm' });
        const formData = new FormData();
        formData.append('audio', audioBlob, 'recording.webm');

        try {
            const response = await fetch('/transcribe', {
                method: 'POST',
                body: formData
            });
            if (!response.ok) {
                throw new Error('Error del servidor: ' + response.statusText);
            }
            const result = await response.json();
            console.log('Respuesta del servidor:', result.text);
            // Mostrar la transcripción en la interfaz
            const transcriptionDiv = document.getElementById('transcription');
            if (transcriptionDiv) {
                transcriptionDiv.textContent = result.text;
            } else {
                console.warn('Elemento con id "transcription" no encontrado');
            }
        } catch (error) {
            console.error('Error al enviar audio:', error);
            alert('No se pudo enviar el audio: ' + error.message);
        }
    }

    initEventListeners() {
        const sphere = document.getElementById('sphere');
        if (!sphere) {
            console.error('Esfera no encontrada en el DOM');
            return;
        }
        // Eventos para escritorio
        sphere.addEventListener('mousedown', () => this.startRecording());
        sphere.addEventListener('mouseup', () => this.stopRecording());
        // Eventos para móviles
        sphere.addEventListener('touchstart', (e) => {
            e.preventDefault();
            this.startRecording();
        }, { passive: false });
        sphere.addEventListener('touchend', (e) => {
            e.preventDefault();
            this.stopRecording();
        }, { passive: false });
    }
}

// Inicializamos el asistente
const assistant = new VoiceAssistant();