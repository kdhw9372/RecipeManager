"""
Service zur KI-gestützten Extraktion von Rezeptinformationen aus PDF-Dateien.
"""
import re
import os
import pdfplumber
from typing import Dict, Any, List, Tuple
import logging
import nltk
from nltk.tokenize import sent_tokenize
import spacy
from spacy.language import Language
from spacy.tokens import Doc

# Logging konfigurieren
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# NLTK-Daten herunterladen (wenn nötig)
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt')

# Spacy-Modell laden
try:
    nlp = spacy.load("de_core_news_sm")
except OSError:
    # Falls das Modell nicht installiert ist, einen Hinweis anzeigen
    logger.error("Spacy-Modell 'de_core_news_sm' nicht gefunden.")
    logger.info("Bitte installieren Sie es mit 'python -m spacy download de_core_news_sm'")
    raise

class RecipeExtractor:
    """
    Klasse zur KI-gestützten Extraktion von Rezeptinformationen aus PDFs.
    Verwendet Spacy für NER und Textklassifikation.
    """
    
    # Typische Einheitenwörter in Rezepten
    UNITS = [
        'g', 'kg', 'ml', 'l', 'el', 'tl', 'prise', 'prisen', 'stück', 'stk',
        'bund', 'zehe', 'zehen', 'scheibe', 'scheiben', 'tasse', 'tassen',
        'dose', 'dosen', 'packung', 'päckchen', 'gramm', 'liter', 'milliliter',
        'esslöffel', 'teelöffel'
    ]
    
    # Muster für Zutatenangaben (z.B. "200 g Mehl")
    INGREDIENT_PATTERN = re.compile(
        r'(\d+(?:[.,]\d+)?(?:\s*-\s*\d+(?:[.,]\d+)?)?)\s*'  # Menge (z.B. 200 oder 200-300)
        r'(?:' + '|'.join(UNITS) + r')?\s*'                # optionale Einheit
        r'([a-zäöüß].+)'                                  # Zutat selbst
    )
    
    # Muster, die auf Anweisungen hindeuten
    INSTRUCTION_INDICATORS = [
        'schritt', 'zubereitung', 'anleitung', 'vorbereitung',
        'kochen', 'backen', 'braten', 'dünsten', 'garen',
        'mischen', 'rühren', 'schneiden', 'hinzufügen',
        'erhitzen', 'abkühlen', 'ruhen', 'ziehen'
    ]
    
    # Typische Titel-Marker
    TITLE_INDICATORS = ['rezept für', 'rezept:', 'rezept', 'zutaten für']
    
    def __init__(self):
        """Initialisiert den RecipeExtractor mit angepassten Spacy-Komponenten."""
        # Komponente für Zutaten-Erkennung registrieren
        if not Language.has_factory("ingredients_component"):
            @Language.factory("ingredients_component")
            def create_ingredients_component(nlp, name):
                return IngredientsComponent(nlp)
            
        # Komponente für Anweisungs-Erkennung registrieren
        if not Language.has_factory("instructions_component"):
            @Language.factory("instructions_component")
            def create_instructions_component(nlp, name):
                return InstructionsComponent(nlp)
        
        # Komponenten zur Pipeline hinzufügen
        if "ingredients_component" not in nlp.pipe_names:
            nlp.add_pipe("ingredients_component")
        if "instructions_component" not in nlp.pipe_names:
            nlp.add_pipe("instructions_component")
    
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
        
        # Daten mit NLP extrahieren
        title = self._extract_title(sections)
        ingredients = self._extract_ingredients(sections)
        instructions = self._extract_instructions(sections)
        
        return {
            "title": title,
            "ingredients": ingredients,
            "instructions": instructions
        }
    
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
        
        # Dann Absätze in Sätze aufteilen und alles zusammenführen
        sections = []
        for paragraph in paragraphs:
            # Leerzeilen und sehr kurze Paragraphen als eigene Abschnitte betrachten
            if len(paragraph) < 15:
                if paragraph.strip():
                    sections.append(paragraph)
                continue
                
            sentences = sent_tokenize(paragraph)
            sections.extend(sentences)
        
        return sections
    
    def _extract_title(self, sections: List[str]) -> str:
        """Identifiziert den Titel des Rezepts in den Textabschnitten."""
        # Strategie 1: Ersten substanziellen Abschnitt als Titel betrachten, wenn er kurz ist
        for section in sections:
            if 3 < len(section) < 60 and not any(char.isdigit() for char in section):
                # Prüfen, ob es sich um einen Titel handeln könnte
                section_lower = section.lower()
                if not any(indicator in section_lower for indicator in self.INSTRUCTION_INDICATORS):
                    return section.strip()
        
        # Strategie 2: Nach typischen Titelindikatoren suchen
        for section in sections:
            section_lower = section.lower()
            for indicator in self.TITLE_INDICATORS:
                if indicator in section_lower:
                    # Extrahieren des Texts nach dem Indikator
                    title_part = section_lower.split(indicator, 1)[1].strip()
                    if title_part:
                        return section.strip()
        
        # Strategie 3: Spacy-basierte Entitätserkennung für Gerichte
        for section in sections[:5]:  # Nur in den ersten 5 Abschnitten suchen
            doc = nlp(section)
            for ent in doc.ents:
                if ent.label_ == "FOOD" or ent.label_ == "PRODUCT":
                    title_candidate = section.strip()
                    if 3 < len(title_candidate) < 60:
                        return title_candidate
        
        # Fallback: Ersten substanziellen Abschnitt zurückgeben
        for section in sections:
            if len(section) > 3:
                return section.strip()
        
        return "Unbekanntes Rezept"
    
    def _extract_ingredients(self, sections: List[str]) -> str:
        """
        Extrahiert Zutaten aus den Textabschnitten mithilfe von NLP und Mustern.
        """
        potential_ingredients = []
        ingredient_sections = []
        
        # Abschnitte identifizieren, die Zutaten enthalten könnten
        for idx, section in enumerate(sections):
            if self._is_likely_ingredient_section(section):
                ingredient_sections.append(section)
                
                # Auch die nächsten Abschnitte hinzufügen, wenn sie Zutaten enthalten könnten
                for next_idx in range(idx + 1, min(idx + 10, len(sections))):
                    next_section = sections[next_idx]
                    if self._is_likely_ingredient_section(next_section):
                        ingredient_sections.append(next_section)
                    elif self._is_likely_instruction_section(next_section):
                        break
                
                break
        
        # Wenn keine spezifischen Zutatenabschnitte gefunden wurden, alle Abschnitte prüfen
        if not ingredient_sections:
            ingredient_sections = sections
        
        # Texte mit Spacy analysieren
        for section in ingredient_sections:
            doc = nlp(section)
            
            # Annotationen der benutzerdefinierten Komponente nutzen
            if doc.has_extension("is_ingredient") and doc._.is_ingredient:
                potential_ingredients.append(section)
            # Auch regulären Ausdruck für Zutaten prüfen
            elif self._contains_ingredient_pattern(section):
                potential_ingredients.append(section)
        
        # Zutaten formatieren
        formatted_ingredients = "\n".join(potential_ingredients)
        
        return formatted_ingredients
    
    def _extract_instructions(self, sections: List[str]) -> str:
        """
        Extrahiert Zubereitungsanweisungen aus den Textabschnitten mithilfe von NLP.
        """
        instructions = []
        in_instructions_section = False
        
        # Erste Strategie: Nach Überschriften suchen, die auf Anweisungen hindeuten
        for idx, section in enumerate(sections):
            section_lower = section.lower()
            
            # Prüfen, ob der Abschnitt eine Überschrift für Anweisungen ist
            if any(indicator in section_lower for indicator in ["zubereitung", "anleitung", "schritt"]):
                in_instructions_section = True
                continue
            
            # Nachfolgende Abschnitte als Anweisungen sammeln, bis ein neuer Hauptabschnitt beginnt
            if in_instructions_section:
                # Prüfen, ob ein neuer Hauptabschnitt beginnt
                if section_lower.strip() and len(section_lower) < 20 and section_lower.endswith(':'):
                    in_instructions_section = False
                    continue
                
                if section.strip():
                    instructions.append(section)
        
        # Zweite Strategie: NLP-basierte Erkennung von Anweisungen
        if not instructions:
            for section in sections:
                doc = nlp(section)
                if doc.has_extension("is_instruction") and doc._.is_instruction:
                    instructions.append(section)
        
        # Dritte Strategie: Nach typischen Satzanfängen für Anweisungen suchen
        if not instructions:
            for section in sections:
                if self._is_likely_instruction_section(section) and not self._is_likely_ingredient_section(section):
                    instructions.append(section)
        
        # Anweisungen formatieren
        formatted_instructions = "\n".join(instructions)
        
        return formatted_instructions
    
    def _is_likely_ingredient_section(self, text: str) -> bool:
        """Prüft, ob ein Textabschnitt wahrscheinlich Zutaten enthält."""
        text_lower = text.lower()
        
        # Nach typischen Überschriften für Zutaten suchen
        if "zutaten" in text_lower and len(text_lower) < 30:
            return True
        
        # Nach Mustern für Zutatenangaben suchen
        if self._contains_ingredient_pattern(text):
            return True
        
        return False
    
    def _is_likely_instruction_section(self, text: str) -> bool:
        """Prüft, ob ein Textabschnitt wahrscheinlich Anweisungen enthält."""
        text_lower = text.lower()
        
        # Nach typischen Überschriften für Anweisungen suchen
        for indicator in ["zubereitung", "anleitung", "schritt"]:
            if indicator in text_lower and len(text_lower) < 30:
                return True
        
        # Nach typischen Verben in Anweisungen suchen
        for verb in ["mischen", "rühren", "hinzufügen", "erhitzen", "schneiden", "kochen", "backen"]:
            if verb in text_lower:
                return True
        
        # Nach Schritten wie "1.", "2." suchen
        if re.search(r'^\s*\d+\.\s', text):
            return True
        
        return False
    
    def _contains_ingredient_pattern(self, text: str) -> bool:
        """Prüft, ob der Text ein typisches Zutatenmuster enthält."""
        return bool(self.INGREDIENT_PATTERN.search(text))


