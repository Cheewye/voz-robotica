export class TranscriptionService {
    async transcribe(audioBlob) {
        try {
            console.log('Enviando audioBlob al endpoint /transcribe:', audioBlob);
            const formData = new FormData();
            formData.append('audio', audioBlob, 'recording.webm'); // Asegurar nombre de archivo y tipo MIME

            const response = await fetch('https://192.168.1.108:8080/transcribe', {
                method: 'POST',
                body: formData,
                headers: {
                    'Accept': 'application/json'
                }
            });

            if (!response.ok) {
                const errorText = await response.text();
                console.error('Error en /transcribe:', response.status, errorText);
                throw new Error(`Error al transcribir audio: ${response.status} ${errorText}`);
            }

            const result = await response.json();
            console.log('Resultado de transcripción:', result);
            return result; // Espera { text: "...", language_code: "..." }
        } catch (error) {
            console.error('Error al transcribir:', error);
            throw error;
        }
    }
}