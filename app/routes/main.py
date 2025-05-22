from flask import Blueprint, request, jsonify, send_file, render_template, current_app as app
import io
import os
import tempfile
import requests
import re
import subprocess
import time
import traceback
from pydub import AudioSegment
import urllib.parse
from datetime import datetime
import pytz
from google.cloud import speech
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
import langdetect

from app.utils.helpers import detect_language_nlp, detect_language, is_news_related, query_newsapi, extract_city, add_header

main_routes = Blueprint('main', __name__)

# Configurar reintentos para solicitudes HTTP
retries = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
adapter = HTTPAdapter(max_retries=retries)
http = requests.Session()
http.mount("https://", adapter)

# Variables globales para las claves API
OPENWEATHER_API_KEY = None
SUPERGROK_API_KEY = None
AZURE_SPEECH_KEY = None
NEWS_API_KEY = None
AZURE_REGION = None
GOOGLE_APPLICATION_CREDENTIALS = None
SCRAPE_DELAY = None

# Carga las claves API dentro del contexto de la aplicación
@main_routes.before_app_request
def load_api_keys():
    global OPENWEATHER_API_KEY, SUPERGROK_API_KEY, AZURE_SPEECH_KEY, NEWS_API_KEY, AZURE_REGION, GOOGLE_APPLICATION_CREDENTIALS, SCRAPE_DELAY
    OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")
    SUPERGROK_API_KEY = os.getenv("SUPERGROK_API_KEY")
    AZURE_SPEECH_KEY = os.getenv("AZURE_SPEECH_KEY")
    NEWS_API_KEY = os.getenv("NEWS_API_KEY")
    AZURE_REGION = os.getenv("AZURE_REGION", "brazilsouth")
    GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "/secrets/google-credentials")
    SCRAPE_DELAY = float(os.getenv("SCRAPE_DELAY", 1.0))

    # Verifica las claves API
    app.logger.debug(f"OPENWEATHER_API_KEY = {'set' if OPENWEATHER_API_KEY else 'not set'}")
    app.logger.debug(f"SUPERGROK_API_KEY = {'set' if SUPERGROK_API_KEY else 'not set'}")
    app.logger.debug(f"AZURE_SPEECH_KEY = {'set' if AZURE_SPEECH_KEY else 'not set'}")
    app.logger.debug(f"NEWS_API_KEY = {'set' if NEWS_API_KEY else 'not set'}")
    app.logger.debug(f"GOOGLE_APPLICATION_CREDENTIALS = {'set' if GOOGLE_APPLICATION_CREDENTIALS else 'not set'}")
    app.logger.debug(f"SCRAPE_DELAY = {SCRAPE_DELAY} seconds")

    if not os.path.exists(GOOGLE_APPLICATION_CREDENTIALS):
        app.logger.error(f"Archivo de credenciales de Google no encontrado en {GOOGLE_APPLICATION_CREDENTIALS}")

@main_routes.after_request
def after_request(response):
    return add_header(response)

@main_routes.route('/')
def home():
    try:
        app.logger.debug("Renderizando index-v2.html")
        return render_template('index-v2.html')
    except Exception as e:
        app.logger.error(f"Error al renderizar index-v2.html: {str(e)}\n{traceback.format_exc()}")
        return jsonify({"error": "Error interno del servidor"}), 500

@main_routes.route('/favicon.ico')
def favicon():
    return '', 204

@main_routes.route('/test', methods=['GET'])
def test():
    return jsonify({"message": "El servidor está funcionando correctamente"})

