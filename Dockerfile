FROM python:3.11-slim

# Installation des dépendances système minimales
RUN apt-get update && apt-get install -y \
    unixodbc \
    unixodbc-dev \
    gnupg2 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV PYTHONPATH=/app

# On commence par les dépendances pour profiter du cache Docker
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# On copie le reste (le .dockerignore fera le tri)
COPY . .

# On s'assure que les dossiers de logs/data existent (vides)
RUN mkdir -p data/logs

# Ports pour API et UI
EXPOSE 8000 8001

# L'entrée sera définie au lancement (command dans docker-compose ou Azure)