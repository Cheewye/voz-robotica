export class ApiClient {
    constructor(currentLanguage) {
        this.currentLanguage = currentLanguage;
    }

    async obtenerRespuestaIA(texto, lat, lon, voice) {
        try {
            const response = await fetch('/ask-ai', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text: texto, lat, lon, voice })
            });
            if (!response.ok) throw new Error('Error al obtener respuesta de IA: ' + response.statusText);
            const data = await response.json();
            if (data.error) throw new Error(data.error);
            return data.response;
        } catch (error) {
            console.error('Error al obtener respuesta de IA:', error);
            throw error;
        }
    }

    async generarAudio(texto, voice) {
        try {
            const response = await fetch('/speak', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text: texto, voice })
            });
            if (!response.ok) throw new Error('Error al generar audio: ' + response.statusText);
            return await response.blob();
        } catch (error) {
            console.error('Error al generar audio:', error);
            throw error;
        }
    }
}