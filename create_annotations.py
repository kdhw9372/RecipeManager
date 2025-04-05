"""
Hilfsskript zur Erstellung von Annotationsdateien für das ML-Modell.
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
    # Normalisiere Unicode-Zeichen
    if not isinstance(text, str):
        return ""
        
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
        '\xa0': ' '  # Nicht brechende Leerzeichen
    }
    for old, new in replacements.items():
        normalized = normalized.replace(old, new)
    return normalized

def extract_sections_from_pdf(pdf_path: str) -> list:
    """Extrahiert Textabschnitte aus einer PDF-Datei mit korrekter Kodierung."""
    sections = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages):
                page_text = page.extract_text(x_tolerance=3, y_tolerance=3) or ""
                
                # Normalisiere Text
                page_text = normalize_text(page_text)
                
                # Teile in Absätze
                paragraphs = [p.strip() for p in page_text.split('\n\n') if p.strip()]
                
                # Füge Absätze zu Abschnitten hinzu
                for paragraph in paragraphs:
                    # Sehr kurze Absätze überspringen
                    if len(paragraph) < 3:
                        continue
                    
                    # Längere Absätze aufteilen, falls sie mehrere Zeilen enthalten
                    lines = paragraph.split('\n')
                    if len(lines) > 1:
                        # Suche nach Zutatenlisten (oft eingerückt oder mit Mengenangaben)
                        if any(re.search(r'^\s*\d+\s*(?:g|kg|ml|l|EL|TL|Stück)', line, re.IGNORECASE) for line in lines):
                            # Es handelt sich wahrscheinlich um eine Zutatenliste - als ganzen Block behalten
                            sections.append(paragraph)
                        else:
                            # Für lange Linien einzeln hinzufügen
                            for line in lines:
                                if len(line) > 10:  # Nur substantielle Zeilen
                                    sections.append(line.strip())
                    else:
                        sections.append(paragraph)
                
                # Seitenzahlen als Kontext hinzufügen (optional)
                logger.debug(f"Seite {page_num+1}/{len(pdf.pages)}: {len(sections)} Abschnitte extrahiert")
                
    except Exception as e:
        logger.error(f"Fehler beim Extrahieren des Textes aus der PDF {pdf_path}: {e}")
    
    # Entferne Duplikate und sehr kurze Abschnitte
    cleaned_sections = []
    seen = set()
    for section in sections:
        section = section.strip()
        # Prüfe auf Duplikate und Mindestlänge
        if section and len(section) >= 5 and section not in seen:
            cleaned_sections.append(section)
            seen.add(section)
    
    return cleaned_sections

def create_annotation_template(pdf_dir: str, output_file: str):
    """
    Erstellt eine Vorlage für Annotationen aus PDFs in einem Verzeichnis.
    
    Args:
        pdf_dir: Verzeichnis mit PDF-Dateien
        output_file: Pfad zur Ausgabedatei (CSV)
    """
    all_sections = []
    file_names = []
    positions = []
    
    # PDFs durchlaufen und Abschnitte extrahieren
    pdf_files = [f for f in os.listdir(pdf_dir) if f.lower().endswith('.pdf')]
    logger.info(f"Verarbeite {len(pdf_files)} PDF-Dateien in {pdf_dir}")
    
    for filename in pdf_files:
        try:
            pdf_path = os.path.join(pdf_dir, filename)
            logger.info(f"Verarbeite {filename}")
            
            sections = extract_sections_from_pdf(pdf_path)
            
            for i, section in enumerate(sections):
                all_sections.append(section)
                file_names.append(filename)
                positions.append(i)
                
            logger.info(f"  - {len(sections)} Abschnitte extrahiert")
        except Exception as e:
            logger.error(f"Fehler bei {filename}: {str(e)}")
    
    # DataFrame erstellen
    df = pd.DataFrame({
        'filename': file_names,
        'position': positions,
        'text': all_sections,
        'label': ''  # Leere Spalte für manuelle Annotationen
    })
    
    # Entferne Zeilen mit leeren Texten
    df = df[df['text'].str.strip().astype(bool)]
    
    # CSV-Datei speichern (mit expliziter UTF-8-Kodierung)
    df.to_csv(output_file, index=False, encoding='utf-8')
    logger.info(f"{len(df)} Abschnitte aus {len(set(file_names))} PDFs exportiert nach {output_file}")

def main():
    parser = argparse.ArgumentParser(description='Erstelle Annotationsvorlage aus PDF-Verzeichnis')
    parser.add_argument('pdf_dir', help='Verzeichnis mit PDF-Dateien')
    parser.add_argument('--output', '-o', default='data/annotations_template.csv',
                        help='Pfad zur CSV-Ausgabedatei')
    args = parser.parse_args()
    
    # Prüfen, ob das Verzeichnis existiert
    if not os.path.isdir(args.pdf_dir):
        logger.error(f"Verzeichnis nicht gefunden: {args.pdf_dir}")
        return
    
    # Ausgabeverzeichnis erstellen, falls es nicht existiert
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    
    # Annotationsvorlage erstellen
    create_annotation_template(args.pdf_dir, args.output)

if __name__ == "__main__":
    main()