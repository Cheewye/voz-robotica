from flask import Flask, request, jsonify, send_file, render_template
from flask_cors import CORS
import io
import os
import tempfile
import requests
import re
import subprocess
import time
from dotenv import load_dotenv
from pydub import AudioSegment
import urllib.parse
import pandas as pd
import numpy as np
from datetime import datetime
import pytz
from google.cloud import language_v1, speech
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup

app = Flask(__name__)
CORS(app)

# Configurar reintentos para solicitudes HTTP
retries = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
adapter = HTTPAdapter(max_retries=retries)
http = requests.Session()
http.mount("https://", adapter)

# Cargar .env
try:
    load_dotenv(dotenv_path="/home/cris/voz_robotica/.env")
    print("DEBUG: .env cargado desde /home/cris/voz_robotica/.env")
except Exception as e:
    print(f"DEBUG: Error al cargar .env: {e}")

# Función para leer secretos desde archivos
def read_secret(file_path):
    try:
        with open(file_path, 'r') as f:
            return f.read().strip()
    except Exception as e:
        print(f"ERROR: No se pudo leer el secreto en {file_path}: {e}")
        return None

# Carga las API Keys
OPENWEATHER_API_KEY = read_secret("/secrets/openweather-api-key") or os.getenv("OPENWEATHER_API_KEY")
SUPERGROK_API_KEY = read_secret("/secrets/supergrok-api-key") or os.getenv("SUPERGROK_API_KEY")
AZURE_SPEECH_KEY = read_secret("/secrets/azure-speech-key") or os.getenv("AZURE_SPEECH_KEY")
NEWS_API_KEY = read_secret("/secrets/news-api-key") or os.getenv("NEWS_API_KEY")
AZURE_REGION = os.getenv("AZURE_REGION", "brazilsouth")
GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "/secrets/google-credentials")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
SCRAPE_DELAY = float(os.getenv("SCRAPE_DELAY", 1.0))  # Retraso configurable para scraping

# Verifica las API Keys
print(f"DEBUG: OPENWEATHER_API_KEY = {OPENWEATHER_API_KEY if OPENWEATHER_API_KEY else 'not set'}")
print(f"DEBUG: SUPERGROK_API_KEY = {SUPERGROK_API_KEY[:5] if SUPERGROK_API_KEY else 'not set'}...")
print(f"DEBUG: AZURE_SPEECH_KEY = {'set' if AZURE_SPEECH_KEY else 'not set'}")
print(f"DEBUG: NEWS_API_KEY = {'set' if NEWS_API_KEY else 'not set'}")
print(f"DEBUG: GOOGLE_APPLICATION_CREDENTIALS = {'set' if GOOGLE_APPLICATION_CREDENTIALS else 'not set'}")
print(f"DEBUG: DEEPSEEK_API_KEY = {'set' if DEEPSEEK_API_KEY else 'not set'}")
print(f"DEBUG: ELEVENLABS_API_KEY = {'set' if ELEVENLABS_API_KEY else 'not set'}")
print(f"DEBUG: SCRAPE_DELAY = {SCRAPE_DELAY} seconds")

# Verificar GOOGLE_APPLICATION_CREDENTIALS
if not os.path.exists(GOOGLE_APPLICATION_CREDENTIALS):
    print(f"ERROR: Archivo de credenciales de Google no encontrado en {GOOGLE_APPLICATION_CREDENTIALS}")

# Inicializar cliente de Google Cloud Natural Language
try:
    nlp_client = language_v1.LanguageServiceClient.from_service_account_json(GOOGLE_APPLICATION_CREDENTIALS)
    print("DEBUG: Cliente de Google Cloud Natural Language inicializado")
except Exception as e:
    print(f"ERROR: No se pudo inicializar el cliente de NLP: {e}")
    nlp_client = None

# Función para detectar idioma con Google Cloud Natural Language
def detect_language_nlp(text):
    if not nlp_client:
        print("DEBUG: Cliente NLP no disponible, usando detección por palabras clave")
        return None
    try:
        document = language_v1.Document(content=text, type_=language_v1.Document.Type.PLAIN_TEXT)
        response = nlp_client.analyze_sentiment(document=document)
        language = response.language
        confidence = response.document_sentiment.score
        print(f"DEBUG: Idioma detectado por NLP: {language}, confianza: {confidence}")
        return language
    except Exception as e:
        print(f"ERROR: No se pudo detectar idioma con NLP: {e}")
        return None

# Función para detectar preguntas relacionadas con noticias
def is_news_related(query):
    news_keywords = [
        "actual", "noticias", "news", "papa", "pope", "pontífice", "presidente",
        "gobierno", "elección", "evento", "crisis", "conflicto", "falleció",
        "muerte", "nuevo", "reciente", "hoy", "ayer", "emergência", "segurança",
        "saúde", "inundação", "incêndio", "festas", "museus", "cultura",
        "permacultura", "meditação", "yoga", "culto", "ayahuasca", "creyentes",
        "trilhas", "motos", "crente", "caiçara",
    ]
    climate_keywords = ["clima", "tempo", "playas", "playa", "bañar", "baño"]
    activity_keywords = ["trilhas", "senderismo", "caminata", "hiking", "eventos", "festas"]

    if any(keyword in query.lower() for keyword in climate_keywords):
        return False

    if any(keyword in query.lower() for keyword in activity_keywords):
        print("DEBUG: Consulta detectada como relacionada con actividades, scrapeando Wikiloc")
        response = scrape_activities()
        return response.get_json().get("activities", "No encontré actividades disponibles.")

    return any(keyword in query.lower() for keyword in news_keywords)

