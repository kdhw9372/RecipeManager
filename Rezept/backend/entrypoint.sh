#!/bin/sh

# Auf die Datenbank warten
echo "Warte auf PostgreSQL..."
while ! nc -z db 5432; do
  sleep 0.1
done
echo "PostgreSQL gestartet"

# Datenbankmigration ausführen
flask db upgrade

# Anwendung starten
gunicorn --bind 0.0.0.0:5000 --timeout 120 "app:create_app()"