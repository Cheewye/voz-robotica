from flask import Flask, request, jsonify, send_file, render_template
from flask_cors import CORS
import os
from dotenv import load_dotenv
from google.cloud import speech
from google.cloud import texttospeech
import tempfile
import logging
import io
import openai
import requests
from flask import send_from_directory
import re

# Configurar logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

load_dotenv()
app = Flask(__name__, static_folder='app/static', template_folder='app/templates')
CORS(app)

# Configurar Google Cloud (Speech-to-Text y Text-to-Speech)
credential_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "/home/cris/voz_robotica/credentials.json")
logger.debug(f"Usando credenciales de Google en: {credential_path}")
if not os.path.exists(credential_path):
    logger.error(f"Archivo de credenciales no encontrado: {credential_path}")
    raise FileNotFoundError(f"Archivo de credenciales no encontrado: {credential_path}")

# Verificar archivos SSL
ssl_files = ['cert.pem', 'key.pem']
for ssl_file in ssl_files:
    ssl_file_path = os.path.join('/home/cris/voz_robotica', ssl_file)
    if not os.path.exists(ssl_file_path):
        logger.error(f"Archivo SSL no encontrado: {ssl_file_path}")
        raise FileNotFoundError(f"Archivo SSL no encontrado: {ssl_file_path}")

# Mapa de voces de la UI a voces de Google Cloud Text-to-Speech
VOICE_MAP = {
    'pt-BR-YaraNeural': {'language_code': 'pt-BR', 'name': 'pt-BR-Neural2-A'},
    'en-US-JennyNeural': {'language_code': 'en-US', 'name': 'en-US-Neural2-C'},
    'es-AR-DaniaNeural': {'language_code': 'es-US', 'name': 'es-US-Neural2-A'},
    'fr-FR-DeniseNeural': {'language_code': 'fr-FR', 'name': 'fr-FR-Neural2-A'},
    'it-IT-IsabellaNeural': {'language_code': 'it-IT', 'name': 'it-IT-Neural2-A'}
}

# Configurar claves API
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")

if not OPENAI_API_KEY or not OPENWEATHER_API_KEY:
    logger.error("Faltan claves API en el archivo .env")
    raise ValueError("Faltan claves API en el archivo .env")

openai.api_key = OPENAI_API_KEY

# Ruta para servir archivos de la UI holográfica
@app.route('/iURi3D/<path:filename>')
def serve_iURi3D(filename):
    # Solo permitir archivos específicos por seguridad
    if not filename.endswith(('.html', '.css', '.js')):
        logger.warning(f"Intento de acceder a archivo no permitido: {filename}")
        return jsonify({"error": "Archivo no permitido"}), 403
    return send_from_directory('iURi3D', filename)

@app.route('/favicon.ico')
def favicon():
    return '', 204

# Endpoint para transcribir audio a texto
@app.route('/transcribe', methods=['POST'])
def transcribe():
    try:
        logger.debug("Recibiendo solicitud de transcripción")
        if 'audio' not in request.files:
            logger.error("No se proporcionó un archivo de audio")
            return jsonify({"error": "No se proporcionó un archivo de audio. ¡Graba algo primero!"}), 400

        audio_file = request.files['audio']
        audio_content = audio_file.read()
        file_size = len(audio_content)
        logger.debug(f"Tamaño del archivo de audio: {file_size} bytes")

        # Validar tamaño del archivo
        MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
        if file_size > MAX_FILE_SIZE:
            logger.error("El archivo de audio es demasiado grande")
            return jsonify({"error": f"El archivo de audio es demasiado grande (máximo {MAX_FILE_SIZE} bytes)"}), 400
        if file_size < 1000:
            logger.error("El archivo de audio es demasiado pequeño")
            return jsonify({"error": "El audio es muy corto. ¡Habla un poco más!"}), 400

        client = speech.SpeechClient()
        audio = speech.RecognitionAudio(content=audio_content)
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.WEBM_OPUS,
            sample_rate_hertz=48000,  # Ajustado a 48000 Hz para coincidir con el WebM Opus del navegador
            language_code="es-ES",
            alternative_language_codes=["en-US", "pt-BR"],
            enable_automatic_punctuation=True
        )

        logger.debug("Enviando solicitud a Google Cloud Speech-to-Text")
        response = client.recognize(config=config, audio=audio)
        if not response.results:
            logger.warning("No se detectó voz clara en el audio")
            return jsonify({"error": "No escuché nada claro. ¡Habla más fuerte o reduce el ruido!"}), 400

        texto = response.results[0].alternatives[0].transcript
        language_code = response.results[0].language_code.upper()
        logger.debug(f"Texto transcrito: {texto}, Idioma detectado: {language_code}")
        return jsonify({"text": texto, "language_code": language_code})

    except Exception as e:
        logger.error(f"Error al transcribir audio: {str(e)}")
        return jsonify({"error": f"Ups, algo falló al transcribir: {str(e)}"}), 500