# Función para consultar NewsAPI con enfoque en Río de Janeiro o eventos
def query_newsapi(query):
    try:
        if not NEWS_API_KEY:
            print("ERROR: NEWS_API_KEY no está configurada")
            return None

        keywords = (
            "Maricá OR Saquarema OR Niterói OR Araruama OR Búzios OR Itaboraí OR Magé OR "
            "Petrópolis OR Teresópolis OR Rio de Janeiro OR Cabo Frio OR Arraial do Cabo OR "
            "São Pedro da Aldeia OR São José do Vale do Rio Preto OR Barra Mansa OR Nova Friburgo OR "
            "Visconde de Mauá OR Resende OR Penedo OR Parque Nacional de Itatiaia OR Espraiado OR "
            "Ponta Negra OR Serra da Tiririca OR Barra de Sana OR fluminense OR buziano OR "
            "eventos OR festas OR museus OR cultura OR permacultura OR meditação OR yoga OR culto OR "
            "ayahuasca OR creyentes OR trilhas OR motos OR Rock in Rio OR Copacabana OR reggae"
        )
        if "papa" in query.lower() or "pope" in query.lower() or "pontífice" in query.lower():
            keywords = "Papa OR Vatican OR Pope"
            if "actual" in query.lower() or "current" in query.lower():
                return "O Papa atual é León XIV, eleito em 8 de maio de 2025. Robert Prevost é americano e peruano. Verifica em www.vatican.va para informações oficiales."
            if "falleció" in query.lower() or "died" in query.lower():
                keywords += " OR morte OR death"
        elif "playas" in query.lower() or "playa" in query.lower() or "bañar" in query.lower():
            keywords = "playas Maricá OR condiciones banho Maricá"

        encoded_keywords = urllib.parse.quote(keywords)
        url = f"https://newsapi.org/v2/everything?q={encoded_keywords}&sortBy=publishedAt&apiKey={NEWS_API_KEY}"
        print(f"DEBUG: Enviando solicitud a NewsAPI: {url}")
        response = http.get(url, timeout=10)
        response.raise_for_status()
        articles = response.json().get("articles", [])
        
        if not articles:
            print("DEBUG: No se encontraron artículos en NewsAPI")
            return "Não encontrei notícias recentes sobre este tema. Verifica em fontes confiáveis como www.g1.globo.com ou www.marica.rj.gov.br."

        latest_article = articles[0]
        title = latest_article.get("title", "")
        published_at = latest_article.get("publishedAt", "")
        source = latest_article.get("source", {}).get("name", "desconocida")
        print(f"DEBUG: Artículo encontrado: {title} ({published_at})")
        
        return f"Segundo notícias recentes de {source} ({published_at}), {title}. Verifica em www.g1.globo.com ou www.marica.rj.gov.br para mais informações."

    except requests.exceptions.HTTPError as http_err:
        print(f"ERROR: Error HTTP al consultar NewsAPI: {str(http_err)}")
        return "Ocurrió un error al consultar notícias recientes. Verifica em www.g1.globo.com ou www.marica.rj.gov.br."
    except Exception as e:
        print(f"ERROR: Error al consultar NewsAPI: {str(e)}")
        return "Ocurrió un error al consultar notícias recientes. Verifica em www.g1.globo.com ou www.marica.rj.gov.br."

# Desactivar caché
@app.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '-1'
    return response

@app.route('/')
def home():
    try:
        print("DEBUG: Renderizando index-v2.html")
        return render_template('index-v2.html')
    except Exception as e:
        print(f"ERROR: Error al renderizar index-v2.html: {str(e)}")
        return jsonify({"error": "Error interno del servidor"}), 500

@app.route('/favicon.ico')
def favicon():
    return '', 204

@app.route('/test', methods=['GET'])
def test():
    return jsonify({"message": "El servidor está funcionando correctamente"})

