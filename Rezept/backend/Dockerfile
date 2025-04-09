# Basis-Image
FROM python:3.9-slim

# Arbeitsverzeichnis setzen
WORKDIR /app

# Netcat installieren für das Warten auf die Datenbank im entrypoint.sh
RUN apt-get update && apt-get install -y netcat-openbsd

# Abhängigkeiten installieren
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Anwendung kopieren
COPY . .

# Skript ausführbar machen
RUN chmod +x entrypoint.sh

# Startbefehl
ENTRYPOINT ["./entrypoint.sh"]