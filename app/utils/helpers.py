import os

def read_secret(key_name):
    """
    Lee el valor de una clave desde variables de entorno o archivos físicos.
    - Primero intenta desde os.getenv (útil para .env y Cloud Run).
    - Si no, intenta leer desde /secrets/{key_name}.
    - Devuelve None si no se encuentra.
    """
    env_key = key_name.upper().replace('-', '_')  # Ej: 'openweather-api-key' -> 'OPENWEATHER_API_KEY'
    value = os.getenv(env_key)
    if value:
        print(f"DEBUG: Clave '{env_key}' encontrada en variables de entorno.")
        return value

    # Fallback: intentar leer desde archivo físico
    file_path = f"/secrets/{key_name}"
    try:
        with open(file_path, 'r') as f:
            value = f.read().strip()
            print(f"DEBUG: Clave '{key_name}' encontrada en archivo {file_path}.")
            return value
    except FileNotFoundError:
        print(f"ADVERTENCIA: No se encontró archivo de secreto en {file_path}.")
    except Exception as e:
        print(f"ERROR: No se pudo leer el secreto para '{key_name}': {e}")

    print(f"ADVERTENCIA: Clave '{key_name}' no encontrada en variables de entorno ni en archivos.")
    return None

def detect_language_nlp(text):
    """
    Detecta el idioma del texto usando NLP.
    Esta es una implementación básica; ajusta según tus necesidades.
    """
    # Ejemplo simple: siempre devuelve 'es' (español)
    return 'es'

def detect_language(text, voice_name):
    """
    Detecta el idioma del texto basado en el nombre de la voz o el contenido.
    Esta es una implementación básica; ajusta según tus necesidades.
    """
    # Ejemplo simple: siempre devuelve 'es' (español)
    return 'es'

def is_news_related(query):
    """
    Determina si la consulta está relacionada con noticias.
    Esta es una implementación básica; ajusta según tus necesidades.
    """
    # Ejemplo simple: siempre devuelve False
    return False

def query_newsapi(query):
    """
    Consulta la API de noticias.
    Esta es una implementación básica; ajusta según tus necesidades.
    """
    # Ejemplo simple: devuelve un diccionario vacío
    return {}

def extract_city(text):
    """
    Extrae el nombre de la ciudad del texto.
    Esta es una implementación básica; ajusta según tus necesidades.
    """
    # Ejemplo simple: siempre devuelve 'Madrid'
    return 'Madrid'

def add_header(response):
    """
    Agrega encabezados a la respuesta.
    Esta es una implementación básica; ajusta según tus necesidades.
    """
    # Ejemplo simple: no hace nada
    return response