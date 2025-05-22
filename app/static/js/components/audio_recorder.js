export class AudioRecorder {
    constructor(app) {
        this.app = app;
        this.recorder = null;
        this.stream = null;
        this.audioChunks = [];
        this.isRecording = false;
        this.isInitialized = false;
    }

    async initMediaRecorder() {
        try {
            console.log('Inicializando MediaRecorder...');
            this.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            console.log('Acceso al micrófono concedido');
            this.recorder = new MediaRecorder(this.stream);
            this.recorder.ondataavailable = (event) => {
                if (event.data.size > 0) {
                    this.audioChunks.push(event.data);
                    console.log('Datos de audio recibidos:', event.data.size);
                }
            };
            this.recorder.onstop = () => {
                console.log('Grabación detenida, procesando audio...');
                const audioBlob = new Blob(this.audioChunks, { type: 'audio/webm' });
                this.audioChunks = [];
                this.app.procesarGrabacion(audioBlob);
            };
            this.isInitialized = true;
            console.log('MediaRecorder inicializado correctamente');
        } catch (error) {
            console.error('Error al inicializar MediaRecorder:', error);
            throw error;
        }
    }

    async startRecording() {
        if (!this.isInitialized) {
            await this.initMediaRecorder();
        }
        if (this.isRecording) {
            console.error('No se puede iniciar grabación: ya grabando');
            throw new Error('Ya grabando');
        }
        if (this.recorder && this.recorder.state === 'recording') {
            console.error('No se puede iniciar grabación: detención pendiente');
            throw new Error('Detención pendiente');
        }
        console.log('Comenzando grabación...');
        this.audioChunks = [];
        this.recorder.start();
        this.isRecording = true;
    }

    async stopRecording() {
        if (!this.isInitialized) {
            console.error('No se puede detener grabación: recorder no inicializado');
            throw new Error('Recorder no inicializado');
        }
        if (!this.isRecording) {
            console.error('No se puede detener grabación: no hay grabación activa');
            throw new Error('No hay grabación activa');
        }
        console.log('Deteniendo grabación...');
        this.recorder.stop();
        this.isRecording = false;
        if (this.stream) {
            this.stream.getTracks().forEach(track => track.stop());
            this.stream = null;
        }
        this.recorder = null;
        this.isInitialized = false;
    }
}