@app.route('/transcribe', methods=['POST'])
def transcribe_audio():
    try:
        print("DEBUG: Verificando ffmpeg")
        ffmpeg_version = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True).stdout
        print(f"DEBUG: FFmpeg version: {ffmpeg_version[:50]}...")

        google_credentials_path = GOOGLE_APPLICATION_CREDENTIALS
        print(f"DEBUG: Ruta de credenciales de Google Cloud: {google_credentials_path}")
        if not os.path.exists(google_credentials_path):
            raise ValueError(f"Archivo de credenciales no encontrado en {google_credentials_path}")

        speech_client = speech.SpeechClient.from_service_account_json(google_credentials_path)
        print("DEBUG: Cliente de Speech-to-Text inicializado")

        if 'audio' not in request.files:
            print("ERROR: No se proporcionó un archivo de audio")
            return jsonify({"error": "No se proporcionó un archivo de audio"}), 400

        audio_file = request.files['audio']
        if not audio_file.filename:
            print("ERROR: El archivo de audio está vacío o sin nombre")
            return jsonify({"error": "El archivo de audio está vacío o sin nombre"}), 400

        with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as temp_audio:
            audio_file.save(temp_audio.name)
            file_size = os.path.getsize(temp_audio.name)
            print(f"DEBUG: Tamaño del archivo de audio: {file_size} bytes")
            if file_size == 0:
                raise ValueError("El archivo de audio está vacío")

            try:
                audio = AudioSegment.from_file(temp_audio.name, format="webm")
                audio = audio.set_channels(1).set_frame_rate(16000).set_sample_width(2)
                print(f"DEBUG: Audio procesado con pydub, duración (ms): {len(audio)}")
            except Exception as e:
                print(f"ERROR: Error al procesar audio con pydub: {str(e)}")
                raise ValueError(f"Error al procesar audio con pydub: {str(e)}")

            temp_wav = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
            audio.export(temp_wav.name, format="wav", parameters=["-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1"])
            wav_size = os.path.getsize(temp_wav.name)
            print(f"DEBUG: Tamaño del archivo WAV: {wav_size} bytes")
            if wav_size < 100:
                raise ValueError(f"El archivo de audio es demasiado pequeño: {wav_size} bytes")

            with open(temp_wav.name, "rb") as audio_file:
                content = audio_file.read()
            if not content:
                raise ValueError("El contenido del archivo de audio está vacío")

            # Detectar idioma del audio
            detected_language = detect_language_nlp(content.decode('utf-8', errors='ignore'))
            language_code = "pt-BR"
            alternative_codes = ["es-AR", "en-US", "fr-FR"]
            if detected_language == "it":
                language_code = "it-IT"
                alternative_codes = ["pt-BR", "es-AR", "en-US", "fr-FR"]
            elif detected_language in ["es", "en", "fr"]:
                language_code = {"es": "es-AR", "en": "en-US", "fr": "fr-FR"}[detected_language]
                alternative_codes = ["pt-BR"] + [code for code in ["es-AR", "en-US", "fr-FR"] if code != language_code]

            audio = speech.RecognitionAudio(content=content)
            config = speech.RecognitionConfig(
                encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
                sample_rate_hertz=16000,
                language_code=language_code,
                alternative_language_codes=alternative_codes,
                enable_automatic_punctuation=True,
                model="latest_short",
                enable_word_time_offsets=True,
                speech_contexts=[speech.SpeechContext(phrases=[
                    "hablando en portugués", "Niterói", "Río de Janeiro",
                    "olá", "como estás", "falar", "português", "brasileiro",
                    "Maricá", "Saquarema", "Araruama", "Cabo Frio",
                    "Grimsby", "Grimsby Inglaterra", "Grimsby UK",
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
                    "Trilha da Pedra do Macaco", "Cachoeira do Segredo em Silvado",
                    "Tribo Nawa Ayahuasca Maricá"
                ])]
            )

            print(f"DEBUG: Enviando audio a Speech-to-Text: {len(content)} bytes")
            response = speech_client.recognize(config=config, audio=audio)
            print(f"DEBUG: Respuesta de Speech-to-Text: {response}")
            if not response.results:
                print("ERROR: No hay resultados en la transcripción")
                return jsonify({"error": "No se detectó voz clara, intenta de nuevo"}), 400
            transcription = response.results[0].alternatives[0].transcript
            if not transcription.strip():
                print("ERROR: Transcripción vacía, no se detectó voz clara")
                return jsonify({"error": "No se detectó voz clara, intenta de nuevo"}), 400
            print(f"DEBUG: Transcripción obtenida: {transcription}")
            os.unlink(temp_audio.name)
            os.unlink(temp_wav.name)
            return jsonify({"text": transcription})

    except ImportError as e:
        print(f"ERROR: Error al importar google.cloud.speech: {str(e)}")
        return jsonify({"error": f"Servicio de Speech-to-Text no disponible: {str(e)}"}), 500
    except Exception as e:
        print(f"ERROR: Error al procesar audio: {str(e)}")
        if 'temp_audio' in locals():
            os.unlink(temp_audio.name)
        if 'temp_wav' in locals():
            os.unlink(temp_wav.name)
        return jsonify({"error": f"Error al procesar audio: {str(e)}"}), 500

@app.route('/weather', methods=['POST'])
def get_weather():
    try:
        data = request.json
        city = data.get('city')
        lat = data.get('lat', -22.91889)  # Maricá por defecto
        lon = data.get('lon', -42.81889)
        text = data.get('text', '')  # Texto de la consulta
        user_lat = data.get('user_lat')  # Geolocalización del usuario
        user_lon = data.get('user_lon')

        print(f"DEBUG: Coordenadas recibidas en /weather: lat={lat}, lon={lon}, city={city}, text={text}, user_lat={user_lat}, user_lon={user_lon}")

        if city:
            geocode_url = f"http://api.openweathermap.org/geo/1.0/direct?q={urllib.parse.quote(city)}&limit=1&appid={OPENWEATHER_API_KEY}"
            print(f"DEBUG: Enviando solicitud de geocodificación: {geocode_url}")
            geocode_response = http.get(geocode_url)
            geocode_response.encoding = 'utf-8'
            print(f"DEBUG: Respuesta de geocodificación: {geocode_response.status_code}, {geocode_response.text[:100]}")
            geocode_response.raise_for_status()
            geocode_data = geocode_response.json()
            print(f"DEBUG: Datos de geocodificación: {geocode_data}")
            if not geocode_data:
                city_name = "Maricá"
                lat = -22.91889
                lon = -42.81889
            else:
                lat = geocode_data[0]['lat']
                lon = geocode_data[0]['lon']
                city_name = geocode_data[0]['name']
        else:
            geocode_url = f"http://api.openweathermap.org/geo/1.0/reverse?lat={lat}&lon={lon}&limit=1&appid={OPENWEATHER_API_KEY}"
            print(f"DEBUG: Enviando solicitud de geocodificación inversa: {geocode_url}")
            geocode_response = http.get(geocode_url)
            geocode_response.encoding = 'utf-8'
            print(f"DEBUG: Respuesta de geocodificación inversa: {geocode_response.status_code}, {geocode_response.text[:100]}")
            geocode_response.raise_for_status()
            geocode_data = geocode_response.json()
            city_name = geocode_data[0]['name'] if geocode_data else "Maricá"

        print(f"DEBUG: Ciudad procesada en /weather: {city_name}")

        url = f"https://api.openweathermap.org/data/3.0/onecall?lat={lat}&lon={lon}&appid={OPENWEATHER_API_KEY}&units=metric&lang=pt_br"
        print(f"DEBUG: Enviando solicitud de clima: {url}")
        response = http.get(url)
        response.encoding = 'utf-8'
        print(f"DEBUG: Respuesta de clima: {response.status_code}, {response.text[:100]}")
        response.raise_for_status()
        weather_data = response.json()

        current_weather = weather_data['current']
        temperature = current_weather['temp']
        description = current_weather['weather'][0]['description']
        humidity = current_weather['humidity']
        wind_speed = current_weather['wind_speed']
        rain = current_weather.get('rain', {}).get('1h', 0)

        weather_response = (
            f"Em {city_name}, o clima está {description}. "
            f"A temperatura é de {temperature}°C, "
            f"a umidade é de {humidity}%, "
            f"e a velocidade do vento é de {wind_speed} m/s."
        )
        bathing_conditions = ""
        if text and ("playas" in text.lower() or "playa" in text.lower() or "bañar" in text.lower()):
            if temperature > 20 and rain == 0 and "chuva" not in description.lower():
                bathing_conditions = " As condições são boas para se banhar nas praias hoje."
            else:
                bathing_conditions = " As condições não são ideales para se banhar hoje devido ao clima."

        # Mapa de Google Maps
        map_url = f"https://www.google.com/maps/embed/v1/place?q={urllib.parse.quote(city_name)}&key={OPENWEATHER_API_KEY}&zoom=10"
        if user_lat and user_lon:
            map_url += f"&center={user_lat},{user_lon}"  # Corregido el parámetro

        return jsonify({
            "weather": weather_response + bathing_conditions,
            "map_url": map_url
        })

    except requests.exceptions.HTTPError as http_err:
        print(f"ERROR: Error HTTP al obtener el clima: {str(http_err)}")
        return jsonify({"weather": f"Error al obtener el clima para {city_name or 'la ubicación'}: {str(http_err)}. Intenta con otra ciudad."})
    except Exception as e:
        print(f"ERROR: Error al obtener el clima: {str(e)}")
        return jsonify({"weather": f"Error al obtener el clima: {str(e)}. Intenta con otra ciudad."})