@main_routes.route('/transcribe', methods=['POST'])
def transcribe_audio():
    try:
        app.logger.debug("Verificando ffmpeg")
        ffmpeg_version = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True).stdout
        app.logger.debug(f"FFmpeg version: {ffmpeg_version[:50]}...")

        google_credentials_path = GOOGLE_APPLICATION_CREDENTIALS
        app.logger.debug(f"Ruta de credenciales de Google Cloud: {google_credentials_path}")
        if not os.path.exists(google_credentials_path):
            raise ValueError(f"Archivo de credenciales no encontrado en {google_credentials_path}")

        speech_client = speech.SpeechClient.from_service_account_json(google_credentials_path)
        app.logger.debug("Cliente de Speech-to-Text inicializado")

        if 'audio' not in request.files:
            app.logger.error("No se proporcionó un archivo de audio")
            return jsonify({"error": "No se proporcionó un archivo de audio"}), 400

        audio_file = request.files['audio']
        if not audio_file.filename:
            app.logger.error("El archivo de audio está vacío o sin nombre")
            return jsonify({"error": "El archivo de audio está vacío o sin nombre"}), 400

        with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as temp_audio:
            audio_file.save(temp_audio.name)
            file_size = os.path.getsize(temp_audio.name)
            app.logger.debug(f"Tamaño del archivo de audio: {file_size} bytes")
            if file_size < 100:
                raise ValueError(f"El archivo de audio es demasiado pequeño: {file_size} bytes")

            try:
                audio = AudioSegment.from_file(temp_audio.name, format="webm")
                audio = audio.set_channels(1).set_frame_rate(16000).set_sample_width(2)
                app.logger.debug(f"Audio procesado con pydub, duración (ms): {len(audio)}")
                if len(audio) < 1000:
                    raise ValueError("El audio es demasiado corto para procesar")
            except Exception as e:
                app.logger.error(f"Error al procesar audio con pydub: {str(e)}\n{traceback.format_exc()}")
                raise ValueError(f"Error al procesar audio con pydub: {str(e)}")

            temp_wav = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
            audio.export(temp_wav.name, format="wav", parameters=["-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1"])
            wav_size = os.path.getsize(temp_wav.name)
            app.logger.debug(f"Tamaño del archivo WAV: {wav_size} bytes")
            if wav_size < 1000:
                raise ValueError(f"El archivo WAV es demasiado pequeño: {wav_size} bytes")

            with open(temp_wav.name, "rb") as audio_file:
                content = audio_file.read()
            if not content:
                raise ValueError("El contenido del archivo de audio está vacío")

            detected_language = detect_language_nlp(content.decode('utf-8', errors='ignore'))
            if not detected_language:
                app.logger.warning("No se pudo detectar el idioma, usando es-ES por defecto")
                detected_language = "es"
            language_code = "es-ES" if detected_language == "es" else "pt-BR"
            alternative_codes = ["pt-BR", "en-US", "fr-FR", "it-IT"]
            app.logger.debug(f"Idioma detectado: {detected_language}, usando language_code: {language_code}")

            audio = speech.RecognitionAudio(content=content)
            config = speech.RecognitionConfig(
                encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
                sample_rate_hertz=16000,
                language_code=language_code,
                alternative_language_codes=alternative_codes,
                enable_automatic_punctuation=True,
                model="default",
                enable_word_time_offsets=True,
                audio_channel_count=1,
                enable_separate_recognition_per_channel=False,
                speech_contexts=[speech.SpeechContext(phrases=[
                    "hola", "cómo estás", "hablar", "español", "portugués",
                    "Maricá", "Río de Janeiro", "Niterói", "Saquarema",
                    "Buenos Aires", "Petrópolis", "Londres", "Tokio",
                    "Itaboraí", "Magé", "Teresópolis", "Arraial do Cabo",
                    "São Pedro da Aldeia", "São José do Vale do Rio Preto",
                    "Barra Mansa", "Nova Friburgo", "Visconde de Mauá",
                    "Resende", "Penedo", "Parque Nacional de Itatiaia",
                    "Parque Natural Municipal Morada dos Corrêas",
                    "Espraiado", "Ponta Negra", "Serra da Tiririca",
                    "Barra de Sana", "Pedra de Inoã", "fluminense", "buziano",
                    "Yara", "Jenny", "Dania", "Denise", "Isabella",
                    "Reserva Natural de Massambaba - Saquarema", "Pedra do Macaco",
                    "Trilha da Pedra do Macaco", "Cachoeira do Segredo en Silvado",
                    "Tribo Nawa Ayahuasca Maricá"
                ])]
            )

            app.logger.debug(f"Enviando audio a Speech-to-Text: {len(content)} bytes, config: {config}")
            response = speech_client.recognize(config=config, audio=audio)
            app.logger.debug(f"Respuesta de Speech-to-Text: {response}")
            if not response.results:
                app.logger.error("No hay resultados en la transcripción. Audio guardado para depuración.")
                with open("/home/cris/voz_robotica/test_audio.wav", "wb") as test_file:
                    test_file.write(content)
                return jsonify({"error": "No se detectó voz clara. Intenta hablar más claro y cerca del micrófono."}), 400
            transcription = response.results[0].alternatives[0].transcript
            if not transcription.strip():
                app.logger.error("Transcripción vacía.")
                return jsonify({"error": "No se detectó voz clara. Intenta hablar más claro y cerca del micrófono."}), 400
            app.logger.debug(f"Transcripción obtenida: {transcription}")
            os.unlink(temp_audio.name)
            os.unlink(temp_wav.name)
            return jsonify({"text": transcription, "language": detected_language})

    except Exception as e:
        app.logger.error(f"Error al procesar audio: {str(e)}\n{traceback.format_exc()}")
        if 'temp_audio' in locals():
            os.unlink(temp_audio.name)
        if 'temp_wav' in locals():
            os.unlink(temp_wav.name)
        return jsonify({"error": f"Error al transcribir audio: {str(e)}"}), 500