class IngredientsComponent:
    """Spacy-Komponente zur Erkennung von Zutaten."""
    
    def __init__(self, nlp):
        """Initialisiert die Komponente."""
        Doc.set_extension("is_ingredient", default=False, force=True)
        self.nlp = nlp
    
    def __call__(self, doc):
        """Analysiert den Dokument-Text und annotiert Zutaten."""
        text = doc.text.lower()
        
        # Einfache Heuristik: Prüfen, ob der Text ein typisches Zutatenmuster enthält
        contains_amount = bool(re.search(r'\d+\s*(?:g|kg|ml|l|el|tl)', text))
        contains_food_related = any(word in text for word in [
            "mehl", "zucker", "salz", "pfeffer", "öl", "butter", "ei", "eier", "milch",
            "wasser", "sahne", "käse", "schokolade", "vanille", "zimt", "backpulver"
        ])
        
        # Kombinierte Entscheidung
        doc._.is_ingredient = contains_amount or contains_food_related
        
        return doc


class InstructionsComponent:
    """Spacy-Komponente zur Erkennung von Anweisungen."""
    
    def __init__(self, nlp):
        """Initialisiert die Komponente."""
        Doc.set_extension("is_instruction", default=False, force=True)
        self.nlp = nlp
        
        # Typische Verben in Kochanweisungen
        self.cooking_verbs = [
            "mischen", "rühren", "schneiden", "hacken", "kochen", "braten", "backen",
            "gießen", "hinzufügen", "erhitzen", "abkühlen", "garnieren", "servieren",
            "pürieren", "stampfen", "vermengen", "schlagen", "kneten", "formen"
        ]
    
    def __call__(self, doc):
        """Analysiert den Dokument-Text und annotiert Anweisungen."""
        text = doc.text.lower()
        
        # Schrittweise Anweisungen erkennen
        is_step = bool(re.search(r'^\s*\d+\.\s', text))
        
        # Nach Imperativ-Formen suchen (typisch für Anweisungen)
        contains_imperative = False
        for token in doc:
            if token.pos_ == "VERB" and token.is_sent_start:
                contains_imperative = True
                break
        
        # Nach typischen Kochverben suchen
        contains_cooking_verb = any(verb in text for verb in self.cooking_verbs)
        
        # Kombinierte Entscheidung
        doc._.is_instruction = is_step or contains_imperative or contains_cooking_verb
        
        return doc


# Instanz des Extractors erstellen (kann global verwendet werden)
recipe_extractor = RecipeExtractor()


def extract_recipe_from_pdf(pdf_path: str) -> Dict[str, Any]:
    """
    Wrapper-Funktion für die Extraktion von Rezeptdaten aus PDFs.
    
    Args:
        pdf_path: Pfad zur PDF-Datei
        
    Returns:
        Dictionary mit extrahierten Daten (Titel, Zutaten, Anweisungen)
    """
    try:
        result = recipe_extractor.extract_from_pdf(pdf_path)
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