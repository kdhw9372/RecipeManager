import os
import numpy as np
import tensorflow as tf
from tensorflow.keras.preprocessing.text import Tokenizer
from tensorflow.keras.preprocessing.sequence import pad_sequences
from tensorflow.keras.models import Sequential, load_model
from tensorflow.keras.layers import Dense, Embedding, GlobalAveragePooling1D
from sklearn.preprocessing import LabelEncoder
from app import db, celery
from app.models import Recipe, Category, RecipeCategory

class AIService:
    """Service für KI-basierte Funktionen wie Rezeptklassifikation"""
    
    def __init__(self, model_path='/app/models'):
        self.model_path = model_path
        self.model = None
        self.tokenizer = None
        self.label_encoder = None
        self.max_sequence_length = 500
        
        # Verzeichnis für Modelle erstellen, falls nicht vorhanden
        os.makedirs(model_path, exist_ok=True)
        
        # Versuchen, das Modell zu laden, falls vorhanden
        self._load_model()
    
    def _load_model(self):
        """Lädt ein trainiertes Modell, falls vorhanden"""
        model_file = os.path.join(self.model_path, 'recipe_classifier.h5')
        tokenizer_file = os.path.join(self.model_path, 'tokenizer.pickle')
        encoder_file = os.path.join(self.model_path, 'label_encoder.pickle')
        
        if os.path.exists(model_file) and os.path.exists(tokenizer_file) and os.path.exists(encoder_file):
            try:
                import pickle
                
                # Modell laden
                self.model = load_model(model_file)
                
                # Tokenizer laden
                with open(tokenizer_file, 'rb') as handle:
                    self.tokenizer = pickle.load(handle)
                
                # Label-Encoder laden
                with open(encoder_file, 'rb') as handle:
                    self.label_encoder = pickle.load(handle)
                
                return True
            except Exception as e:
                print(f"Fehler beim Laden des Modells: {str(e)}")
        
        return False
    
    def train_recipe_classifier(self, force_retrain=False):
        """Trainiert einen Klassifikator basierend auf vorhandenen Rezepten"""
        # Prüfen, ob bereits ein Modell existiert und kein Neutraining erzwungen wird
        if self.model is not None and not force_retrain:
            return {'status': 'already_trained'}
        
        # Rezepte mit Kategorien abrufen
        recipes = db.session.query(
            Recipe.id,
            Recipe.title,
            Recipe.description,
            Recipe.instructions,
            Category.name.label('category_name')
        ).join(
            RecipeCategory, Recipe.id == RecipeCategory.recipe_id
        ).join(
            Category, RecipeCategory.category_id == Category.id
        ).all()
        
        if not recipes or len(recipes) < 50:  # Mindestanzahl für Training
            return {
                'status': 'insufficient_data',
                'message': 'Nicht genügend Daten zum Trainieren des Modells'
            }
        
        # Daten vorbereiten
        texts = []
        labels = []
        
        for recipe in recipes:
            # Text zusammenfügen (Titel, Beschreibung, Anleitung)
            text = f"{recipe.title} {recipe.description or ''} {recipe.instructions or ''}"
            texts.append(text)
            labels.append(recipe.category_name)
        
        # Tokenizer für Texte erstellen
        self.tokenizer = Tokenizer(num_words=10000)
        self.tokenizer.fit_on_texts(texts)
        
        # Texte in Sequenzen umwandeln
        sequences = self.tokenizer.texts_to_sequences(texts)
        padded_sequences = pad_sequences(sequences, maxlen=self.max_sequence_length)
        
        # Labels kodieren
        self.label_encoder = LabelEncoder()
        encoded_labels = self.label_encoder.fit_transform(labels)
        num_classes = len(self.label_encoder.classes_)
        
        # Modell erstellen
        self.model = Sequential([
            Embedding(10000, 16, input_length=self.max_sequence_length),
            GlobalAveragePooling1D(),
            Dense(24, activation='relu'),
            Dense(num_classes, activation='softmax')
        ])
        
        # Modell kompilieren
        self.model.compile(
            loss='sparse_categorical_crossentropy',
            optimizer='adam',
            metrics=['accuracy']
        )
        
        # Modell trainieren
        history = self.model.fit(
            padded_sequences,
            encoded_labels,
            epochs=15,
            validation_split=0.2,
            verbose=1
        )
        
        # Modell speichern
        import pickle
        model_file = os.path.join(self.model_path, 'recipe_classifier.h5')
        tokenizer_file = os.path.join(self.model_path, 'tokenizer.pickle')
        encoder_file = os.path.join(self.model_path, 'label_encoder.pickle')
        
        self.model.save(model_file)
        
        with open(tokenizer_file, 'wb') as handle:
            pickle.dump(self.tokenizer, handle, protocol=pickle.HIGHEST_PROTOCOL)
        
        with open(encoder_file, 'wb') as handle:
            pickle.dump(self.label_encoder, handle, protocol=pickle.HIGHEST_PROTOCOL)
        
        # Trainingsergebnisse
        val_accuracy = history.history['val_accuracy'][-1]
        
        return {
            'status': 'success',
            'accuracy': val_accuracy,
            'num_recipes': len(texts),
            'num_categories': num_classes
        }
    
    def classify_recipe(self, title, description, instructions):
        """Klassifiziert ein Rezept basierend auf seinem Text"""
        if self.model is None or self.tokenizer is None or self.label_encoder is None:
            success = self._load_model()
            if not success:
                return {
                    'status': 'error',
                    'message': 'Kein trainiertes Modell verfügbar'
                }
        
        # Text vorbereiten
        text = f"{title} {description or ''} {instructions or ''}"
        sequences = self.tokenizer.texts_to_sequences([text])
        padded_sequence = pad_sequences(sequences, maxlen=self.max_sequence_length)
        
        # Vorhersage durchführen
        predictions = self.model.predict(padded_sequence)
        predicted_index = np.argmax(predictions[0])
        predicted_category = self.label_encoder.inverse_transform([predicted_index])[0]
        confidence = float(predictions[0][predicted_index])
        
        # Top-3 Kategorien mit Wahrscheinlichkeiten
        top_indices = np.argsort(predictions[0])[-3:][::-1]
        top_categories = []
        
        for idx in top_indices:
            category = self.label_encoder.inverse_transform([idx])[0]
            probability = float(predictions[0][idx])
            top_categories.append({
                'category': category,
                'probability': probability
            })
        
        return {
            'status': 'success',
            'category': predicted_category,
            'confidence': confidence,
            'top_categories': top_categories
        }