def extract_city(text):
    print(f"DEBUG: Intentando extraer ciudad de: {text}")
    cities = [
        "Maricá", "Saquarema", "Niterói", "Araruama", "Búzios", "Itaboraí", "Magé",
        "Petrópolis", "Teresópolis", "Rio de Janeiro", "Cabo Frio", "Arraial do Cabo",
        "São Pedro da Aldeia", "São José do Vale do Rio Preto", "Barra Mansa",
        "Nova Friburgo", "Visconde de Mauá", "Resende", "Penedo", "Parque Nacional de Itatiaia",
        "Espraiado", "Ponta Negra", "Serra da Tiririca", "Barra de Sana", "Pedra de Inoã",
        "fluminense", "buziano", "maricaense", "niteroiense", "saquaremense", "cabo-friense"
    ]
    city_pattern = r'\b(?:em|clima|tempo|tiempo|weather|en|hace en|qué clima|qué tiempo es|qué tiempo|playas en|météo)\s+([\w\sáéíóúÁÉÍÓÚñÑ,\'-]+?)(?:\s+(hoje|agora|hoy|now|clima|england|inglaterra|argentina|brasil|france|francia|$))?'
    match = re.search(city_pattern, text, re.IGNORECASE)
    city = match.group(1).strip() if match else None
    if city:
        city = city.lower()
        corrections = {
            'grisby': 'Grimsby', 'direi': 'Grimsby', 'grinsby': 'Grimsby',
            'grimsby': 'Grimsby', 'green': 'Grimsby', 'greensville': 'Grimsby'
        }
        city = corrections.get(city, city.title())
        for prefix in ['en ', 'em ']:
            if city.lower().startswith(prefix):
                city = city[len(prefix):].title()
        # Validar con OpenWeatherMap
        geocode_url = f"http://api.openweathermap.org/geo/1.0/direct?q={urllib.parse.quote(city)}&limit=1&appid={OPENWEATHER_API_KEY}"
        try:
            response = http.get(geocode_url, timeout=5)
            response.raise_for_status()
            geocode_data = response.json()
            if geocode_data and geocode_data[0]['country'] == 'BR':
                city = geocode_data[0]['name']
            else:
                city = "Maricá"
        except Exception as e:
            print(f"DEBUG: Error al validar ciudad con OpenWeatherMap: {e}")
            city = "Maricá"
    else:
        city = "Maricá"
    print(f"DEBUG: Ciudad extraída: {city}")
    return city

def detect_language(text, voice_name):
    # Intentar con Google Cloud Natural Language
    detected_language = detect_language_nlp(text)
    if detected_language:
        return detected_language
    # Respaldo con palabras clave
    if voice_name == 'en-US-JennyNeural' or any(keyword in text.lower() for keyword in ['weather', 'what', 'how', 'is', 'in']):
        return 'en'
    elif voice_name == 'es-AR-DaniaNeural' or any(keyword in text.lower() for keyword in ['clima', 'tiempo', 'qué', 'hace', 'dame']):
        return 'es'
    elif voice_name == 'fr-FR-DeniseNeural' or any(keyword in text.lower() for keyword in ['météo', 'quel', 'temps', 'est', 'à']):
        return 'fr'
    elif voice_name == 'it-IT-IsabellaNeural' or any(keyword in text.lower() for keyword in ['ciao', 'che', 'tempo', 'come', 'dove']):
        return 'it'
    return 'pt'

