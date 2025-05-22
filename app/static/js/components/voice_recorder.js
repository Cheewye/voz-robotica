export class VoiceRecorder {
    constructor() {
        this.recorder = null;
        this.audioChunks = [];
        this.stream = null;
        this.isRecording = false;
        this.startTime = null;
        this.mimeType = null;
    }

    async initMediaRecorder() {
        console.log('Inicializando MediaRecorder...');
        try {
            if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
                throw new Error('La API MediaDevices no está disponible. Usa un navegador moderno con HTTPS.');
            }

            console.log('Verificando permisos de micrófono...');
            const permissionStatus = await navigator.permissions.query({ name: 'microphone' });
            console.log('Estado del permiso:', permissionStatus.state);

            if (permissionStatus.state === 'denied') {
                throw new Error('El acceso al micrófono está denegado. Habilítalo en la configuración del navegador.');
            }

            // Enumerar dispositivos antes de getUserMedia
            console.log('Enumerando dispositivos de audio antes de getUserMedia...');
            const devices = await navigator.mediaDevices.enumerateDevices();
            const audioDevices = devices.filter(device => device.kind === 'audioinput');
            console.log('Dispositivos de audio encontrados:', audioDevices);
            audioDevices.forEach(device => {
                console.log(`Dispositivo: ${device.label}, ID: ${device.deviceId}, Tipo: ${device.kind}`);
            });
            if (audioDevices.length === 0) {
                console.error('No se encontraron dispositivos de audio antes de getUserMedia.');
                throw new Error('No se encontraron dispositivos de audio antes de getUserMedia.');
            }

            console.log('Solicitando acceso al micrófono con dispositivo predeterminado...');
            try {
                // Especificar el dispositivo predeterminado
                this.stream = await navigator.mediaDevices.getUserMedia({ 
                    audio: { 
                        deviceId: { ideal: 'default' },
                        autoGainControl: true,
                        echoCancellation: true,
                        noiseSuppression: true
                    }
                });
                console.log('Stream de audio obtenido:', {
                    id: this.stream.id,
                    active: this.stream.active,
                    tracks: this.stream.getAudioTracks()
                });
                if (!this.stream.active) {
                    console.error('El stream de audio no está activo.');
                    throw new Error('El stream de audio no está activo.');
                }
            } catch (error) {
                console.error('Error detallado:', {
                    name: error.name,
                    message: error.message,
                    stack: error.stack
                });
                throw new Error(`Error al acceder al micrófono: ${error.message}`);
            }

            const audioTracks = this.stream.getAudioTracks();
            console.log('Pistas de audio en el stream:', audioTracks);
            if (audioTracks.length === 0) {
                console.error('No se encontraron pistas de audio en el stream.');
                throw new Error('No se encontraron pistas de audio en el stream.');
            }

            let mimeType = 'audio/webm;codecs=opus';
            if (!MediaRecorder.isTypeSupported(mimeType)) {
                console.log('Formato webm/opus no soportado, intentando audio/wav');
                mimeType = 'audio/wav';
                if (!MediaRecorder.isTypeSupported(mimeType)) {
                    console.log('Formato wav no soportado, intentando audio/mp3');
                    mimeType = 'audio/mp3';
                    if (!MediaRecorder.isTypeSupported(mimeType)) {
                        console.error('Ningún formato de audio compatible encontrado.');
                        throw new Error('Ningún formato de audio compatible encontrado.');
                    }
                }
            }
            this.mimeType = mimeType;
            this.recorder = new MediaRecorder(this.stream, { mimeType });
            console.log('MediaRecorder inicializado con mimeType:', mimeType);

            this.recorder.ondataavailable = (event) => {
                if (event.data.size > 0) {
                    this.audioChunks.push(event.data);
                    console.log('Datos de audio recibidos:', event.data.size);
                }
            };

            this.recorder.onstop = () => {
                console.log('Grabación detenida');
            };

            this.recorder.onerror = (event) => {
                console.error('Error en MediaRecorder:', event.error);
                this.recorder = null;
            };
        } catch (error) {
            console.error('Error al inicializar MediaRecorder:', error);
            throw error;
        }
    }

    async startRecording() {
        console.log('startRecording llamado, estado actual:', this.recorder ? this.recorder.state : 'sin recorder');
        try {
            if (!this.recorder || !this.stream || !this.stream.active) {
                console.log('Recorder o stream no válidos, reinicializando...');
                await this.initMediaRecorder();
            }

            const audioTracks = this.stream.getAudioTracks();
            if (audioTracks.length === 0) {
                console.error('No hay pistas de audio en el stream.');
                throw new Error('No hay pistas de audio en el stream.');
            }

            if (this.isRecording || this.recorder.state === 'recording') {
                console.log('Grabación ya en curso');
                return;
            }

            this.audioChunks = [];
            this.recorder.start();
            console.log('Iniciando grabación...');
            this.isRecording = true;
            this.startTime = Date.now();
        } catch (error) {
            console.error('Error al iniciar la grabación:', error);
            throw error;
        }
    }

    stopRecording() {
        console.log('stopRecording llamado, estado actual:', this.recorder ? this.recorder.state : 'sin recorder');
        if (!this.recorder) {
            throw new Error('El grabador no está inicializado.');
        }

        if (this.recorder.state !== 'recording') {
            console.log('No hay grabación activa');
            return;
        }

        const elapsedTime = Date.now() - this.startTime;
        const minRecordingTime = 2000;

        const finalizeRecording = () => {
            this.recorder.stop();
            console.log('Deteniendo grabación...');
            this.isRecording = false;
            console.log('Tamaño de audioChunks al detener:', this.audioChunks.length);

            if (this.stream && this.stream.active) {
                this.stream.getTracks().forEach(track => {
                    track.stop();
                    console.log('Pista de audio detenida:', track.kind);
                });
                this.stream = null;
                console.log('Stream de audio liberado');
            }
        };

        if (elapsedTime < minRecordingTime) {
            const remainingTime = minRecordingTime - elapsedTime;
            setTimeout(finalizeRecording, remainingTime);
        } else {
            finalizeRecording();
        }
    }

    getAudioBlob() {
        if (this.audioChunks.length === 0) {
            console.error('No hay datos de audio para crear el Blob.');
            throw new Error('No hay datos de audio grabados.');
        }
        return new Blob(this.audioChunks, { type: this.mimeType || 'audio/webm' });
    }
}