def get_weather(lat, lon):
    api_key = os.getenv('OPENWEATHER_API_KEY')
    if not api_key:
        app.logger.error("La clave de OpenWeatherMap no está configurada.")
        return "No se pudo obtener el clima porque falta la clave API."

    url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={api_key}&units=metric"
    try:
        response = requests.get(url)
        response.raise_for_status()
        weather_data = response.json()
        description = weather_data['weather'][0]['description']
        temperature = weather_data['main']['temp']
        return f"El clima actual es {description} con una temperatura de {temperature}°C."
    except requests.exceptions.RequestException as e:
        app.logger.error(f"Error al obtener el clima: {str(e)}")
        return "No se pudo obtener la información del clima en este momento."

@main_routes.route('/ask-ai', methods=['POST'])
def ask_ai():
    try:
        data = request.get_json()
        if not data or 'text' not in data:
            app.logger.error("No se proporcionó texto en la solicitud")
            return jsonify({"error": "No se proporcionó texto"}), 400

        text = data['text'].lower()
        language = data.get('language', 'es')  # Idioma detectado por /transcribe
        lat = data.get('lat', -22.91889)
        lon = data.get('lon', -42.81889)
        app.logger.debug(f"Recibido: texto={text}, language={language}, lat={lat}, lon={lon}")

        assistant_names = {
            'denis': {'name': 'Denise', 'voice': 'fr-FR-DeniseNeural', 'lang': 'fr'},
            'isabella': {'name': 'Isabella', 'voice': 'it-IT-IsabellaNeural', 'lang': 'it'},
            'jenny': {'name': 'Jenny', 'voice': 'en-US-JennyNeural', 'lang': 'en'},
            'yara': {'name': 'Yara', 'voice': 'pt-BR-YaraNeural', 'lang': 'pt'},
            'dania': {'name': 'Dania', 'voice': 'es-AR-DaniaNeural', 'lang': 'es'}
        }

        mentioned_assistant = None
        for name in assistant_names:
            if name in text:
                mentioned_assistant = assistant_names[name]
                break

        if mentioned_assistant:
            assistant_name = mentioned_assistant['name']
            voice_name = mentioned_assistant['voice']
            lang_code = mentioned_assistant['lang']
            app.logger.debug(f"Asistente mencionada: {assistant_name}, Voz: {voice_name}, Idioma: {lang_code}")
        else:
            lang_code = language  # Usar el idioma detectado por /transcribe
            lang_to_assistant = {
                'en': {'name': 'Jenny', 'voice': 'en-US-JennyNeural'},
                'pt': {'name': 'Yara', 'voice': 'pt-BR-YaraNeural'},
                'es': {'name': 'Dania', 'voice': 'es-AR-DaniaNeural'},
                'fr': {'name': 'Denise', 'voice': 'fr-FR-DeniseNeural'},
                'it': {'name': 'Isabella', 'voice': 'it-IT-IsabellaNeural'}
            }
            assistant = lang_to_assistant.get(lang_code, lang_to_assistant['es'])
            assistant_name = assistant['name']
            voice_name = assistant['voice']

        app.logger.debug("Consulta general, consultando SuperGrok")
        url = "https://api.x.ai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {SUPERGROK_API_KEY}", "Content-Type": "application/json"}
        system_message = {
            'es': f"Soy {assistant_name}, asistente de iURi. Responde en español.",
            'en': f"I am {assistant_name}, assistant to iURi. Respond in English.",
            'pt': f"Sou {assistant_name}, assistente de iURi. Responda em português.",
            'fr': f"Je suis {assistant_name}, assistante d'iURi. Répondez en français.",
            'it': f"Sono {assistant_name}, assistente di iURi. Rispondi in italiano."
        }.get(lang_code, f"Soy {assistant_name}, asistente de iURi. Responde en español.")
        payload = {
            "model": "grok-3",
            "messages": [{"role": "system", "content": system_message}, {"role": "user", "content": text}],
            "max_tokens": 150
        }
        response = http.post(url, json=payload, headers=headers, timeout=20)
        result = response.json()
        answer = result['choices'][0]['message']['content'].strip()
        return jsonify({"response": answer, "voice": voice_name, "language": lang_code})

    except Exception as e:
        app.logger.error(f"Error en /ask-ai: {str(e)}")
        return jsonify({"error": f"Error interno: {str(e)}"}), 500

