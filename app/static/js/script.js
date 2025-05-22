const history = [];

window.addEventListener('DOMContentLoaded', () => {
    const sphere = document.getElementById('sphere');
    let isRecording = false;

    if (sphere) {
        sphere.addEventListener('click', toggleRecording);
        sphere.addEventListener('touchstart', (e) => {
            e.preventDefault();
            toggleRecording();
        }, { passive: false });

        addToHistory('Sistema', 'UI inicializada correctamente');
    }

    function toggleRecording() {
        if (!isRecording) {
            sphere.classList.add('recording');
            addToHistory('Usuario', 'Grabación iniciada');
            isRecording = true;
            // Llamada a la función de inicio de grabación
            window.app.startRecording();
        } else {
            sphere.classList.remove('recording');
            sphere.classList.add('releasing');
            addToHistory('Usuario', 'Grabación detenida');
            setTimeout(() => {
                sphere.classList.remove('releasing');
            }, 1500);
            isRecording = false;
            // Llamada a la función de detener grabación
            window.app.stopRecording();
        }
    }

    // Función para agregar mensajes al historial
    function addToHistory(sender, message) {
        history.push({ sender, message });
        const historyDiv = document.getElementById('history');
        if (historyDiv) {
            const p = document.createElement('p');
            p.className = sender.toLowerCase();
            p.innerHTML = `<b>${sender}:</b> ${message}`;
            historyDiv.appendChild(p);
            historyDiv.scrollTop = historyDiv.scrollHeight;
        }
    }

    // Exponer la función globalmente
    window.addToHistory = addToHistory;
});