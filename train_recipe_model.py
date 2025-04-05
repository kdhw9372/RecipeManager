"""
Skript zum Trainieren des ML-Modells für die Rezeptextraktion.
"""
import os
import pandas as pd
import argparse
from ml_recipe_extractor import MLRecipeExtractor
import logging
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.pipeline import Pipeline
from sklearn.model_selection import train_test_split
import joblib

# Logging konfigurieren
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_training_data(annotations_file: str) -> pd.DataFrame:
    """
    Erstellt Trainingsdaten aus einer Annotationsdatei.
    
    Args:
        annotations_file: Pfad zur CSV-Datei mit Annotationen
    
    Returns:
        DataFrame mit aufbereiteten Trainingsdaten
    """
    # CSV-Datei mit Annotationen laden
    # Format: text,label (label ist 'title', 'ingredients' oder 'instructions')
    df = pd.read_csv(annotations_file, encoding='utf-8')
    
    # Nur Zeilen mit Labels behalten
    df = df[df['label'].notna() & (df['label'] != '')]
    
    # Sicherstellen, dass die notwendigen Spalten vorhanden sind
    if 'text' not in df.columns or 'label' not in df.columns:
        raise ValueError("Die Annotationsdatei muss 'text' und 'label' Spalten enthalten")
    
    # Labels zu Strings konvertieren (falls sie als Zahlen geladen wurden)
    df['label'] = df['label'].astype(str)
    
    return df

def main():
    parser = argparse.ArgumentParser(description='Trainiere ML-Modell für Rezeptextraktion')
    parser.add_argument('annotations', help='Pfad zur CSV-Datei mit annotierten Textabschnitten')
    parser.add_argument('--output', '-o', default='models/recipe_classifier.joblib',
                        help='Pfad zum Speichern des trainierten Modells')
    args = parser.parse_args()
    
    # Prüfen, ob die Annotationsdatei existiert
    if not os.path.exists(args.annotations):
        logger.error(f"Annotationsdatei nicht gefunden: {args.annotations}")
        return
    
    # Trainingsdaten erstellen
    try:
        training_data = create_training_data(args.annotations)
        logger.info(f"Trainingsdaten mit {len(training_data)} Einträgen geladen")
    except Exception as e:
        logger.error(f"Fehler beim Laden der Trainingsdaten: {str(e)}")
        return
    
    # Ausgabeverzeichnis erstellen, falls es nicht existiert
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    
    # Features und Labels trennen
    X = training_data['text']
    y = training_data['label']
    
    # Traings- und Testdaten aufteilen
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    # Pipeline mit Text-Vektorisierung und Classifier erstellen
    model = Pipeline([
        ('vectorizer', CountVectorizer(ngram_range=(1, 2), min_df=2)),
        ('classifier', RandomForestClassifier(n_estimators=100, random_state=42))
    ])
    
    # Modell trainieren
    model.fit(X_train, y_train)
    
    # Modell evaluieren
    accuracy = model.score(X_test, y_test)
    logger.info(f"Modellgenauigkeit: {accuracy:.2f}")
    
    # Modell speichern
    joblib.dump(model, args.output)
    logger.info(f"Modell erfolgreich unter {args.output} gespeichert")

if __name__ == "__main__":
    main()