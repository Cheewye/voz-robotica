export class MessageManager {
    agregarMensaje(remitente, mensaje, id = null, currentLanguage) {
        const historial = document.getElementById('historial');
        const mensajeDiv = document.createElement('div');
        mensajeDiv.classList.add('mensaje', remitente);
        if (id) mensajeDiv.id = id;
        mensajeDiv.textContent = mensaje;
        historial.appendChild(mensajeDiv);
        historial.scrollTop = historial.scrollHeight;
    }

    mostrarError(error, currentLanguage) {
        const errorMessage = error.message || error.toString();
        this.agregarMensaje('error', errorMessage, null, currentLanguage);
    }

    agregarMensajeInicial(currentLanguage) {
        const translations = { 'pt': 'Aperta o botão vermelho e solta' /* ... */ };
        this.agregarMensaje('sistema', translations[currentLanguage], null, currentLanguage);
    }
}