# Endpoint para procesar preguntas y generar respuestas
@app.route('/ask-ai', methods=['POST'])
def ask_ai():
    try:
        data = request.json
        text = data.get('text', '').lower()
        lat = data.get('lat', None)
        lon = data.get('lon', None)
        logger.debug(f"Recibido en /ask-ai: text={text}, lat={lat}, lon={lon}")

        # Detectar preguntas sobre localización
        if any(keyword in text for keyword in ['localización', 'ubicación', 'dónde estoy']):
            if lat and lon:
                respuesta = f"Estás en las coordenadas {lat}, {lon}. ¡Eso es Maricá, Brasil! ¿Quieres saber el clima o algo más?"
            else:
                respuesta = "No tengo tu ubicación. ¿En qué más te ayudo?"
        
        # Detectar preguntas sobre el clima con mejor extracción de ciudades
        elif 'clima' in text or 'tiempo' in text:
            # Usar regex para extraer la ciudad después de "en" o "de"
            city_match = re.search(r"\b(en|de)\s+([\w\s]+?)(?:\s+hoy|\s+ahora|\b|$)", text, re.IGNORECASE)
            if city_match:
                city = city_match.group(2).strip()
                city = ' '.join(word.capitalize() for word in city.split())  # Capitalizar nombre
            else:
                # Fallback: buscar una palabra que pueda ser ciudad
                words = text.split()
                possible_cities = [word.capitalize() for word in words if word not in ['clima', 'tiempo', 'en', 'de', 'hoy', 'ahora']]
                city = possible_cities[-1] if possible_cities else "Maricá"  # Fallback a Maricá

            url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={OPENWEATHER_API_KEY}&units=metric"
            try:
                response = requests.get(url)
                response.raise_for_status()
                data = response.json()
                temp = data['main']['temp']
                desc = data['weather'][0]['description']
                respuesta = f"El clima en {city} es {desc} con {temp}°C."
            except requests.exceptions.RequestException as e:
                logger.error(f"Error al obtener el clima: {str(e)}")
                respuesta = f"No encontré el clima de {city}. ¿Probamos otra ciudad?"
        
        # Respuesta conversacional con OpenAI para otros casos
        else:
            try:
                client = openai.OpenAI(api_key=OPENAI_API_KEY)
                response = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": "Eres un asistente útil."},
                        {"role": "user", "content": text}
                    ],
                    max_tokens=150,
                    temperature=0.7
                )
                respuesta = response.choices[0].message.content.strip()
            except Exception as e:
                logger.error(f"Error con OpenAI: {str(e)}")
                respuesta = "Ups, algo falló. ¿Qué más puedo hacer por ti?"

        return jsonify({"response": respuesta})

    except Exception as e:
        logger.error(f"Error en /ask-ai: {str(e)}")
        return jsonify({"error": f"Error al procesar la solicitud: {str(e)}"}), 500

# Endpoint para generar audio a partir de texto
@app.route('/speak', methods=['POST'])
def speak():
    try:
        data = request.json
        text = data.get('text', '')
        voice = data.get('voice', 'pt-BR-YaraNeural')
        logger.debug(f"Recibido en /speak: text={text}, voice={voice}")

        if not text:
            logger.error("No se proporcionó texto para sintetizar")
            return jsonify({"error": "No se proporcionó texto para sintetizar"}), 400

        if voice not in VOICE_MAP:
            logger.error(f"Voz no soportada: {voice}")
            return jsonify({"error": f"Voz no soportada: {voice}"}), 400

        voice_config = VOICE_MAP[voice]
        client = texttospeech.TextToSpeechClient()
        synthesis_input = texttospeech.SynthesisInput(text=text)
        voice_params = texttospeech.VoiceSelectionParams(
            language_code=voice_config['language_code'],
            name=voice_config['name']
        )
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3
        )

        response = client.synthesize_speech(
            input=synthesis_input,
            voice=voice_params,
            audio_config=audio_config
        )

        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as temp_file:
            temp_file.write(response.audio_content)
            temp_file_path = temp_file.name

        return send_file(temp_file_path, mimetype='audio/mpeg', as_attachment=True, download_name='response.mp3')

    except Exception as e:
        logger.error(f"Error al generar audio: {str(e)}")
        if 'temp_file_path' in locals():
            os.unlink(temp_file_path)
        return jsonify({"error": f"Error al generar audio: {str(e)}"}), 500

# Ruta para la URL raíz
@app.route('/')
def home():
    return render_template('index-v2.html')

# Iniciar el servidor Flask
if __name__ == '__main__':
    try:
        app.run(host='0.0.0.0', port=8080, debug=True, ssl_context=('/home/cris/voz_robotica/cert.pem', '/home/cris/voz_robotica/key.pem'))
    except Exception as e:
        logger.error(f"Error al iniciar el servidor: {str(e)}")
        raise