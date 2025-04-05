"""
Erweitertes Skript zum Trainieren des ML-Modells für Rezeptextraktion mit verbesserten Features.
"""
import os
import pandas as pd
import numpy as np
import argparse
import logging
import joblib
import time
from sklearn.model_selection import train_test_split, GridSearchCV
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import Pipeline
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.svm import LinearSVC
from sklearn.metrics import classification_report, confusion_matrix
from tqdm import tqdm  # Für Fortschrittsanzeigen

# Logging konfigurieren
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_training_data(annotations_file):
    """Erstellt Trainingsdaten aus einer annotierten CSV-Datei."""
    try:
        # CSV mit expliziter Kodierung lesen
        print(f"Lade Annotationsdatei: {annotations_file}")
        df = pd.read_csv(annotations_file, encoding='utf-8')
        logger.info(f"CSV geladen mit {len(df)} Zeilen")
        
        # Nur Zeilen mit Labels behalten
        df = df[df['label'].notna() & (df['label'] != '')]
        
        # Sicherstellen, dass die Labels Strings sind
        df['label'] = df['label'].astype(str)
        
        # Informationen anzeigen
        label_counts = df['label'].value_counts()
        logger.info(f"Label-Verteilung: {label_counts.to_dict()}")
        
        print(f"Daten erfolgreich geladen - {len(df)} gültige Einträge")
        return df
    except Exception as e:
        logger.error(f"Fehler beim Laden der Trainingsdaten: {str(e)}")
        raise

def extract_text_features(text):
    """Extrahiert zusätzliche Features aus dem Text."""
    if not isinstance(text, str):
        return {
            'length': 0,
            'word_count': 0,
            'contains_numbers': False,
            'contains_units': False
        }
    
    features = {
        'length': len(text),
        'word_count': len(text.split()),
        'contains_numbers': any(c.isdigit() for c in text),
        'contains_units': any(unit in text.lower() for unit in ['g', 'kg', 'ml', 'l', 'el', 'tl'])
    }
    
    return features

def train_and_evaluate_model(X_train, X_test, y_train, y_test):
    """Trainiert und evaluiert verschiedene Modelle und wählt das beste aus."""
    # Definiere verschiedene Klassifizierer
    classifiers = [
        ('rf', RandomForestClassifier(random_state=42)),
        ('gb', GradientBoostingClassifier(random_state=42)),
        ('lr', LogisticRegression(max_iter=1000, random_state=42)),
        ('svc', LinearSVC(max_iter=5000, random_state=42))
    ]
    
    best_accuracy = 0
    best_model = None
    best_model_name = None
    
    # Für jeden Klassifizierer
    for name, clf in tqdm(classifiers, desc="Training der Modelle", unit="Modell"):
        print(f"\n{'-'*50}")
        print(f"Training des {name}-Modells gestartet...")
        start_time = time.time()
        
        # Pipeline mit TF-IDF Vektorisierung
        pipeline = Pipeline([
            ('tfidf', TfidfVectorizer(ngram_range=(1, 3), min_df=2, sublinear_tf=True)),
            ('clf', clf)
        ])
        
        # Modell trainieren
        pipeline.fit(X_train, y_train)
        
        # Modell evaluieren
        accuracy = pipeline.score(X_test, y_test)
        end_time = time.time()
        training_time = end_time - start_time
        
        print(f"Training abgeschlossen in {training_time:.2f} Sekunden")
        print(f"{name} Genauigkeit: {accuracy:.4f}")
        
        # Vorhersage und detaillierte Metriken
        y_pred = pipeline.predict(X_test)
        report = classification_report(y_test, y_pred)
        print(f"\nKlassifikationsbericht für {name}:\n{report}")
        
        # Wenn dies das beste Modell ist, speichern
        if accuracy > best_accuracy:
            best_accuracy = accuracy
            best_model = pipeline
            best_model_name = name
            print(f"Neues bestes Modell: {name} mit Genauigkeit {accuracy:.4f}")
    
    print(f"\n{'-'*50}")
    print(f"Bestes Modell: {best_model_name} mit Genauigkeit {best_accuracy:.4f}")
    
    # Konfusionsmatrix für das beste Modell
    if best_model:
        y_pred = best_model.predict(X_test)
        cm = confusion_matrix(y_test, y_pred)
        print(f"\nKonfusionsmatrix für das beste Modell ({best_model_name}):")
        print(cm)
    
    return best_model

