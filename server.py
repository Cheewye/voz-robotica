from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import logging
import subprocess
import whisper
import requests

app = Flask(__name__, static_folder='static', template_folder='.')
CORS(app)
logging.basicConfig(level=logging.DEBUG)

# Configura tu clave API de xAI
XAI_API_KEY = "xai-VVrsTIz6RgagtnZYtvBFQZhj74LaG64jYJMt6NkFL2MYzeB8Jrsy9seu5ljBqF9o2t4HZQmSY7J96sXu"  # Reemplaza con tu clave API

@app.route('/')
def serve_index():
    return send_from_directory('.', 'index-v2.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('.', path)

@app.route('/transcribe', methods=['POST'])
def transcribe():
    app.logger.debug("Recibida solicitud en /transcribe")
    try:
        if 'audio' not in request.files:
            return jsonify({"error": "No se proporcionó archivo de audio"}), 400
        audio_file = request.files['audio']
        audio_file.save('received_audio.webm')
        app.logger.debug(f"Audio recibido, tamaño: {audio_file.seek(0, 2)} bytes")
        audio_file.seek(0)

        # Convertir el audio a WAV para Whisper
        subprocess.run(['ffmpeg', '-i', 'received_audio.webm', 'received_audio.wav', '-y'])

        # Usar Whisper para transcribir
        model = whisper.load_model("medium")
        result = model.transcribe('received_audio.wav')
        transcription = result["text"]
        return jsonify({"text": transcription})
    except Exception as e:
        app.logger.error(f"Error en /transcribe: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/ask-ai', methods=['POST'])
def ask_ai():
    app.logger.debug("Recibida solicitud en /ask-ai")
    try:
        data = request.get_json()
        text = data.get('text')
        lat = data.get('lat')
        lon = data.get('lon')

        # Hacer una solicitud a la API de Grok
        headers = {
            "Authorization": f"Bearer {XAI_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "grok-3",  # Cambiamos de "grok" a "grok-3"
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": text}
            ]
        }
        response = requests.post("https://api.x.ai/v1/chat/completions", headers=headers, json=payload)
        app.logger.debug(f"Respuesta completa de xAI API: {response.status_code} - {response.text}")
        if not response.ok:
            raise Exception(f"Error {response.status_code}: {response.text}")
        result = response.json()
        ai_response = result["choices"][0]["message"]["content"].strip()
        return jsonify({"response": ai_response})
    except Exception as e:
        app.logger.error(f"Error en /ask-ai: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/speak', methods=['POST'])
def speak():
    app.logger.debug("Recibida solicitud en /speak")
    try:
        data = request.get_json()
        text = data.get('text')
        import subprocess
        subprocess.run(['ffmpeg', '-i', 'received_audio.webm', '-ar', '16000', '-ac', '1', '-af', 'volume=2', 'received_audio.wav', '-y'])
        with open('received_audio.wav', 'rb') as audio_file:
            audio_data = audio_file.read()
        return app.response_class(audio_data, mimetype='audio/wav')
    except Exception as e:
        app.logger.error(f"Error en /speak: {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8088, debug=True)