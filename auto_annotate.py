"""
Skript zur automatischen Annotation von Rezeptabschnitten.
"""
import pandas as pd
import re
import argparse
import os
import logging

# Logging konfigurieren
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def auto_label_sections(input_file, output_file):
    """
    Liest die CSV-Datei ein und fügt automatisch Labels hinzu.
    
    Args:
        input_file: Pfad zur Eingabe-CSV
        output_file: Pfad zur Ausgabe-CSV
    """
    try:
        # CSV mit expliziter Kodierung lesen
        df = pd.read_csv(input_file, encoding='utf-8')
        logger.info(f"CSV geladen mit {len(df)} Zeilen")
        
        # Rezepte nach Dateiname gruppieren
        recipe_groups = df.groupby('filename')
        
        # Für jedes Rezept Labels vorschlagen
        all_labeled_sections = []
        
        for recipe_name, sections in recipe_groups:
            # Sortiere nach Position
            sections = sections.sort_values('position')
            
            # Konvertiere DataFrame zu Liste von Dictionaries
            section_list = sections.to_dict('records')
            
            # Automatisches Labeling
            labeled_sections = auto_label_recipe(section_list)
            all_labeled_sections.extend(labeled_sections)
        
        # Neues DataFrame erstellen
        result_df = pd.DataFrame(all_labeled_sections)
        
        # CSV speichern
        result_df.to_csv(output_file, encoding='utf-8', index=False)
        logger.info(f"Ergebnisse in {output_file} gespeichert")
        
    except Exception as e:
        logger.error(f"Fehler beim Verarbeiten der CSV: {str(e)}")
        raise

def auto_label_recipe(sections):
    """
    Fügt automatisch Labels für Abschnitte eines Rezepts hinzu.
    
    Args:
        sections: Liste von Dictionaries mit 'filename', 'position', 'text'
        
    Returns:
        Liste von Dictionaries mit hinzugefügtem 'label'
    """
    # Titel wahrscheinlich am Anfang
    if sections:
        sections[0]['label'] = 'title'
    
    # Regeln zur Erkennung
    title_patterns = [
        r'^[A-Z\u00C0-\u00DC][^.!?]*$',  # Großbuchstabe am Anfang, kein Satzzeichen am Ende
        r'rezept', r'salat', r'auflauf', r'kuchen', r'torte', r'gebäck', r'suppe', 
        r'eintopf', r'braten', r'sauce', r'dressing'
    ]
    
    ingredient_patterns = [
        r'zutaten', r'für \d+ personen', 
        r'^\d+\s*(?:g|kg|ml|l|el|tl|prise|prisen|stück|bund)',
        r'^\d+\s*[A-Za-zäöüÄÖÜß]+\s+(?:g|kg|ml|l|el|tl)'
    ]
    
    instruction_patterns = [
        r'zubereitung', r'schritt', r'anleitung', r'hinweis', r'tipp',
        r'^\d+\.\s', r'mischen', r'rühren', r'schneiden', r'kochen', r'backen',
        r'garen', r'braten', r'servieren', r'vorbereiten'
    ]
    
    # Zustand verfolgen
    current_section = None
    
    # Über alle Abschnitte iterieren
    for i in range(1, len(sections)):
        section = sections[i]
        text = section['text'].lower()
        
        # Bereichsmarkierungen erkennen
        if any(re.search(pattern, text, re.IGNORECASE) for pattern in ['zutaten']):
            current_section = 'ingredients'
        elif any(re.search(pattern, text, re.IGNORECASE) for pattern in ['zubereitung', 'anleitung']):
            current_section = 'instructions'
        
        # Titel erkennen
        if (i < 3 and  # In den ersten Zeilen
            any(re.search(pattern, text, re.IGNORECASE) for pattern in title_patterns)):
            section['label'] = 'title'
        
        # Zutaten erkennen
        elif (current_section == 'ingredients' or 
              any(re.search(pattern, text, re.IGNORECASE) for pattern in ingredient_patterns)):
            section['label'] = 'ingredients'
        
        # Anweisungen erkennen
        elif (current_section == 'instructions' or 
              any(re.search(pattern, text, re.IGNORECASE) for pattern in instruction_patterns)):
            section['label'] = 'instructions'
        
        # Standardwert, wenn nichts zutrifft
        else:
            section['label'] = ''
    
    return sections
            
def main():
    parser = argparse.ArgumentParser(description='Automatisches Labelling von Rezeptabschnitten')
    parser.add_argument('input', help='Pfad zur Eingabe-CSV')
    parser.add_argument('--output', '-o', default='data/annotations_auto.csv',
                        help='Pfad zur Ausgabe-CSV')
    args = parser.parse_args()
    
    # Prüfen, ob die Eingabedatei existiert
    if not os.path.exists(args.input):
        logger.error(f"Eingabedatei nicht gefunden: {args.input}")
        return
    
    # Ausgabeverzeichnis erstellen, falls es nicht existiert
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    
    # Automatische Annotation durchführen
    auto_label_sections(args.input, args.output)

if __name__ == "__main__":
    main()