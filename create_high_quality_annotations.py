"""
Skript zum Erstellen von hochwertigen Annotationsvorlagen für das ML-Modell.
"""
import os
import pandas as pd
import argparse
import pdfplumber
import logging
import unicodedata
import re

# Logging konfigurieren
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def normalize_text(text):
    """Normalisiert Text und entfernt unerwünschte Zeichen."""
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

def is_ingredient_line(line):
    """Prüft, ob eine Zeile wahrscheinlich eine Zutat beschreibt."""
    line_lower = line.lower()
    # Typische Zutatenmuster
    has_amount = bool(re.search(r'^\s*\d+[\s,.]', line))
    has_unit = any(unit in line_lower for unit in ['g', 'kg', 'ml', 'l', 'el', 'tl', 'prise', 'stück', 'bund', 'dose'])
    has_ingredient = any(ing in line_lower for ing in ['mehl', 'zucker', 'salz', 'eier', 'butter', 'milch', 'wasser'])
    
    return has_amount and (has_unit or has_ingredient)

def is_instruction_line(line):
    """Prüft, ob eine Zeile wahrscheinlich eine Anweisung ist."""
    line_lower = line.lower()
    # Typische Anweisungsmuster
    has_step_number = bool(re.search(r'^\s*\d+\.\s', line))
    has_verb = any(verb in line_lower for verb in ['mischen', 'rühren', 'kochen', 'backen', 'braten', 'schneiden'])
    no_ingredient = not is_ingredient_line(line)
    
    return (has_step_number or has_verb) and no_ingredient

def extract_sections_from_pdf(pdf_path):
    """Extrahiert strukturierte Textabschnitte aus einer PDF-Datei."""
    title_section = ""
    ingredient_sections = []
    instruction_sections = []
    other_sections = []
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            full_text = ""
            for page in pdf.pages:
                page_text = page.extract_text(x_tolerance=3, y_tolerance=3) or ""
                # Normalisiere Text
                page_text = normalize_text(page_text)
                full_text += page_text + "\n\n"
            
            # Teile in Absätze auf
            paragraphs = [p.strip() for p in full_text.split('\n\n') if p.strip()]
            
            # Titel ist oft der erste kurze Absatz
            if paragraphs and len(paragraphs[0]) < 100:
                title_section = paragraphs[0]
                paragraphs = paragraphs[1:]
            
            # Erkenne Zutaten und Anweisungen
            in_ingredient_section = False
            in_instruction_section = False
            
            for paragraph in paragraphs:
                paragraph_lower = paragraph.lower()
                
                # Abschnittsüberschriften erkennen
                if "zutaten" in paragraph_lower and len(paragraph) < 30:
                    in_ingredient_section = True
                    in_instruction_section = False
                    continue
                elif any(x in paragraph_lower for x in ["zubereitung", "anleitung", "schritt"]) and len(paragraph) < 30:
                    in_ingredient_section = False
                    in_instruction_section = True
                    continue
                
                # Zeilen nach Typ verarbeiten
                lines = paragraph.split('\n')
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    
                    # Klassifiziere Zeile
                    if is_ingredient_line(line):
                        ingredient_sections.append(line)
                    elif is_instruction_line(line):
                        instruction_sections.append(line)
                    elif in_ingredient_section:
                        ingredient_sections.append(line)
                    elif in_instruction_section:
                        instruction_sections.append(line)
                    else:
                        other_sections.append(line)
    
    except Exception as e:
        logger.error(f"Fehler beim Extrahieren aus PDF {pdf_path}: {str(e)}")
    
    return title_section, ingredient_sections, instruction_sections, other_sections

def create_high_quality_template(pdf_dir, output_file):
    """Erstellt eine hochwertige Annotationsvorlage für bessere Modelltraining."""
    all_sections = []
    
    # PDF-Dateien im Verzeichnis finden
    pdf_files = [f for f in os.listdir(pdf_dir) if f.lower().endswith('.pdf')]
    logger.info(f"Verarbeite {len(pdf_files)} PDF-Dateien in {pdf_dir}")
    
    for filename in pdf_files:
        try:
            pdf_path = os.path.join(pdf_dir, filename)
            logger.info(f"Verarbeite {filename}")
            
            # Extrahiere strukturierte Abschnitte
            title, ingredients, instructions, others = extract_sections_from_pdf(pdf_path)
            
            # Titel hinzufügen
            if title:
                all_sections.append({
                    "filename": filename,
                    "position": 0,
                    "text": title,
                    "suggested_label": "title"
                })
            
            # Zutaten hinzufügen
            for idx, ingredient in enumerate(ingredients):
                all_sections.append({
                    "filename": filename,
                    "position": idx + 1,
                    "text": ingredient,
                    "suggested_label": "ingredients"
                })
            
            # Anweisungen hinzufügen
            for idx, instruction in enumerate(instructions):
                all_sections.append({
                    "filename": filename,
                    "position": idx + 1 + len(ingredients),
                    "text": instruction,
                    "suggested_label": "instructions"
                })
            
            # Andere Abschnitte hinzufügen
            for idx, other in enumerate(others):
                all_sections.append({
                    "filename": filename,
                    "position": idx + 1 + len(ingredients) + len(instructions),
                    "text": other,
                    "suggested_label": ""
                })
            
            logger.info(f"  - Extrahiert: {len(ingredients)} Zutaten, {len(instructions)} Anweisungen")
        except Exception as e:
            logger.error(f"Fehler bei {filename}: {str(e)}")
    
    # DataFrame erstellen
    df = pd.DataFrame(all_sections)
    
    # Ausgabeverzeichnis erstellen, falls es nicht existiert
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    # Spalte für die finalen Annotationen hinzufügen
    df['label'] = df['suggested_label']
    
    # CSV-Datei speichern
    df.to_csv(output_file, index=False, encoding='utf-8')
    logger.info(f"{len(df)} Abschnitte aus {len(pdf_files)} PDFs exportiert nach {output_file}")
    logger.info(f"Label-Verteilung: {df['suggested_label'].value_counts().to_dict()}")

def main():
    parser = argparse.ArgumentParser(description='Erstelle qualitativ hochwertige Annotationsvorlage')
    parser.add_argument('pdf_dir', help='Verzeichnis mit PDF-Dateien')
    parser.add_argument('--output', '-o', default='data/high_quality_annotations.csv',
                        help='Pfad zur CSV-Ausgabedatei')
    args = parser.parse_args()
    
    # Prüfen, ob das Verzeichnis existiert
    if not os.path.isdir(args.pdf_dir):
        logger.error(f"Verzeichnis nicht gefunden: {args.pdf_dir}")
        return
    
    # Hochwertige Annotationsvorlage erstellen
    create_high_quality_template(args.pdf_dir, args.output)

if __name__ == "__main__":
    main()