@app.route('/ask-ai', methods=['POST'])
def ask_ai():
    try:
        data = request.get_json()
        if not data or 'text' not in data:
            print("ERROR: No se proporcionó texto en la solicitud")
            return jsonify({"error": "No se proporcionó texto"}), 400

        text = data['text']
        lat = data.get('lat')
        lon = data.get('lon')
        user_lat = data.get('user_lat')
        user_lon = data.get('user_lon')
        voice_name = data.get('voice', 'pt-BR-YaraNeural')
        print(f"DEBUG: Recibido: texto={text}, lat={lat}, lon={lon}, user_lat={user_lat}, user_lon={user_lon}, voice={voice_name}")
        if not isinstance(text, str) or not text.strip():
            print("ERROR: El texto debe ser una cadena no vacía")
            return jsonify({"error": "El texto debe ser una cadena no vacía"}), 400

        # Detectar idioma
        lang = detect_language(text, voice_name)
        lang_map = {
            'pt': 'pt-BR',
            'en': 'en-US',
            'es': 'es-AR',
            'fr': 'fr-FR',
            'it': 'it-IT'
        }
        lang_code = lang_map.get(lang, 'pt-BR')

        # Detectar consultas de clima
        climate_keywords = ['clima', 'tempo', 'temperatura', 'chuva', 'sol', 'nublado', 'tiempo', 'weather', 'calor', 'frío', 'lluvia', 'qué clima', 'qué tiempo', 'qué tiempo es', 'hace en', 'météo']
        is_climate_query = any(keyword in text.lower() for keyword in climate_keywords)
        if is_climate_query:
            print("DEBUG: Consulta sobre el clima, consultando OpenWeatherMap")
            city = extract_city(text)
            if not OPENWEATHER_API_KEY:
                print("ERROR: OPENWEATHER_API_KEY no configurada")
                error_msg = {
                    'pt': "Falta la clave de API de OpenWeatherMap. Configúrala e intenta de novo.",
                    'en': "Missing OpenWeatherMap API key. Configure it and try again.",
                    'es': "Falta la clave de la API de OpenWeatherMap. Configúrala e intenta de nuevo.",
                    'fr': "Clé API OpenWeatherMap manquante. Configurez-la et réessayez.",
                    'it': "Manca la chiave API di OpenWeatherMap. Configurala e riprova."
                }
                return jsonify({"response": error_msg[lang]})
            weather_data = {
                'city': city,
                'lat': lat if lat else -22.91889,
                'lon': lon if lon else -42.81889,
                'text': text,
                'user_lat': user_lat,
                'user_lon': user_lon
            }
            weather_response = get_weather()  # Llamada directa a la función en lugar de solicitud HTTP
            return jsonify(weather_response.get_json())

        # Detectar consultas de playas
        beach_keywords = ['playas', 'playa', 'bañar', 'baño', 'plage', 'baignade']
        is_beach_query = any(keyword in text.lower() for keyword in beach_keywords)
        if is_beach_query:
            print("DEBUG: Consulta sobre playas detectada, consultando OpenWeatherMap")
            city = extract_city(text)
            if not OPENWEATHER_API_KEY:
                print("ERROR: OPENWEATHER_API_KEY no configurada")
                error_msg = {
                    'pt': "Falta la clave de API de OpenWeatherMap. Configúrala e intenta de novo.",
                    'en': "Missing OpenWeatherMap API key. Configure it and try again.",
                    'es': "Falta la clave de la API de OpenWeatherMap. Configúrala e intenta de nuevo.",
                    'fr': "Clé API OpenWeatherMap manquante. Configurez-la et réessayez.",
                    'it': "Manca la chiave API di OpenWeatherMap. Configurala e riprova."
                }
                return jsonify({"response": error_msg[lang]})
            weather_data = {
                'city': city,
                'lat': lat if lat else -22.91889,
                'lon': lon if lon else -42.81889,
                'text': text,
                'user_lat': user_lat,
                'user_lon': user_lon
            }
            weather_response = get_weather()  # Llamada directa a la función
            return jsonify(weather_response.get_json())

        # Detectar consultas de hora
        time_keywords = ['qué hora es', 'hora actual', 'horas', 'quelle heure', 'heure actuelle']
        is_time_query = any(keyword in text.lower() for keyword in time_keywords)
        if is_time_query:
            print("DEBUG: Consulta sobre la hora detectada")
            brt = pytz.timezone('America/Sao_Paulo')
            current_time = datetime.now(brt).strftime('%H:%M')
            response_text = {
                'pt': f"São {current_time} em Maricá, RJ.",
                'en': f"It is {current_time} in Maricá, RJ.",
                'es': f"Son las {current_time} en Maricá, RJ.",
                'fr': f"Il est {current_time} à Maricá, RJ.",
                'it': f"Sono le {current_time} a Maricá, RJ."
            }[lang]
            return jsonify({"response": response_text})

        # Detectar consultas de emergencias
        emergency_keywords = ['inundação', 'incêndio', 'emergência', 'desastre', 'acidente']
        is_emergency_query = any(keyword in text.lower() for keyword in emergency_keywords)
        if is_emergency_query:
            print("DEBUG: Consulta sobre emergencia detectada")
            city = extract_city(text)
            emergency_type = next((k for k in emergency_keywords if k in text.lower()), "emergência")
            emergency_numbers = {
                "inundação": {"number": "193", "service": "Bomberos"},
                "incêndio": {"number": "199", "service": "Defensa Civil"},
                "default": [
                    {"number": "192", "service": "SAMU"},
                    {"number": "193", "service": "Bomberos"},
                    {"number": "199", "service": "Defensa Civil"}
                ]
            }
            advice = {
                "inundação": "Busque um local elevado, evite áreas alagadas e entre em contato con os bombeiros.",
                "incêndio": "Evacue a área, mantenha-se afastado da fumaça e contate a Defesa Civil.",
                "default": "Mantenha a calma e contate os servicios de emergencia apropriados."
            }
            number = emergency_numbers.get(emergency_type, emergency_numbers["default"])
            service = emergency_numbers.get(emergency_type, {"service": " Emergência"})["service"]
            advice_text = advice.get(emergency_type, advice["default"])
            map_url = f"https://www.google.com/maps/embed/v1/place?q={urllib.parse.quote(city)}&key={OPENWEATHER_API_KEY}&zoom=10"
            if user_lat and user_lon:
                map_url += f"&center={user_lat},{user_lon}"
            response_text = {
                'pt': f"Em caso de {emergency_type} em {city}, {advice_text} Ligue para {service} no {number if isinstance(number, str) else ', '.join([n['number'] for n in number])}. <a href='tel:{number if isinstance(number, str) else number[0]['number']}' class='emergency-link'>Ligar</a>",
                'en': f"In case of {emergency_type} in {city}, {advice_text} Call {service} at {number if isinstance(number, str) else ', '.join([n['number'] for n in number])}. <a href='tel:{number if isinstance(number, str) else number[0]['number']}' class='emergency-link'>Call</a>",
                'es': f"En caso de {emergency_type} en {city}, {advice_text} Llame a {service} al {number if isinstance(number, str) else ', '.join([n['number'] for n in number])}. <a href='tel:{number if isinstance(number, str) else number[0]['number']}' class='emergency-link'>Llamar</a>",
                'fr': f"En cas de {emergency_type} à {city}, {advice_text} Appelez {service} au {number if isinstance(number, str) else ', '.join([n['number'] for n in number])}. <a href='tel:{number if isinstance(number, str) else number[0]['number']}' class='emergency-link'>Appeler</a>",
                'it': f"In caso di {emergency_type} a {city}, {advice_text} Chiama {service} al {number if isinstance(number, str) else ', '.join([n['number'] for n in number])}. <a href='tel:{number if isinstance(number, str) else number[0]['number']}' class='emergency-link'>Chiamare</a>"
            }[lang]
            return jsonify({"response": response_text, "map_url": map_url})

        # Verificar si la consulta está relacionada con noticias o eventos
        if is_news_related(text):
            print("DEBUG: Consulta detectada como relacionada con noticias o eventos")
            news_response = query_newsapi(text)
            if news_response:
                modified_answer = news_response
            else:
                modified_answer = {
                    'pt': "Não encontrei informações recientes sobre este tema. Verifica em fontes confiáveis como www.g1.globo.com ou www.marica.rj.gov.br.",
                    'en': "I couldn't find recent information on this topic. Check reliable sources like www.g1.globo.com or www.marica.rj.gov.br.",
                    'es': "No encontré información reciente sobre este tema. Verifica en fuentes confiables como www.g1.globo.com o www.marica.rj.gov.br.",
                    'fr': "Je n'ai pas trouvé d'informations récentes sur ce sujet. Vérifiez des sources fiables comme www.g1.globo.com ou www.marica.rj.gov.br.",
                    'it': "Non ho trovato informazioni recenti su questo argomento. Controlla fonti affidabili come www.g1.globo.com o www.marica.rj.gov.br."
                }[lang]
        else:
            print("DEBUG: Consulta no relacionada con noticias ni clima, consultando SuperGrok")
            if not SUPERGROK_API_KEY:
                print("ERROR: Falta la clave de API de SuperGrok")
                error_msg = {
                    'pt': "Falta la clave de API de SuperGrok.",
                    'en': "Missing SuperGrok API key.",
                    'es': "Falta la clave de la API de SuperGrok.",
                    'fr': "Clé API SuperGrok manquante.",
                    'it': "Manca la chiave API di SuperGrok."
                }
                return jsonify({"error": error_msg[lang]}), 500

            url = "https://api.x.ai/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {SUPERGROK_API_KEY}",
                "Content-Type": "application/json"
            }
            system_message = {
                'pt': (
                    "Você é Yara, uma das assistentes de iURi, um viajero do tempo que criou um assistente de voz para Maricá, RJ. Responda de forma natural e directa, em português, em até 2-3 frases. "
                    "Evite responder perguntas relacionadas com notícias ou eventos atuais, pois essas serão manejadas por outras fontes. "
                    "Concentre-se em perguntas de conhecimento geral, ciência, matemáticas ou temas não relacionados com atualidade. "
                    "Se a informação for incerta, sugira verificar fontes confiáveis."
                ),
                'en': (
                    "You are Jenny, one of iURi's assistants, a time traveler who created a voice assistant for Maricá, RJ. Respond naturally and directly in English, in 2-3 sentences. "
                    "Avoid answering questions about current events or news, as these will be handled by other sources. "
                    "Focus on general knowledge, science, math, or non-current topics. If unsure, suggest checking reliable sources."
                ),
                'es': (
                    "Eres Dania, una de las asistentes de iURi, un viajero del tiempo que creó un asistente de voz para Maricá, RJ. Responde de forma natural y directa en español, en 2-3 frases. "
                    "Evita responder preguntas sobre noticias o eventos actuales, ya que estas serán manejadas por otras fuentes. "
                    "Concéntrate en preguntas de conocimiento general, ciencia, matemáticas o temas no relacionados con la actualidad. "
                    "Si la información es incierta, sugiere verificar fuentes confiables."
                ),
                'fr': (
                    "Vous êtes Denise, l'une des assistantes d'iURi, un voyageur du temps qui a créé un assistant vocal pour Maricá, RJ. Répondez de manière naturelle et directe en français, en 2-3 phrases. "
                    "Évitez de répondre aux questions sur les actualités ou les événements actuels, car celles-ci seront gérées par d'autres sources. "
                    "Concentrez-vous sur les questions de culture générale, de science, de mathématiques ou de sujets non liés à l'actualité. "
                    "En cas d'incertitude, suggérez de vérifier des sources fiables."
                ),
                'it': (
                    "Sei Isabella, una delle assistenti di iURi, un viaggiatore del tempo che ha creato un assistente vocale per Maricá, RJ. Rispondi in modo naturale e diretto in italiano, in 2-3 frasi. "
                    "Evita di rispondere a domande su notizie o eventi attuali, poiché saranno gestite da altre fonti. "
                    "Concentrati su domande di cultura generale, scienza, matematica o argomenti non legati all'attualità. "
                    "Se l'informazione è incerta, suggerisci di verificare fonti affidabili."
                )
            }[lang]
            payload = {
                "model": "grok-3",
                "messages": [
                    {
                        "role": "system",
                        "content": system_message
                    },
                    {"role": "user", "content": text}
                ],
                "max_tokens": 150,
                "temperature": 0.5,
                "top_p": 0.9
            }

            if lat and lon:
                location_msg = {
                    'pt': f"Localização do usuário: lat={lat}, lon={lon}",
                    'en': f"User location: lat={lat}, lon={lon}",
                    'es': f"Ubicación del usuario: lat={lat}, lon={lon}",
                    'fr': f"Emplacement de l'utilisateur : lat={lat}, lon={lon}",
                    'it': f"Posizione dell'utente: lat={lat}, lon={lon}"
                }[lang]
                payload["messages"].append({"role": "system", "content": location_msg})

            print(f"DEBUG: Enviando solicitud a xAI API: {payload}")
            response = http.post(url, json=payload, headers=headers, timeout=20)
            print(f"DEBUG: Respuesta HTTP: {response.status_code}, {response.text[:100]}...")
            response.raise_for_status()
            result = response.json()
            print(f"DEBUG: Respuesta de xAI API: {result}")

            if 'choices' not in result or not result['choices']:
                print("ERROR: No se encontraron respuestas válidas en la respuesta de xAI")
                error_msg = {
                    'pt': "Não encontrei respostas válidas.",
                    'en': "No valid responses found.",
                    'es': "No se encontraron respuestas válidas.",
                    'fr': "Aucune réponse valide trouvée.",
                    'it': "Nessuna risposta valida trovata."
                }
                return jsonify({"error": error_msg[lang]}), 500

            answer = result['choices'][0]['message']['content']
            print(f"DEBUG: Respuesta recibida del modelo: {answer}")
            modified_answer = answer

        cleaned_answer = re.sub(r'\*\*.*?\*\*', lambda m: m.group(0).replace('**', ''), modified_answer)
        cleaned_answer = re.sub(r'[\U0001F000-\U0001FFFF]', '', cleaned_answer)
        modified_answer = cleaned_answer.strip()
        if not modified_answer:
            print("WARNING: Respuesta vacía, usando respuesta por defecto")
            modified_answer = {
                'pt': "Desculpe, não entendi. Pode repetir?",
                'en': "Sorry, I didn't understand. Can you repeat?",
                'es': "Lo siento, no entendí. ¿Puedes repetir?",
                'fr': "Désolé, je n'ai pas compris. Pouvez-vous répéter ?",
                'it': "Scusa, non ho capito. Puoi ripetere?"
            }[lang]
        return jsonify({"response": modified_answer})

    except requests.exceptions.HTTPError as http_err:
        print(f"ERROR: Error HTTP al conectar con xAI API: {str(http_err)}, Response: {http_err.response.text if http_err.response else 'No response'}")
        error_msg = {
            'pt': f"Erro HTTP ao conectar com xAI API: {str(http_err)}. Tente de novo.",
            'en': f"HTTP error connecting to xAI API: {str(http_err)}. Try again.",
            'es': f"Error HTTP al conectar con la API de xAI: {str(http_err)}. Intenta de nuevo.",
            'fr': f"Erreur HTTP lors de la connexion à l'API xAI : {str(http_err)}. Réessayez.",
            'it': f"Errore HTTP durante la connessione all'API xAI: {str(http_err)}. Riprova."
        }
        return jsonify({"error": error_msg[lang]}), 500
    except requests.exceptions.RequestException as req_err:
        print(f"ERROR: Error de red al conectar con xAI API: {str(req_err)}")
        error_msg = {
            'pt': f"Erro de rede ao conectar com xAI API: {str(req_err)}. Tente de novo.",
            'en': f"Network error connecting to xAI API: {str(req_err)}. Try again.",
            'es': f"Error de red al conectar con la API de xAI: {str(req_err)}. Intenta de nuevo.",
            'fr': f"Erreur réseau lors de la connexion à l'API xAI : {str(req_err)}. Réessayez.",
            'it': f"Errore di rete durante la connessione all'API xAI: {str(req_err)}. Riprova."
        }
        return jsonify({"error": error_msg[lang]}), 500
    except ValueError as json_err:
        print(f"ERROR: Error al procesar la respuesta JSON de xAI API: {str(json_err)}")
        error_msg = {
            'pt': f"Erro ao processar a resposta JSON: {str(json_err)}. Tente de novo.",
            'en': f"Error processing JSON response: {str(json_err)}. Try again.",
            'es': f"Error al procesar la respuesta JSON: {str(json_err)}. Intenta de nuevo.",
            'fr': f"Erreur lors du traitement de la réponse JSON : {str(json_err)}. Réessayez.",
            'it': f"Errore durante l'elaborazione della risposta JSON: {str(json_err)}. Riprova."
        }
        return jsonify({"error": error_msg[lang]}), 500
    except Exception as e:
        print(f"ERROR: Error inesperado al procesar la solicitud en /ask-ai: {str(e)}")
        error_msg = {
            'pt': f"Erro inesperado ao processar a solicitação: {str(e)}. Tente de novo.",
            'en': f"Unexpected error processing the request: {str(e)}. Try again.",
            'es': f"Error inesperado al procesar la solicitud: {str(e)}. Intenta de nuevo.",
            'fr': f"Erreur inattendue lors du traitement de la demande : {str(e)}. Réessayez.",
            'it': f"Errore imprevisto durante l'elaborazione della richiesta: {str(e)}. Riprova."
        }
        return jsonify({"error": error_msg[lang]}), 500

