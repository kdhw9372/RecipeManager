"""
Verbesserte Klasse zur ML-gestützten Extraktion von Rezeptinformationen aus PDFs.
"""
import os
import re
import pdfplumber
import pandas as pd
import numpy as np
import joblib
import logging
from typing import Dict, Any, List, Optional
import unicodedata

# Logging konfigurieren
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ImprovedRecipeExtractor:
    """
    Verbesserte Klasse zur ML-gestützten Extraktion von Rezeptinformationen aus PDFs.
    Nutzt ein trainiertes Modell und Post-Processing für bessere Ergebnisse.
    """
    
    def __init__(self, model_path: Optional[str] = None):
        """
        Initialisiert den RecipeExtractor mit einem trainierten Modell.
        
        Args:
            model_path: Pfad zum gespeicherten Modell
        """
        self.model = None
        if model_path and os.path.exists(model_path):
            try:
                self.model = joblib.load(model_path)
                logger.info(f"Modell aus {model_path} geladen")
            except Exception as e:
                logger.error(f"Konnte Modell nicht laden: {str(e)}")
    
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
        
        # Sonst ML-basierte Extraktion und Nachbearbeitung
        extracted_data = self._extract_ml_based(sections)
        processed_data = self._postprocess_extraction(extracted_data)
        
        return processed_data
    
    def _normalize_text(self, text: str) -> str:
        """Normalisiert Text für konsistente Verarbeitung."""
        if not isinstance(text, str):
            return ""
            
        # Normalisiere Unicode-Zeichen
        normalized = unicodedata.normalize('NFKD', text)
        # Ersetze problematische Zeichen
        replacements = {
            '«': '"',
            '»': '"',
            ''': "'",
            ''': "'",
            '"': '"',
            '"': '"',
            '–': '-',
            '—': '-',
            '\xa0': ' ',  # Nicht brechende Leerzeichen
            '\u200b': ''  # Zero-width space
        }
        for old, new in replacements.items():
            normalized = normalized.replace(old, new)
        return normalized
    
    def _extract_text_from_pdf(self, pdf_path: str) -> str:
        """Extrahiert den Text aus allen Seiten einer PDF-Datei."""
        full_text = ""
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text(x_tolerance=3, y_tolerance=3) or ""
                    page_text = self._normalize_text(page_text)
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
            
            # Absätze mit Zeilenumbrüchen aufteilen
            if '\n' in paragraph:
                lines = paragraph.split('\n')
                # Prüfen, ob es eine formatierte Liste ist
                if any(re.match(r'^\s*\d+[\.,]?\s', line) for line in lines) or \
                   any(re.match(r'^\s*[\-\*•]\s', line) for line in lines):
                    # Als Ganzes behalten, wahrscheinlich eine Liste
                    sections.append(paragraph)
                else:
                    # Jede Zeile einzeln hinzufügen
                    sections.extend(line.strip() for line in lines if line.strip())
            else:
                # Ganze Absätze hinzufügen
                sections.append(paragraph)
        
        return sections
    
    def _extract_ml_based(self, sections: List[str]) -> Dict[str, Any]:
        """
        Extrahiert Rezeptinformationen basierend auf ML-Klassifikation.
        
        Args:
            sections: Liste von Textabschnitten
            
        Returns:
            Dictionary mit extrahierten Daten
        """
        if not sections:
            return {"title": "Unbekanntes Rezept", "ingredients": "", "instructions": ""}
        
        # Vorhersagen mit dem Modell machen
        predictions = self.model.predict(sections)
        
        # Ergebnisse nach Kategorie gruppieren
        title_sections = [sections[i] for i, pred in enumerate(predictions) if pred == 'title']
        ingredient_sections = [sections[i] for i, pred in enumerate(predictions) if pred == 'ingredients']
        instruction_sections = [sections[i] for i, pred in enumerate(predictions) if pred == 'instructions']
        
        # Besten Titel auswählen (erster oder längster Titel)
        title = ""
        if title_sections:
            # Bevorzuge kurze Titel am Anfang des Dokuments
            title_candidates = [(i, s) for i, s in enumerate(title_sections) if len(s) < 100]
            if title_candidates:
                title = min(title_candidates, key=lambda x: x[0])[1]
            else:
                title = title_sections[0]
        else:
            # Fallback: Verwende den Dateinamen oder ersten Abschnitt
            title = "Unbekanntes Rezept"
        
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
            if 3 < len(section) < 100 and not any(char.isdigit() for char in section):
                title = section
                break
        
        # Zutaten und Anweisungen identifizieren
        ingredients = []
        instructions = []
        
        # Aktuellen Zustand verfolgen
        in_ingredient_section = False
        in_instruction_section = False
        
        for section in sections:
            section_lower = section.lower()
            
            # Abschnittsüberschriften erkennen
            if "zutaten" in section_lower and len(section) < 30:
                in_ingredient_section = True
                in_instruction_section = False
                ingredients.append(section)
                continue
            elif any(x in section_lower for x in ["zubereitung", "anleitung"]) and len(section) < 30:
                in_ingredient_section = False
                in_instruction_section = True
                instructions.append(section)
                continue
            
            # Erkennung basierend auf Mustern
            if re.search(r'^\d+\s*(?:g|kg|ml|l|el|tl)\b', section_lower) or \
               (re.search(r'\d+\s*g\b', section_lower) and not re.search(r'^\d+\.\s', section_lower)):
                ingredients.append(section)
                in_ingredient_section = True
                in_instruction_section = False
            elif re.search(r'^\d+\.\s', section) or \
                 any(verb in section_lower for verb in ["mischen", "rühren", "kochen", "backen"]):
                instructions.append(section)
                in_ingredient_section = False
                in_instruction_section = True
            elif in_ingredient_section:
                ingredients.append(section)
            elif in_instruction_section:
                instructions.append(section)
        
        return {
            "title": title,
            "ingredients": "\n".join(ingredients),
            "instructions": "\n".join(instructions)
        }
    
    def _postprocess_extraction(self, extracted_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Verbessert die extrahierten Daten durch Nachbearbeitung.
        
        Args:
            extracted_data: Ursprünglich extrahierte Daten
            
        Returns:
            Verbesserte Daten
        """
        processed_data = extracted_data.copy()
        
        # Bereinige Titel: Entferne Nummern, URLs, etc.
        if 'title' in processed_data and processed_data['title']:
            title = processed_data['title']
            # Entferne Dateinameninformationen und URLs
            title = re.sub(r'\.pdf|www\.|http|\.ch|\.com', '', title, flags=re.IGNORECASE)
            # Entferne Nummern am Anfang
            title = re.sub(r'^\d+[\s\-\.]+', '', title)
            processed_data['title'] = title.strip()
        
        # Bereinige Zutaten: Entferne nicht-Zutatentexte
            if 'ingredients' in processed_data and processed_data['ingredients']:
                ingredient_lines = []
                for line in processed_data['ingredients'].split('\n'):
                    line = line.strip()
                    # Überspringe leere Zeilen und offensichtliche nicht-Zutaten
                    if not line or any(x in line.lower() for x in ['www.', '.com', '.ch', 'gut zu wissen']):
                        continue
                    # Behalte Überschriften und Zutaten
                    if line.lower().startswith('zutaten') or \
                       re.search(r'^\d+\s*(?:g|kg|ml|l|el|tl|stück|bund)', line.lower()) or \
                       re.search(r'für\s+\d+\s+personen', line.lower()):
                        ingredient_lines.append(line)
                    # Auch Zutatenzeilen ohne Mengenangaben behalten
                    elif any(ing in line.lower() for ing in ['mehl', 'zucker', 'salz', 'eier', 'butter', 'milch']):
                        ingredient_lines.append(line)
                    # Oder wenn die vorherige Zeile eine Zutat war und diese Zeile eine Fortsetzung sein könnte
                    elif ingredient_lines and not re.search(r'^\d+\.\s', line):
                        ingredient_lines.append(line)
                
                processed_data['ingredients'] = '\n'.join(ingredient_lines)
            
            # Bereinige Anweisungen: Entferne nicht-Anweisungstexte
            if 'instructions' in processed_data and processed_data['instructions']:
                instruction_lines = []
                for line in processed_data['instructions'].split('\n'):
                    line = line.strip()
                    # Überspringe leere Zeilen und offensichtliche nicht-Anweisungen
                    if not line or any(x in line.lower() for x in ['www.', '.com', '.ch', 'zutaten']):
                        continue
                    
                    # Behalte Überschriften und Anweisungen
                    if any(x in line.lower() for x in ['zubereitung', 'anleitung', 'schritt']) or \
                       re.search(r'^\d+\.\s', line) or \
                       any(verb in line.lower() for verb in ['mischen', 'rühren', 'kochen', 'backen']):
                        instruction_lines.append(line)
                    # Auch Sätze mit Verben als potentielle Anweisungen behalten
                    elif '.' in line and len(line) > 15:
                        instruction_lines.append(line)
                
                processed_data['instructions'] = '\n'.join(instruction_lines)
        
        return processed_data


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
        extractor = ImprovedRecipeExtractor(model_path)
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