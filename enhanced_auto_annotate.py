"""
Erweitertes Skript zur präzisen automatischen Annotation von Rezeptabschnitten.
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
        
        # Statistik ausgeben
        labels_count = result_df['label'].value_counts()
        logger.info(f"Label-Verteilung: {labels_count.to_dict()}")
        
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
    # Titel erkennen - meist in den ersten Zeilen
    if sections:
        first_text = sections[0]['text'].lower()
        # Wenn die erste Zeile kurz ist und keine Zahl enthält, ist es wahrscheinlich ein Titel
        if len(sections[0]['text']) < 80 and not re.search(r'\d+\s*(?:g|kg|ml|l|el|tl)', first_text):
            sections[0]['label'] = 'title'
    
    # Zubereitungsmarkierungen, Überschriften und irrelevante Inhalte identifizieren
    ignore_patterns = [
        r'eigenschaften', r'glutenfrei', r'vegan', r'vegetarisch', r'purinarm',
        r'nährwerte', r'zeitaufwand', r'koch-/backzeit', r'vorbereitungszeit',
        r'pro portion', r'kcal', r'kohlenhydrate', r'eiweiß', r'fett', r'www\.', r'min\b'
    ]
    
    ingredient_headers = [r'zutaten', r'für \d+ personen']
    instruction_headers = [r'zubereitung', r'schritt', r'anleitung']
    
    # Zustand verfolgen
    current_section = None
    in_ingredient_section = False
    in_instruction_section = False
    
    # Über alle Abschnitte iterieren
    for i, section in enumerate(sections):
        text = section['text'].lower()
        
        # Ignoriere Header/Footer/Metadaten
        if any(re.search(pattern, text, re.IGNORECASE) for pattern in ignore_patterns):
            section['label'] = ''
            continue
            
        # Abschnittsmarkierungen erkennen
        if any(re.search(pattern, text, re.IGNORECASE) for pattern in ingredient_headers):
            current_section = 'ingredients'
            in_ingredient_section = True
            in_instruction_section = False
            
        elif any(re.search(pattern, text, re.IGNORECASE) for pattern in instruction_headers):
            current_section = 'instructions'
            in_ingredient_section = False
            in_instruction_section = True
        
        # Titel in der PDF-Datei (meist der Dateiname oder erste Zeile)
        if i == 0 or (i == 1 and 'title' not in [s.get('label', '') for s in sections]):
            section['label'] = 'title'
            
        # Erkennung basierend auf typischen Zutatenmustern
        elif re.search(r'^\d+\s*(?:g|kg|ml|l|el|tl|prise|stück|bund)\b', text) or re.search(r'^\d+\s*[a-zäöüß]+\b.*(?:g|kg|ml|l)\b', text):
            section['label'] = 'ingredients'
            
        # Erkennung basierend auf Nummern für Schritte oder typischen Kochverben
        elif re.search(r'^\d+\.\s', text) or re.search(r'^(?:mische|rühre|schneide|koche|brate|backe|gare|serviere)\b', text):
            section['label'] = 'instructions'
            
        # Kontextbasierte Zuweisung basierend auf dem aktuellen Abschnitt
        elif in_ingredient_section:
            section['label'] = 'ingredients'
        elif in_instruction_section:
            section['label'] = 'instructions'
        
        # Spezifische Zutatenmuster
        elif re.search(r'\d+\s*g\b|\d+\s*kg\b|\d+\s*ml\b|\d+\s*l\b', text):
            section['label'] = 'ingredients'
            
        # Wenn nichts passt, keine Zuweisung
        else:
            section['label'] = ''
    
    return sections
            
def main():
    parser = argparse.ArgumentParser(description='Automatisches Labelling von Rezeptabschnitten')
    parser.add_argument('input', help='Pfad zur Eingabe-CSV')
    parser.add_argument('--output', '-o', default='data/annotations_auto_complete.csv',
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