@app.route('/speak', methods=['POST'])
def speak():
    print("DEBUG: Solicitud recibida en /speak")
    try:
        data = request.get_json()
        if not data or 'text' not in data:
            print("ERROR: No se proporcionó texto para sintetizar audio")
            return jsonify({"error": "No se proporcionó texto"}), 400

        text = data['text']
        voice_name = data.get('voice', 'pt-BR-YaraNeural')
        print(f"DEBUG: Procesando texto para sintetizar: {text}, voz: {voice_name}")
        valid_voices = [
            'pt-BR-YaraNeural',
            'en-US-JennyNeural',
            'es-AR-DaniaNeural',
            'fr-FR-DeniseNeural',
            'it-IT-IsabellaNeural'
        ]
        if voice_name not in valid_voices:
            print(f"ERROR: Voz no válida. Opciones disponibles: {valid_voices}")
            return jsonify({"error": f"Voz no válida. Opciones disponibles: {valid_voices}"}), 400

        if not AZURE_SPEECH_KEY:
            print("ERROR: AZURE_SPEECH_KEY no está configurada")
            return jsonify({"error": "Falta la clave de API de Azure Speech"}), 500

        # Detectar idioma del texto
        detected_lang = detect_language_nlp(text) or detect_language(text, voice_name)
        expected_lang = {
            'pt-BR-YaraNeural': 'pt',
            'en-US-JennyNeural': 'en',
            'es-AR-DaniaNeural': 'es',
            'fr-FR-DeniseNeural': 'fr',
            'it-IT-IsabellaNeural': 'it'
        }[voice_name]
        lang = {
            'pt': 'pt-BR',
            'en': 'en-US',
            'es': 'es-AR',
            'fr': 'fr-FR',
            'it': 'it-IT'
        }.get(detected_lang, expected_lang)

        if detected_lang != expected_lang:
            print(f"WARNING: Idioma detectado ({detected_lang}) no coincide con la voz ({voice_name}, esperado {expected_lang}), usando {lang}")

        # Sanitizar el texto
        text = re.sub(r'[^\w\s.,!?\'-]', '', text)  # Elimina caracteres no permitidos
        text = text.replace('"', "'")  # Reemplaza comillas dobles por simples
        text = text.strip()
        if not text:
            print("ERROR: Texto vacío después de sanitizar")
            return jsonify({"error": "El texto está vacío después de sanitizar"}), 400

        ssml = f"""
        <speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='{lang}'>
            <voice name='{voice_name}'>
                {text}
            </voice>
        </speak>
        """

        url = f"https://{AZURE_REGION}.tts.speech.microsoft.com/cognitiveservices/v1"
        headers = {
            "Ocp-Apim-Subscription-Key": AZURE_SPEECH_KEY,
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": "riff-8khz-16bit-mono-pcm"  # Formato WAV para mejor alineación
        }

        print(f"DEBUG: Enviando solicitud a Azure Speech API: {url}")
        response = http.post(url, headers=headers, data=ssml.encode('utf-8'))
        print(f"DEBUG: Respuesta de Azure: {response.status_code}, {response.text[:100]}...")
        if response.status_code != 200:
            error_msg = f"Error al sintetizar audio: {response.status_code} - {response.text}"
            print(f"ERROR: {error_msg}")
            return jsonify({"error": error_msg}), response.status_code

        print(f"DEBUG: Audio generado con Azure Text-to-Speech (voz {voice_name})")
        return send_file(
            io.BytesIO(response.content),
            mimetype="audio/wav",
            as_attachment=True,
            download_name="response.wav"
        )

    except Exception as e:
        print(f"ERROR: Error al generar audio: {str(e)}")
        return jsonify({"error": f"Error al generar audio: {str(e)}"}), 500

