FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt 

# Sprachmodelle installieren in einem separaten Schritt
RUN pip install --no-cache-dir spacy==3.2.0
RUN python -m spacy download de_core_news_sm || echo "Modell-Download fehlgeschlagen, wird später im Container erledigt"
RUN python -c "import nltk; nltk.download('punkt')" || echo "NLTK-Download fehlgeschlagen, wird später im Container erledigt"

COPY . .

# Erstelle und stelle sicher, dass das Upload-Verzeichnis existiert
RUN mkdir -p uploads && chmod 775 uploads

EXPOSE 5021

CMD ["python", "app.py"]