def optimize_best_model(X_train, X_test, y_train, y_test, model_type='rf'):
    """Führt Hyperparameter-Optimierung für das beste Modell durch."""
    print(f"\n{'-'*50}")
    print(f"Optimiere Hyperparameter für {model_type}...")
    
    # Parameter-Grid je nach Modelltyp
    if model_type == 'rf':
        # Random Forest
        pipeline = Pipeline([
            ('tfidf', TfidfVectorizer()),
            ('clf', RandomForestClassifier(random_state=42))
        ])
        
        param_grid = {
            'tfidf__ngram_range': [(1, 1), (1, 2), (1, 3)],
            'tfidf__min_df': [1, 2, 3],
            'tfidf__sublinear_tf': [True, False],
            'clf__n_estimators': [100, 200, 300],
            'clf__max_depth': [None, 10, 20, 30],
            'clf__min_samples_split': [2, 5, 10]
        }
    elif model_type == 'gb':
        # Gradient Boosting
        pipeline = Pipeline([
            ('tfidf', TfidfVectorizer()),
            ('clf', GradientBoostingClassifier(random_state=42))
        ])
        
        param_grid = {
            'tfidf__ngram_range': [(1, 1), (1, 2), (1, 3)],
            'tfidf__min_df': [1, 2, 3],
            'clf__n_estimators': [100, 200],
            'clf__learning_rate': [0.01, 0.1, 0.2],
            'clf__max_depth': [3, 5, 7]
        }
    else:
        # Logistic Regression (default fallback)
        pipeline = Pipeline([
            ('tfidf', TfidfVectorizer()),
            ('clf', LogisticRegression(random_state=42, max_iter=1000))
        ])
        
        param_grid = {
            'tfidf__ngram_range': [(1, 1), (1, 2), (1, 3)],
            'tfidf__min_df': [1, 2, 3],
            'tfidf__sublinear_tf': [True, False],
            'clf__C': [0.1, 1.0, 10.0],
            'clf__solver': ['liblinear', 'saga']
        }
    
    # Grid-Search mit Fortschrittsanzeige
    print(f"Starte Grid-Search mit {len(param_grid)} Parametern...")
    total_combinations = 1
    for param in param_grid.values():
        total_combinations *= len(param)
    print(f"Insgesamt {total_combinations} Kombinationen zu testen")
    
    # Grid-Search durchführen (mit eingeschränktem Grid für Effizienz)
    start_time = time.time()
    grid_search = GridSearchCV(pipeline, param_grid, cv=3, n_jobs=-1, verbose=2)
    grid_search.fit(X_train, y_train)
    end_time = time.time()
    
    print(f"Grid-Search abgeschlossen in {end_time - start_time:.2f} Sekunden")
    
    # Bestes Modell ausgeben
    print(f"Beste Parameter: {grid_search.best_params_}")
    print(f"Beste CV-Genauigkeit: {grid_search.best_score_:.4f}")
    
    # Auf Testdaten evaluieren
    best_model = grid_search.best_estimator_
    accuracy = best_model.score(X_test, y_test)
    print(f"Test-Genauigkeit mit optimierten Parametern: {accuracy:.4f}")
    
    return best_model

def main():
    parser = argparse.ArgumentParser(description='Trainiere erweitertes ML-Modell für Rezeptextraktion')
    parser.add_argument('annotations', help='Pfad zur CSV-Datei mit annotierten Textabschnitten')
    parser.add_argument('--output', '-o', default='models/recipe_classifier_enhanced.joblib',
                        help='Pfad zum Speichern des trainierten Modells')
    parser.add_argument('--optimize', '-opt', action='store_true',
                        help='Hyperparameter-Optimierung durchführen')
    args = parser.parse_args()
    
    # Prüfen, ob die Annotationsdatei existiert
    if not os.path.exists(args.annotations):
        logger.error(f"Annotationsdatei nicht gefunden: {args.annotations}")
        return
    
    # Beginn des Trainings anzeigen
    print(f"\n{'='*50}")
    print(f"ML-MODELL-TRAINING FÜR REZEPTEXTRAKTION GESTARTET")
    print(f"{'='*50}")
    start_time = time.time()
    
    # Trainingsdaten laden
    try:
        training_data = create_training_data(args.annotations)
        logger.info(f"Trainingsdaten mit {len(training_data)} Einträgen geladen")
    except Exception as e:
        logger.error(f"Fehler beim Laden der Trainingsdaten: {str(e)}")
        return
    
    # Daten für Training und Test aufteilen
    print("Teile Daten in Training- und Testsets auf...")
    X = training_data['text']
    y = training_data['label']
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    print(f"Training mit {len(X_train)} Samples, Test mit {len(X_test)} Samples")
    
    # Ausgabeverzeichnis erstellen, falls es nicht existiert
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    
    if args.optimize:
        print("Modus: Hyperparameter-Optimierung (kann länger dauern)")
        # Hyperparameter-Optimierung
        best_model = optimize_best_model(X_train, X_test, y_train, y_test)
    else:
        print("Modus: Modellvergleich")
        # Verschiedene Modelle trainieren und das beste auswählen
        best_model = train_and_evaluate_model(X_train, X_test, y_train, y_test)
    
    # Modell speichern
    print(f"Speichere Modell unter {args.output}...")
    joblib.dump(best_model, args.output)
    print(f"Modell erfolgreich gespeichert!")
    
    # Ende des Trainings
    end_time = time.time()
    total_time = end_time - start_time
    print(f"\n{'='*50}")
    print(f"TRAINING ABGESCHLOSSEN in {total_time:.2f} Sekunden")
    print(f"{'='*50}")

if __name__ == "__main__":
    main()