@celery.task
def train_recipe_classifier(force_retrain=False):
    """Celery-Task zum Trainieren des Rezeptklassifikators"""
    service = AIService()
    return service.train_recipe_classifier(force_retrain)

@celery.task
def classify_recipe_batch(recipe_ids):
    """Klassifiziert mehrere Rezepte und weist ihnen automatisch Kategorien zu"""
    service = AIService()
    
    # Prüfen, ob ein Modell verfügbar ist
    if service.model is None:
        success = service._load_model()
        if not success:
            return {
                'status': 'error',
                'message': 'Kein trainiertes Modell verfügbar'
            }
    
    results = []
    
    for recipe_id in recipe_ids:
        recipe = Recipe.query.get(recipe_id)
        if not recipe:
            results.append({
                'recipe_id': recipe_id,
                'status': 'error',
                'message': 'Rezept nicht gefunden'
            })
            continue
        
        # Rezept klassifizieren
        classification = service.classify_recipe(
            recipe.title,
            recipe.description,
            recipe.instructions
        )
        
        if classification['status'] == 'success':
            # Nur Kategorien mit hoher Konfidenz (> 0.5) zuweisen
            for category_data in classification['top_categories']:
                if category_data['probability'] > 0.5:
                    # Kategorie in der Datenbank suchen oder erstellen
                    category = Category.query.filter_by(name=category_data['category']).first()
                    if not category:
                        continue
                    
                    # Prüfen, ob die Zuordnung bereits existiert
                    exists = db.session.query(RecipeCategory).filter_by(
                        recipe_id=recipe.id,
                        category_id=category.id
                    ).first() is not None
                    
                    if not exists:
                        # Kategorie dem Rezept zuweisen
                        recipe_category = RecipeCategory(
                            recipe_id=recipe.id,
                            category_id=category.id
                        )
                        db.session.add(recipe_category)
            
            db.session.commit()
            
            results.append({
                'recipe_id': recipe_id,
                'status': 'success',
                'categories': [c['category'] for c in classification['top_categories'] if c['probability'] > 0.5]
            })
        else:
            results.append({
                'recipe_id': recipe_id,
                'status': 'error',
                'message': classification.get('message', 'Klassifikation fehlgeschlagen')
            })
    
    return {
        'status': 'success',
        'processed': len(results),
        'results': results
    }