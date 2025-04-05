"""
Service zur ML-gestützten Extraktion von Rezeptinformationen aus PDF-Dateien.
"""
import re
import os
import pdfplumber
import pandas as pd
import numpy as np
import nltk
from nltk.tokenize import sent_tokenize
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.pipeline import Pipeline
from sklearn.model_selection import train_test_split
import joblib
import logging
from typing import Dict, Any, List, Tuple, Optional, Union

# Logging konfigurieren
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# NLTK-Daten herunterladen (wenn nötig)
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt')

class MLRecipeExtractor:
    """
    Klasse zur ML-gestützten Extraktion von Rezeptinformationen aus PDFs.
    Verwendet ein Random Forest-Modell zur Klassifikation von Textabschnitten.
    """
    
    # Typische Einheitenwörter in Rezepten
    UNITS = [
        'g', 'kg', 'ml', 'l', 'el', 'tl', 'prise', 'prisen', 'stück', 'stk',
        'bund', 'zehe', 'zehen', 'scheibe', 'scheiben', 'tasse', 'tassen',
        'dose', 'dosen', 'packung', 'päckchen', 'gramm', 'liter', 'milliliter',
        'esslöffel', 'teelöffel'
    ]
    
    # Typische Zutaten
    COMMON_INGREDIENTS = [
        'mehl', 'zucker', 'salz', 'pfeffer', 'öl', 'butter', 'ei', 'eier', 'milch',
        'wasser', 'sahne', 'käse', 'schokolade', 'vanille', 'zimt', 'backpulver',
        'hefe', 'joghurt', 'quark', 'tomaten', 'zwiebel', 'knoblauch', 'karotte',
        'kartoffel', 'reis', 'nudel', 'pasta', 'olivenöl'
    ]
    
    # Typische Kochverben
    COOKING_VERBS = [
        'mischen', 'rühren', 'schneiden', 'hacken', 'kochen', 'braten', 'backen',
        'gießen', 'hinzufügen', 'erhitzen', 'abkühlen', 'garnieren', 'servieren',
        'pürieren', 'stampfen', 'vermengen', 'schlagen', 'kneten', 'formen'
    ]
    
    # Marker für Abschnitte
    SECTION_MARKERS = {
        'title': ['rezept', 'rezept für', 'rezept:', 'zubereitung von', 'zubereitung:'],
        'ingredients': ['zutaten', 'zutaten:', 'zutatenliste', 'einkaufsliste'],
        'instructions': ['zubereitung', 'zubereitung:', 'anleitung', 'anleitung:', 'schritt', 'schritte']
    }
    
    def __init__(self, model_path: Optional[str] = None):
        """
        Initialisiert den RecipeExtractor.
        
        Args:
            model_path: Optionaler Pfad zu einem gespeicherten Modell.
        """
        self.model = None
        if model_path and os.path.exists(model_path):
            try:
                self.model = joblib.load(model_path)
                logger.info(f"Modell aus {model_path} geladen")
            except:
                logger.warning(f"Konnte Modell nicht aus {model_path} laden")
    
    def extract_from_pdf(self, pdf_path: str) -> Dict[str, Any]:
        """
        Extrahiert Rezeptinformationen aus einer PDF-Datei.
        
        Args:
            pdf_path: Pfad zur PDF-Datei
            
        Returns:
            Dictionary mit extrahierten Daten (Titel, Zutaten, Anweisungen)
        """
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF-Datei nicht gefunden: {pdf_path}")
        
        # Text aus PDF extrahieren
        text = self._extract_text_from_pdf(pdf_path)
        if not text.strip():
            raise ValueError(f"Keine Textinhalte in PDF gefunden: {pdf_path}")
        
        # Text in bedeutungsvolle Abschnitte aufteilen
        sections = self._split_into_sections(text)
        
        # Wenn kein Modell vorhanden ist, Fallback auf regelbasierte Extraktion
        if self.model is None:
            logger.warning("Kein Modell geladen, verwende regelbasierte Extraktion")
            return self._extract_rule_based(sections)
        
        # Sonst ML-basierte Extraktion
        return self._extract_ml_based(sections)
    
    def _extract_text_from_pdf(self, pdf_path: str) -> str:
        """Extrahiert den Text aus allen Seiten einer PDF-Datei."""
        full_text = ""
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text() or ""
                    full_text += page_text + "\n\n"
            return full_text
        except Exception as e:
            logger.error(f"Fehler beim Extrahieren des Textes aus der PDF: {e}")
            raise
    
    def _split_into_sections(self, text: str) -> List[str]:
        """Teilt den Text in logische Abschnitte auf."""
        # Zuerst in Absätze aufteilen
        paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
        
        # Dann in sinnvolle Abschnitte aufteilen
        sections = []
        for paragraph in paragraphs:
            # Sehr kurze Absätze als eigene Abschnitte betrachten
            if len(paragraph) < 15:
                if paragraph.strip():
                    sections.append(paragraph)
                continue
            
            # Absätze mit Zeilenumbrüchen erhalten
            if '\n' in paragraph and self._is_likely_list(paragraph):
                sections.append(paragraph)
                continue
            
            # Sonst in Sätze aufteilen
            try:
                sentences = sent_tokenize(paragraph)
                sections.extend(sentences)
            except:
                # Fallback: Einfach den ganzen Paragraphen hinzufügen
                sections.append(paragraph)
        
        return sections
    
    def _is_likely_list(self, text: str) -> bool:
        """Prüft, ob ein Text wahrscheinlich eine Liste oder Aufzählung ist."""
        lines = text.split('\n')
        if len(lines) <= 1:
            return False
        
        # Prüfen, ob mehrere Zeilen mit Zahlen oder Aufzählungszeichen beginnen
        bullet_count = 0
        for line in lines:
            if re.match(r'^\s*(\d+\.|\*|\-|\•|\○|\◦|\-)\s', line):
                bullet_count += 1
        
        return bullet_count >= len(lines) * 0.5  # Mindestens 50% der Zeilen sind Aufzählungen
    
    def _extract_ml_based(self, sections: List[str]) -> Dict[str, Any]:
        """
        Extrahiert Rezeptinformationen basierend auf ML-Klassifikation.
        
        Args:
            sections: Liste von Textabschnitten
            
        Returns:
            Dictionary mit extrahierten Daten
        """
        # Features für jeden Abschnitt extrahieren
        features = pd.DataFrame([
            self._extract_features(section, idx, len(sections)) 
            for idx, section in enumerate(sections)
        ])
        
        # Text-Spalte zum Modell hinzufügen
        features['text'] = sections
        
        # Modell anwenden, um Abschnitte zu klassifizieren
        predictions = self.model.predict(features)
        
        # Ergebnisse nach Kategorie gruppieren
        title_sections = [sections[i] for i, pred in enumerate(predictions) if pred == 'title']
        ingredient_sections = [sections[i] for i, pred in enumerate(predictions) if pred == 'ingredients']
        instruction_sections = [sections[i] for i, pred in enumerate(predictions) if pred == 'instructions']
        
        # Besten Titel auswählen (in der Regel der erste)
        title = title_sections[0] if title_sections else "Unbekanntes Rezept"
        
        # Zutaten und Anweisungen zusammenfügen
        ingredients = "\n".join(ingredient_sections)
        instructions = "\n".join(instruction_sections)
        
        return {
            "title": title,
            "ingredients": ingredients,
            "instructions": instructions
        }
    
    def _extract_rule_based(self, sections: List[str]) -> Dict[str, Any]:
        """
        Fallback-Methode: Extrahiert Rezeptinformationen basierend auf Regeln.
        
        Args:
            sections: Liste von Textabschnitten
            
        Returns:
            Dictionary mit extrahierten Daten
        """
        # Titel extrahieren (in der Regel der erste substantielle Abschnitt)
        title = "Unbekanntes Rezept"
        for section in sections[:5]:  # Nur in den ersten 5 Abschnitten suchen
            if 3 < len(section) < 60 and not any(char.isdigit() for char in section):
                title = section
                break
        
        # Zutaten und Anweisungen mit einfachen Regeln identifizieren
        ingredients = []
        instructions = []
        
        for section in sections:
            # Prüfen, ob es eine Zutat sein könnte
            if self._is_likely_ingredient(section):
                ingredients.append(section)
            # Sonst prüfen, ob es eine Anweisung sein könnte
            elif self._is_likely_instruction(section):
                instructions.append(section)
        
        return {
            "title": title,
            "ingredients": "\n".join(ingredients),
            "instructions": "\n".join(instructions)
        }
    
    def _is_likely_ingredient(self, text: str) -> bool:
        """Prüft, ob ein Text wahrscheinlich eine Zutat beschreibt."""
        text_lower = text.lower()
        
        # Nach Mengenangaben suchen
        if re.search(r'\d+\s*(?:' + '|'.join(self.UNITS) + r')\b', text_lower):
            return True
        
        # Nach typischen Zutaten suchen
        for ingredient in self.COMMON_INGREDIENTS:
            if ingredient in text_lower:
                return True
        
        return False
    
    def _is_likely_instruction(self, text: str) -> bool:
        """Prüft, ob ein Text wahrscheinlich eine Anweisung beschreibt."""
        text_lower = text.lower()
        
        # Nach typischen Kochverben suchen
        for verb in self.COOKING_VERBS:
            if verb in text_lower:
                return True
        
        # Nach nummerierter Anweisung suchen
        if re.search(r'^\s*\d+\.\s', text):
            return True
        
        # Nach imperativem Satzanfang suchen (typisch für Anweisungen)
        for verb in self.COOKING_VERBS:
            if text_lower.split()[0].startswith(verb):
                return True
        
        return False
    
    def _extract_features(self, text: str, position: int, total_sections: int) -> Dict[str, Union[int, float, bool]]:
        """
        Extrahiert numerische Features aus einem Textabschnitt für ML-Klassifikation.
        
        Args:
            text: Der Textabschnitt
            position: Position des Abschnitts im Dokument
            total_sections: Gesamtanzahl der Abschnitte
            
        Returns:
            Dictionary mit Features
        """
        text_lower = text.lower()
        words = text.split()
        
        features = {
            # Strukturelle Features
            'length': len(text),
            'word_count': len(words),
            'avg_word_length': sum(len(w) for w in words) / max(1, len(words)),
            'line_breaks': text.count('\n'),
            'rel_position': position / max(1, total_sections),  # Relative Position im Dokument
            
            # Numerische Features
            'digit_count': sum(c.isdigit() for c in text),
            'digit_to_char_ratio': sum(c.isdigit() for c in text) / max(1, len(text)),
            'has_number_list': bool(re.search(r'^\s*\d+\.', text)),
            'has_bullet_list': bool(re.search(r'^\s*[\*\-\•\○\◦]', text)),
            
            # Zutatenbezogene Features
            'has_units': any(unit in text_lower for unit in self.UNITS),
            'has_amount_pattern': bool(re.search(r'\d+\s*(?:' + '|'.join(self.UNITS) + r')\b', text_lower)),
            'ingredient_word_count': sum(1 for ing in self.COMMON_INGREDIENTS if ing in text_lower),
            
            # Anweisungsbezogene Features
            'verb_count': sum(1 for verb in self.COOKING_VERBS if verb in text_lower),
            'starts_with_verb': any(text_lower.split()[0].startswith(verb) for verb in self.COOKING_VERBS) if words else False,
            
            # Abschnittsmarkierungen
            'has_title_marker': any(marker in text_lower for marker in self.SECTION_MARKERS['title']),
            'has_ingredient_marker': any(marker in text_lower for marker in self.SECTION_MARKERS['ingredients']),
            'has_instruction_marker': any(marker in text_lower for marker in self.SECTION_MARKERS['instructions']),
        }
        
        return features
    
    def train(self, training_data: pd.DataFrame, model_save_path: Optional[str] = None) -> None:
        """
        Trainiert das ML-Modell mit vorbereiteten Trainingsdaten.
        
        Args:
            training_data: DataFrame mit 'text' und 'label' Spalten
            model_save_path: Optionaler Pfad zum Speichern des Modells
        """
        # Features aus den Texten extrahieren
        features = []
        for idx, row in training_data.iterrows():
            text_features = self._extract_features(
                row['text'], 
                row.get('position', idx), 
                row.get('total_sections', len(training_data))
            )
            features.append(text_features)
        
        # Feature-DataFrame erstellen
        X = pd.DataFrame(features)
        X['text'] = training_data['text']  # Originaltext für das Modell behalten
        y = training_data['label']
        
        # Trainings- und Testdaten aufteilen
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
        
        # Pipeline mit CountVectorizer für Textfeatures und RandomForest für Klassifikation
        self.model = Pipeline([
            ('classifier', RandomForestClassifier(n_estimators=100, random_state=42))
        ])
        
        # Modell trainieren
        self.model.fit(X_train, y_train)
        
        # Modellleistung bewerten
        accuracy = self.model.score(X_test, y_test)
        logger.info(f"Modellgenauigkeit: {accuracy:.2f}")
        
        # Modell speichern, wenn ein Pfad angegeben wurde
        if model_save_path:
            os.makedirs(os.path.dirname(model_save_path), exist_ok=True)
            joblib.dump(self.model, model_save_path)
            logger.info(f"Modell unter {model_save_path} gespeichert")


def extract_recipe_from_pdf(pdf_path: str, model_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Wrapper-Funktion für die Extraktion von Rezeptdaten aus PDFs.
    
    Args:
        pdf_path: Pfad zur PDF-Datei
        model_path: Optionaler Pfad zu einem gespeicherten ML-Modell
        
    Returns:
        Dictionary mit extrahierten Daten (Titel, Zutaten, Anweisungen)
    """
    try:
        extractor = MLRecipeExtractor(model_path)
        result = extractor.extract_from_pdf(pdf_path)
        return {
            "success": True,
            "data": result
        }
    except Exception as e:
        logger.error(f"Fehler bei der Rezeptextraktion: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }