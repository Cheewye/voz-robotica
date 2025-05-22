#!/bin/bash

# Variables
PROJECT_ID="voz-robotica"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_DIR=~/voz_robotica_backup_$TIMESTAMP

# Crear directorio de backup
mkdir -p $BACKUP_DIR

# 1. Backup del código local (ajustá el path si tu proyecto está en otro lugar)
echo "Haciendo backup del código local..."
cp -r ~/voz_robotica/* $BACKUP_DIR/

# 2. Exportar la configuración actual de Cloud Run
echo "Exportando configuración de Cloud Run..."
gcloud run services describe voz-robotica-service \
  --region southamerica-east1 \
  --format export > $BACKUP_DIR/cloud_run_config_$TIMESTAMP.yaml

# 3. Hacer backup de los secretos en Secret Manager (solo nombres y versiones, no valores)
echo "Listando secretos para backup..."
gcloud secrets list --project $PROJECT_ID > $BACKUP_DIR/secrets_list_$TIMESTAMP.txt
for SECRET in openweather-api-key supergrok-api-key azure-speech-key news-api-key google-credentials; do
  gcloud secrets versions list $SECRET --project $PROJECT_ID >> $BACKUP_DIR/secrets_versions_$TIMESTAMP.txt
done

# 4. Hacer backup de las imágenes de contenedores en Google Container Registry
echo "Etiquetando imagen actual como backup..."
docker pull gcr.io/voz-robotica/voz-robotica:latest
docker tag gcr.io/voz-robotica/voz-robotica:latest gcr.io/voz-robotica/voz-robotica:backup_$TIMESTAMP
docker push gcr.io/voz-robotica/voz-robotica:backup_$TIMESTAMP

echo "Backup completado en $BACKUP_DIR"