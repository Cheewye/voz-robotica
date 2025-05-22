FROM python:3.9-slim

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libavcodec-extra \
    && rm -rf /var/lib/apt/lists/*

# Configurar el directorio de trabajo
WORKDIR /app

# Copiar requirements.txt e instalar dependencias de Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto del código
COPY . .

# Exponer el puerto
EXPOSE 8080

# Comando para iniciar la aplicación
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "4", "--timeout", "30", "appv2:app"]