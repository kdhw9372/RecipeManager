"""
Quick-Fix-Skript zur Erstellung von Labels für die Rezeptabschnitte.
"""
import pandas as pd
import re
import os
import logging

# Logging konfigurieren
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    input_file = 'data/annotations_all_template.csv'
    output_file = 'data/annotations_all_labeled.csv'
    
    try:
        # CSV mit expliziter Kodierung lesen
        df = pd.read_csv(input_file, encoding='utf-8')
        logger.info(f"CSV geladen mit {len(df)} Zeilen")
        
        # Rezepte nach Dateiname gruppieren
        recipe_groups = df.groupby('filename')
        
        # Ergebnisse sammeln
        all_rows = []
        
        # Für jedes Rezept Labels setzen
        for recipe_name, recipe_df in recipe_groups:
            # Sortiere nach Position
            recipe_df = recipe_df.sort_values('position').reset_index(drop=True)
            
            # Erste Zeile als Titel markieren
            if len(recipe_df) > 0:
                recipe_df.at[0, 'label'] = 'title'
                
            # Für jede Zeile Label setzen
            for idx, row in recipe_df.iterrows():
                text = row['text'].lower() if isinstance(row['text'], str) else ""
                
                # Bereits gesetzte Labels beibehalten
                if idx == 0:
                    continue
                
                # Eigenschaften und Nährwerte ignorieren
                if any(keyword in text for keyword in ['eigenschaften', 'glutenfrei', 'nährwerte', 'kcal', 'www.lemenu.ch']):
                    recipe_df.at[idx, 'label'] = ''
                    continue
                
                # Zutaten-Marker erkennen    
                if 'zutaten' in text or 'für' in text and re.search(r'für\s+\d+\s+personen', text):
                    recipe_df.at[idx, 'label'] = 'ingredients'
                    continue
                
                # Zubereitung-Marker erkennen    
                if any(keyword in text for keyword in ['zubereitung', 'zubereiten', 'nachgaren']):
                    recipe_df.at[idx, 'label'] = 'instructions'
                    continue
                
                # Mengenangaben (typisch für Zutaten)
                if (re.search(r'^\d+\s*(?:g|kg|ml|l|el|tl|\bstück\b)', text) or 
                    re.search(r'\d+\s*g\b', text)):
                    recipe_df.at[idx, 'label'] = 'ingredients'
                    continue
                
                # Anweisungen erkennen
                if (re.search(r'^\d+\.', text) or 
                    any(verb in text for verb in ['mischen', 'rühren', 'kochen', 'backen', 'braten', 'garen'])):
                    recipe_df.at[idx, 'label'] = 'instructions'
                    continue
                
                # Wenn keine spezifischen Regeln anwendbar sind, basierend auf Position entscheiden
                if idx < len(recipe_df) * 0.3:
                    recipe_df.at[idx, 'label'] = 'ingredients'
                else:
                    recipe_df.at[idx, 'label'] = 'instructions'
            
            all_rows.append(recipe_df)
        
        # DataFrame aus allen Rezepten erstellen
        result_df = pd.concat(all_rows, ignore_index=True)
        
        # CSV speichern
        result_df.to_csv(output_file, encoding='utf-8', index=False)
        logger.info(f"Ergebnisse in {output_file} gespeichert")
        
        # Statistik ausgeben
        labels_count = result_df['label'].value_counts()
        logger.info(f"Label-Verteilung: {labels_count.to_dict()}")
        
    except Exception as e:
        logger.error(f"Fehler beim Verarbeiten der CSV: {str(e)}")
        raise

if __name__ == "__main__":
    main()