@main_routes.route('/speak', methods=['POST'])
def speak():
    try:
        data = request.get_json()
        if not data or 'text' not in data or 'voice' not in data or 'language' not in data:
            app.logger.error("Faltan datos para sintetizar audio")
            return jsonify({"error": "Faltan datos"}), 400

        text = data['text']
        voice_name = data['voice']
        language = data['language']
        app.logger.debug(f"Procesando texto: {text}, voz: {voice_name}, idioma: {language}")

        valid_voices = ['pt-BR-YaraNeural', 'en-US-JennyNeural', 'es-AR-DaniaNeural', 'fr-FR-DeniseNeural', 'it-IT-IsabellaNeural']
        if voice_name not in valid_voices:
            app.logger.error(f"Voz no válida: {voice_name}")
            return jsonify({"error": f"Voz no válida. Opciones: {valid_voices}"}), 400

        if not AZURE_SPEECH_KEY:
            app.logger.error("AZURE_SPEECH_KEY no está configurada")
            return jsonify({"error": "Falta la clave de API de Azure Speech"}), 500

        lang_map = {
            'pt-BR-YaraNeural': 'pt-BR',
            'en-US-JennyNeural': 'en-US',
            'es-AR-DaniaNeural': 'es-AR',
            'fr-FR-DeniseNeural': 'fr-FR',
            'it-IT-IsabellaNeural': 'it-IT'
        }
        expected_lang = lang_map.get(voice_name, 'es-AR')
        if language != expected_lang.split('-')[0]:
            app.logger.warning(f"Idioma {language} no coincide con la voz {voice_name}. Usando {expected_lang}")
            language = expected_lang

        text = re.sub(r'[^\w\s.,!?\'-]', '', text).replace('"', "'").strip()
        if not text:
            app.logger.error("Texto vacío después de sanitizar")
            return jsonify({"error": "El texto está vacío después de sanitizar"}), 400

        ssml = f"""<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='{language}'><voice name='{voice_name}'>{text}</voice></speak>"""
        url = f"https://{AZURE_REGION}.tts.speech.microsoft.com/cognitiveservices/v1"
        headers = {"Ocp-Apim-Subscription-Key": AZURE_SPEECH_KEY, "Content-Type": "application/ssml+xml", "X-Microsoft-OutputFormat": "riff-8khz-16bit-mono-pcm"}

        response = http.post(url, headers=headers, data=ssml.encode('utf-8'))
        if response.status_code != 200:
            error_msg = f"Error al sintetizar audio: {response.status_code} - {response.text}"
            app.logger.error(error_msg)
            return jsonify({"error": error_msg}), 500

        return send_file(io.BytesIO(response.content), mimetype="audio/wav", as_attachment=True, download_name="response.wav")

    except Exception as e:
        app.logger.error(f"Error al generar audio: {str(e)}\n{traceback.format_exc()}")
        return jsonify({"error": f"Error al generar audio: {str(e)}"}), 500

@main_routes.route('/scrape-activities', methods=['GET'])
def scrape_activities():
    try:
        app.logger.debug(f"Aplicando retraso de {SCRAPE_DELAY} segundos")
        time.sleep(SCRAPE_DELAY)

        url = "https://www.wikiloc.com/trails/hiking/brazil/rio-de-janeiro/marica"
        headers = {
            "User-Agent": "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.120 Mobile Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5"
        }
        response = http.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'lxml')

        trails = []
        trail_elements = soup.select('a.trail__title')
        if not trail_elements:
            app.logger.debug("No se encontraron rutas. HTML (primeros 500 caracteres):")
            app.logger.debug(response.text[:500])
            return jsonify({"activities": "No encontré rutas de senderismo en Maricá. Intenta buscar manualmente en wikiloc.com."})

        for trail in trail_elements[:3]:
            title = trail.text.strip()
            link = trail['href']
            if not link.startswith('http'):
                link = f"https://www.wikiloc.com{link}"
            trails.append({"title": title, "link": link})
            app.logger.debug(f"Ruta encontrada: {title} - {link}")

        response_text = "Aquí tienes algunas rutas de senderismo en Maricá desde Wikiloc:\n" + "\n".join(f"- {t['title']}: {t['link']}" for t in trails)
        return jsonify({"activities": response_text or "No encontré rutas de senderismo en Maricá. Intenta buscar manualmente en wikiloc.com."})

    except Exception as e:
        app.logger.error(f"Error al scrapear Wikiloc: {str(e)}\n{traceback.format_exc()}")
        return jsonify({"activities": "Error al buscar rutas en Wikiloc. Intenta de nuevo más tarde."}), 500