@app.route('/scrape-activities', methods=['GET'])
def scrape_activities():
    try:
        # Añadir un retraso para ser respetuosos con el servidor
        print(f"DEBUG: Aplicando retraso de {SCRAPE_DELAY} segundos antes de scrapear")
        time.sleep(SCRAPE_DELAY)

        # Scraping de Wikiloc
        url = "https://www.wikiloc.com/trails/hiking/brazil/rio-de-janeiro/marica"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5"
        }
        print(f"DEBUG: Enviando solicitud a Wikiloc: {url}")
        response = http.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'lxml')

        trails = []
        # Buscar elementos de rutas (más flexible para cambios en la estructura HTML)
        trail_elements = soup.select('div.trail__title, div.trail-item, a.trail-link')
        if not trail_elements:
            print("DEBUG: No se encontraron elementos de rutas. HTML retornado (primeros 500 caracteres):")
            print(response.text[:500])
            return jsonify({
                "activities": "No encontré rutas de senderismo en Maricá. Es posible que la estructura del sitio haya cambiado. Intenta buscar manualmente en wikiloc.com."
            })

        for trail in trail_elements[:3]:  # Limitamos a 3 resultados
            link_tag = trail if trail.name == 'a' else trail.find('a')
            if link_tag and 'href' in link_tag.attrs and link_tag.text.strip():
                title = link_tag.text.strip()
                link = link_tag['href']
                # Asegurar que el enlace sea completo
                if not link.startswith('http'):
                    link = f"https://www.wikiloc.com{link}"
                trails.append({"title": title, "link": link})
                print(f"DEBUG: Ruta encontrada: {title} - {link}")
            else:
                print("DEBUG: Elemento de ruta sin enlace o título válido. Saltando...")

        if not trails:
            print("DEBUG: No se encontraron rutas válidas en Wikiloc")
            return jsonify({
                "activities": "No encontré rutas de senderismo en Maricá. Intenta buscar manualmente en wikiloc.com."
            })

        # Formatear respuesta
        response_text = "Aquí tienes algunas rutas de senderismo en Maricá desde Wikiloc:\n"
        for trail in trails:
            response_text += f"- {trail['title']}: {trail['link']}\n"

        return jsonify({"activities": response_text})

    except requests.exceptions.HTTPError as http_err:
        print(f"ERROR: Error HTTP al scrapear Wikiloc: {str(http_err)}")
        return jsonify({
            "activities": "Error al buscar rutas en Wikiloc. Intenta de nuevo más tarde."
        }), 500
    except requests.exceptions.RequestException as req_err:
        print(f"ERROR: Error de red al scrapear Wikiloc: {str(req_err)}")
        return jsonify({
            "activities": "Error de red al buscar rutas en Wikiloc. Intenta de nuevo más tarde."
        }), 500
    except Exception as e:
        print(f"ERROR: Error inesperado al scrapear Wikiloc: {str(e)}")
        return jsonify({
            "activities": "Error al buscar rutas en Wikiloc. Intenta de nuevo más tarde."
        }), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 8080))
    print(f"DEBUG: Iniciando servidor en puerto {port}")
    app.run(host='0.0.0.0', port=port, debug=True)  # Debug habilitado para desarrollo local