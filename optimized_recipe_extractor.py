"""
Speziell optimierter Extraktor für Rezeptinformationen mit Layout-Erkennung.
"""
import os
import re
import pdfplumber
import pandas as pd
import numpy as np
import joblib
import logging
from typing import Dict, Any, List, Optional, Tuple
import unicodedata

# Logging konfigurieren
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class OptimizedRecipeExtractor:
    """
    Speziell optimierter Extraktor für deutschsprachige Rezept-PDFs.
    """
    
    def __init__(self, model_path: Optional[str] = None):
        """
        Initialisiert den Extraktor mit einem optionalen ML-Modell.
        
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
        
        # Versuche verschiedene Extraktionsmethoden in Reihenfolge ihrer Präzision
        extraction_methods = [
            self._extract_with_columns,   # Spaltenbasierte Extraktion für zweispaltige Layouts
            self._extract_with_sections,  # Abschnittsbasierte Extraktion für einheitliche Layouts
            self._extract_with_ml,        # ML-basierte Extraktion als Fallback
            self._extract_with_rules      # Regelbasierte Extraktion als letzter Ausweg
        ]
        
        extracted_data = None
        
        for method in extraction_methods:
            try:
                result = method(pdf_path)
                if result and self._is_valid_extraction(result):
                    extracted_data = result
                    logger.info(f"Erfolgreiche Extraktion mit {method.__name__}")
                    break
            except Exception as e:
                logger.warning(f"Fehler bei Extraktion mit {method.__name__}: {str(e)}")
        
        if not extracted_data:
            # Fallback auf einfachste Methode
            extracted_data = {
                "title": os.path.basename(pdf_path).replace('.pdf', ''),
                "ingredients": "",
                "instructions": ""
            }
            logger.warning(f"Keine Extraktionsmethode erfolgreich, Fallback verwendet")
        
        # Nachbearbeitung für bessere Ergebnisse
        processed_data = self._postprocess_extraction(extracted_data)
        
        return processed_data
    
    def _is_valid_extraction(self, data: Dict[str, Any]) -> bool:
        """Prüft, ob die extrahierten Daten gültig sind."""
        return (
            data.get("title", "") and 
            data.get("ingredients", "") and 
            data.get("instructions", "")
        )
    
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
    
    def _extract_text_blocks_with_positions(self, pdf_path: str) -> List[Dict[str, Any]]:
        """
        Extrahiert Textblöcke mit ihren Positionsinformationen aus der PDF.
        Erweiterte Version, die verschiedene Blocktypen berücksichtigt.
        """
        blocks = []
        
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page_idx, page in enumerate(pdf.pages):
                    # Seitenabmessungen
                    page_width = page.width
                    page_height = page.height
                    
                    # Textzeilen extrahieren mit Position
                    for line in page.extract_text_lines(x_tolerance=3):
                        text = self._normalize_text(line['text'])
                        x0, top, x1, bottom = line['x0'], line['top'], line['x1'], line['bottom']
                        
                        # Relative Positionen (0-1)
                        rel_x0 = x0 / page_width
                        rel_x1 = x1 / page_width
                        rel_top = top / page_height
                        rel_bottom = bottom / page_height
                        rel_width = (x1 - x0) / page_width
                        
                        # Blocktyp bestimmen
                        block_type = self._determine_block_type(text, rel_x0, rel_width)
                        
                        blocks.append({
                            'text': text,
                            'page': page_idx,
                            'x0': rel_x0,
                            'x1': rel_x1,
                            'top': rel_top,
                            'bottom': rel_bottom,
                            'width': rel_width,
                            'center_x': (rel_x0 + rel_x1) / 2,
                            'type': block_type
                        })
        except Exception as e:
            logger.error(f"Fehler bei Textblock-Extraktion: {str(e)}")
            raise
        
        # Nach Position sortieren (zuerst Seite, dann vertikal)
        blocks.sort(key=lambda b: (b['page'], b['top']))
        
        return blocks
    
    def _determine_block_type(self, text: str, rel_x: float, rel_width: float) -> str:
        """Bestimmt den Typ eines Textblocks basierend auf seinem Inhalt und seiner Position."""
        text_lower = text.lower()
        
        # Überschriften erkennen
        if any(header in text_lower for header in ['zutaten', 'zubereitung', 'für', 'personen']):
            return 'header'
        
        # Zutatenerkennung
        if re.search(r'^\s*\d+\s*(?:g|kg|ml|l|el|tl|dl|cl|esslöffel|teelöffel)', text_lower):
            return 'ingredient'
        
        # Anweisungserkennung
        if re.search(r'^\s*\d+\.?\s', text_lower) or re.search(r'^(?:den|die|das|für|mit)\s', text_lower):
            return 'instruction'
        
        # Rezepttitel (oft breiter und links ausgerichtet)
        if rel_width > 0.5 and rel_x < 0.2 and len(text) < 60:
            return 'title'
        
        # Sonstige Informationen
        if any(info in text_lower for info in ['eigenschaften', 'glutenfrei', 'vegan', 'nährwert']):
            return 'info'
        
        # Fallback
        return 'other'
    
    def _extract_with_columns(self, pdf_path: str) -> Optional[Dict[str, Any]]:
        """Extraktion für zweispaltige Layouts (Zutaten links, Anweisungen rechts)."""
        try:
            blocks = self._extract_text_blocks_with_positions(pdf_path)
            
            if not blocks:
                return None
            
            # Erkenne Spaltenstruktur
            x_positions = [block['center_x'] for block in blocks]
            x_clusters = self._cluster_values(x_positions, max_gap=0.1)
            
            # Wenn wir weniger als 2 Cluster haben, ist es wahrscheinlich kein zweispaltiges Layout
            if len(x_clusters) < 2:
                return None
            
            # Bestimme Spalten (nehme die 2 häufigsten Cluster)
            column_centers = sorted([(len(cluster), sum(cluster)/len(cluster)) 
                                   for cluster in x_clusters], reverse=True)[:2]
            left_center = min(c[1] for c in column_centers)
            right_center = max(c[1] for c in column_centers)
            
            # Teile Blöcke in linke und rechte Spalte
            left_blocks = [b for b in blocks if abs(b['center_x'] - left_center) < 0.15]
            right_blocks = [b for b in blocks if abs(b['center_x'] - right_center) < 0.15]
            
            # Wenn eine Spalte deutlich weniger Inhalt hat, kein Spaltenlayout
            if len(left_blocks) < 3 or len(right_blocks) < 3:
                return None
            
            # Prüfe, ob linke Spalte Zutaten und rechte Anweisungen enthält
            left_ingredient_score = sum(1 for b in left_blocks if 'zutaten' in b['text'].lower() 
                                      or re.search(r'^\d+\s*(?:g|kg|ml|l|el|tl)', b['text'].lower()))
            right_instruction_score = sum(1 for b in right_blocks if 'zubereitung' in b['text'].lower()
                                        or re.search(r'^\d+\.\s', b['text'].lower()))
            
            # Wenn Score gering ist, spaltenbasierte Extraktion abbrechen
            if left_ingredient_score < 2 and right_instruction_score < 2:
                return None
            
            # Titel extrahieren (typischerweise erster Block)
            title = blocks[0]['text'] if blocks else "Unbekanntes Rezept"
            if len(title) > 100 or len(title) < 3:
                # Suche nach einem besseren Titelkandidaten
                for block in blocks[:5]:
                    if 3 < len(block['text']) < 60 and block['type'] == 'title':
                        title = block['text']
                        break
            
            # Text für Zutaten und Anweisungen extrahieren
            ingredients_text = "\n".join(b['text'] for b in left_blocks 
                                       if b['type'] in ['ingredient', 'header'])
            instructions_text = "\n".join(b['text'] for b in right_blocks
                                        if b['type'] in ['instruction', 'header'])
            
            return {
                "title": title,
                "ingredients": ingredients_text,
                "instructions": instructions_text
            }
        except Exception as e:
            logger.error(f"Fehler bei spaltenbasierter Extraktion: {str(e)}")
            return None
    
    def _cluster_values(self, values: List[float], max_gap: float = 0.1) -> List[List[float]]:
        """Gruppiert ähnliche Werte in Cluster."""
        if not values:
            return []
            
        # Sortiere Werte
        sorted_values = sorted(values)
        
        # Initialisiere Cluster
        clusters = [[sorted_values[0]]]
        
        # Gruppiere Werte
        for value in sorted_values[1:]:
            # Wenn Wert nahe am letzten Cluster, füge ihn diesem hinzu
            if value - clusters[-1][-1] <= max_gap:
                clusters[-1].append(value)
            # Sonst neuen Cluster starten
            else:
                clusters.append([value])
        
        return clusters
    
    def _extract_with_sections(self, pdf_path: str) -> Optional[Dict[str, Any]]:
        """Extraktion basierend auf Abschnittsüberschriften (für Standard-Layouts)."""
        try:
            blocks = self._extract_text_blocks_with_positions(pdf_path)
            
            if not blocks:
                return None
            
            # Titel extrahieren (erster Block, wenn geeignet)
            title = "Unbekanntes Rezept"
            for block in blocks[:5]:
                if 3 < len(block['text']) < 60 and block['type'] in ['title', 'other']:
                    title = block['text']
                    break
            
            # Suche nach Abschnittsüberschriften
            ingredient_section_start = -1
            instruction_section_start = -1
            
            for i, block in enumerate(blocks):
                text_lower = block['text'].lower()
                
                # Zutaten-Überschrift
                if ('zutaten' in text_lower or 'für ' in text_lower and 'personen' in text_lower) \
                        and ingredient_section_start == -1:
                    ingredient_section_start = i
                
                # Zubereitungs-Überschrift
                if ('zubereitung' in text_lower or 'anleitung' in text_lower) \
                        and instruction_section_start == -1:
                    instruction_section_start = i
            
            # Wenn keine Abschnitte gefunden wurden, die Methode abbrechen
            if ingredient_section_start == -1 and instruction_section_start == -1:
                return None
            
            # Bestimmung der Abschnittsgrenzen
            ingredient_section_end = instruction_section_start if instruction_section_start != -1 else len(blocks)
            instruction_section_end = len(blocks)
            
            # Wenn die Reihenfolge umgekehrt ist (zuerst Anweisungen, dann Zutaten)
            if instruction_section_start != -1 and ingredient_section_start != -1 \
                    and instruction_section_start < ingredient_section_start:
                ingredient_section_end = len(blocks)
                instruction_section_end = ingredient_section_start
            
            # Extrahiere Text für Zutaten
            ingredients = []
            if ingredient_section_start != -1:
                for i in range(ingredient_section_start, ingredient_section_end):
                    block = blocks[i]
                    if block['type'] not in ['title', 'info']:
                        ingredients.append(block['text'])
            
            # Extrahiere Text für Anweisungen
            instructions = []
            if instruction_section_start != -1:
                for i in range(instruction_section_start, instruction_section_end):
                    block = blocks[i]
                    if block['type'] not in ['title', 'info']:
                        instructions.append(block['text'])
            
            ingredients_text = "\n".join(ingredients)
            instructions_text = "\n".join(instructions)
            
            # Wenn wir keine ausreichenden Daten haben, die Methode abbrechen
            if not ingredients_text or not instructions_text:
                return None
            
            return {
                "title": title,
                "ingredients": ingredients_text,
                "instructions": instructions_text
            }
        except Exception as e:
            logger.error(f"Fehler bei abschnittsbasierter Extraktion: {str(e)}")
            return None
    
    def _extract_with_ml(self, pdf_path: str) -> Optional[Dict[str, Any]]:
        """ML-basierte Extraktion als Fallback-Methode."""
        if not self.model:
            return None
            
        try:
            # Text extrahieren
            text = self._extract_text_from_pdf(pdf_path)
            sections = self._split_into_sections(text)
            
            if not sections:
                return None
            
            # ML-Modell anwenden
            predictions = self.model.predict(sections)
            
            # Kategorisieren
            title_sections = [sections[i] for i, pred in enumerate(predictions) if pred == 'title']
            ingredient_sections = [sections[i] for i, pred in enumerate(predictions) if pred == 'ingredients']
            instruction_sections = [sections[i] for i, pred in enumerate(predictions) if pred == 'instructions']
            
            # Daten zusammenstellen
            title = title_sections[0] if title_sections else os.path.basename(pdf_path).replace('.pdf', '')
            ingredients_text = "\n".join(ingredient_sections)
            instructions_text = "\n".join(instruction_sections)
            
            # Wenn wir keine ausreichenden Daten haben, die Methode abbrechen
            if not ingredients_text or not instructions_text:
                return None
            
            return {
                "title": title,
                "ingredients": ingredients_text,
                "instructions": instructions_text
            }
        except Exception as e:
            logger.error(f"Fehler bei ML-basierter Extraktion: {str(e)}")
            return None
    
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
    
    def _extract_with_rules(self, pdf_path: str) -> Dict[str, Any]:
        """Regelbasierte Extraktion als letzte Rückfallmethode."""
        try:
            # Text extrahieren
            text = self._extract_text_from_pdf(pdf_path)
            sections = self._split_into_sections(text)
            
            if not sections:
                return {
                    "title": os.path.basename(pdf_path).replace('.pdf', ''),
                    "ingredients": "",
                    "instructions": ""
                }
            
            # Titel extrahieren (erster kurzer Abschnitt)
            title = "Unbekanntes Rezept"
            for section in sections[:5]:
                if 3 < len(section) < 60 and not any(marker in section.lower() for marker in ['zutaten', 'zubereitung']):
                    title = section
                    break
            
            # Regelbasierte Extraktion von Zutaten und Anweisungen
            ingredients = []
            instructions = []
            current_section = None
            
            for section in sections:
                section_lower = section.lower()
                
                # Abschnittsüberschriften erkennen
                if "zutaten" in section_lower or ("für " in section_lower and "personen" in section_lower):
                    current_section = "ingredients"
                    ingredients.append(section)
                    continue
                elif "zubereitung" in section_lower or "anleitung" in section_lower:
                    current_section = "instructions"
                    instructions.append(section)
                    continue
                
                # Zuordnung basierend auf Mustern und aktuellem Abschnitt
                if re.search(r'^\d+\s*(?:g|kg|ml|l|el|tl)\b', section_lower) or \
                   (re.search(r'\d+\s*g\b', section_lower) and not re.search(r'^\d+\.\s', section_lower)):
                    # Mengenangaben deuten auf Zutaten hin
                    ingredients.append(section)
                    current_section = "ingredients"
                elif re.search(r'^\d+\.\s', section) or \
                     any(verb in section_lower for verb in ["mischen", "rühren", "kochen", "backen"]):
                    # Nummerierte Schritte oder Kochverben deuten auf Anweisungen hin
                    instructions.append(section)
                    current_section = "instructions"
                elif current_section == "ingredients":
                    ingredients.append(section)
                elif current_section == "instructions":
                    instructions.append(section)
                elif len(section) > 50:  # Längere Abschnitte sind oft Anweisungen
                    instructions.append(section)
                elif re.search(r'\d+\s*(?:g|kg|ml|l)\b', section_lower):  # Mengenangaben deuten auf Zutaten hin
                    ingredients.append(section)
            
            # Zusammenfassen
            ingredients_text = "\n".join(ingredients)
            instructions_text = "\n".join(instructions)
            
            return {
                "title": title,
                "ingredients": ingredients_text,
                "instructions": instructions_text
            }
        except Exception as e:
            logger.error(f"Fehler bei regelbasierter Extraktion: {str(e)}")
            return {
                "title": os.path.basename(pdf_path).replace('.pdf', ''),
                "ingredients": "",
                "instructions": ""
            }
    
    def _postprocess_extraction(self, extracted_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Verbessert die extrahierten Daten durch Nachbearbeitung, speziell für deutsche Rezepte.
        """
        processed_data = extracted_data.copy()
        
        # Bereinige Titel
        if 'title' in processed_data and processed_data['title']:
            title = processed_data['title']
            # Entferne Dateinameninformationen und URLs
            title = re.sub(r'\.pdf|www\.|http|\.ch|\.com', '', title, flags=re.IGNORECASE)
            # Entferne Nummern am Anfang
            title = re.sub(r'^\d+[\s\-\.]+', '', title)
            # Andere typische nicht-Titel-Marker entfernen
            for marker in ['zutaten', 'zubereit', 'eigenschaften', 'für', 'personen']:
                if title.lower().startswith(marker):
                    title = ""
                    break
            processed_data['title'] = title.strip()
        
        # Bereinige Zutaten
        if 'ingredients' in processed_data and processed_data['ingredients']:
            ingredients_lines = []
            in_header = False
            
            for line in processed_data['ingredients'].split('\n'):
                line = line.strip()
                if not line:
                    continue
                
                # Ignoriere offensichtlich falsche Zeilen
                if any(marker in line.lower() for marker in ['www.', '.com', '.ch', 'nährwerte', 'kcal']):
                    continue
                
                # Markiere wichtige Überschriften
                if any(marker in line.lower() for marker in ['zutaten', 'für ', 'personen']):
                    ingredients_lines.append(line)
                    in_header = True
                    continue
                
                # Prüfe, ob die Zeile eine Anweisung ist, die fehlerhaft in Zutaten ist
                is_instruction = (
                    re.search(r'^\d+\.\s', line) or 
                    len(line) > 100 or  # Sehr lange Zeilen sind wahrscheinlich Anweisungen
                    (in_header and any(v in line.lower() for v in ['mischen', 'rühren', 'kochen', 'backen']))
                )
                
                if is_instruction:
                    in_header = False
                    continue
                
                # Füge die Zeile hinzu, wenn sie eine Zutat zu sein scheint
                ingredients_lines.append(line)
                in_header = False
            
            processed_data['ingredients'] = "\n".join(ingredients_lines)
        
        # Bereinige Anweisungen
        if 'instructions' in processed_data and processed_data['instructions']:
            instructions_lines = []
            
            for line in processed_data['instructions'].split('\n'):
                line = line.strip()
                if not line:
                    continue
                
                # Ignoriere offensichtlich falsche Zeilen
                if any(marker in line.lower() for marker in ['www.', '.com', '.ch', 'nährwerte', 'kcal']):
                    continue
                
                # Behalte Überschriften
                if any(marker in line.lower() for marker in ['zubereitung', 'anleitung', 'schritt']):
                    instructions_lines.append(line)
                    continue
                
                # Typische Kennzeichen für Anweisungen
                is_instruction = (
                    re.search(r'^\d+\.\s', line) or  # Nummerierter Schritt
                    len(line) > 30 or  # Längere Anweisungen
                    any(v in line.lower() for v in ['mischen', 'rühren', 'kochen', 'backen', 'geben', 'lassen'])
                )
                
                # Typische Kennzeichen für Zutaten (die fälschlicherweise in Anweisungen sind)
                is_ingredient = (
                    re.search(r'^\d+\s*(?:g|kg|ml|l)\b', line.lower()) and len(line) < 30
                )
                
                if is_instruction and not is_ingredient:
                    instructions_lines.append(line)
            
            processed_data['instructions'] = "\n".join(instructions_lines)
        
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
        extractor = OptimizedRecipeExtractor(model_path)
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