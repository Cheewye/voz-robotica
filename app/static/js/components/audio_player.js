export class AudioPlayer {
    constructor() {
        this.audioElement = document.createElement('audio');
        this.isReadyToPlay = false;
        // Habilitar reproducción tras la primera interacción
        document.addEventListener('click', () => this.isReadyToPlay = true, { once: true });
        document.addEventListener('touchstart', () => this.isReadyToPlay = true, { once: true });
    }

    async reproducirAudio(audioBlob) {
        if (!this.isReadyToPlay) {
            console.warn('Esperando interacción del usuario para reproducir audio');
            return;
        }
        try {
            const audioUrl = URL.createObjectURL(audioBlob);
            this.audioElement.src = audioUrl;
            await this.audioElement.play();
            this.audioElement.onended = () => URL.revokeObjectURL(audioUrl);
        } catch (error) {
            console.error('Error al reproducir el audio:', error);
            throw new Error('Error al reproducir el audio: ' + error.message);
        }
    }
}