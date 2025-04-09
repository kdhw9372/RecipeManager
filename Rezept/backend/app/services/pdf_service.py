import os
import pdfplumber
import pytesseract
from PIL import Image
import io
import re
import uuid
from werkzeug.utils import secure_filename
from app import db, celery
from app.models import Recipe, Ingredient, RecipeIngredient

class PDFService:
    def __init__(self, storage_path):
        self.storage_path = storage_path
        
    def save_pdf(self, pdf_file):
        """PDF speichern und eindeutigen Dateinamen erstellen"""
        filename = secure_filename(pdf_file.filename)
        # Eindeutigen Dateinamen erstellen
        unique_filename = f"{uuid.uuid4()}_{filename}"
        pdf_path = os.path.join(self.storage_path, unique_filename)
        
        # Verzeichnis erstellen, falls es nicht existiert
        os.makedirs(self.storage_path, exist_ok=True)
        
        # Datei speichern
        pdf_file.save(pdf_path)
        return pdf_path
    
    def extract_recipe_from_pdf(self, pdf_path):
        """Rezept aus PDF extrahieren"""
        result = {
            'title': '',
            'ingredients': [],
            'instructions': '',
            'image_path': None
        }
        
        # PDF mit pdfplumber öffnen
        with pdfplumber.open(pdf_path) as pdf:
            # Titel extrahieren (typischerweise auf der ersten Seite)
            if len(pdf.pages) > 0:
                first_page_text = pdf.pages[0].extract_text()
                if first_page_text:
                    # Nehmen wir an, der Titel ist die erste Zeile
                    result['title'] = first_page_text.split('\n')[0].strip()
            
            # Text aus allen Seiten extrahieren
            full_text = ''
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    full_text += page_text + '\n'
            
            # Zutaten und Zubereitung identifizieren (einfache Heuristik)
            result['ingredients'] = self._extract_ingredients(full_text)
            result['instructions'] = self._extract_instructions(full_text)
            
            # Bild extrahieren
            image_path = self._extract_first_image(pdf, pdf_path)
            result['image_path'] = image_path
        
        return result
    
    def _extract_ingredients(self, text):
        """Zutaten aus dem Text extrahieren"""
        ingredients = []
        
        # Suche nach Abschnitten wie "Zutaten:" oder "Ingredients:"
        ingredient_section = None
        patterns = [
            r'(?:Zutaten|ZUTATEN):(.*?)(?:Zubereitung|ZUBEREITUNG|Anleitung|Vorbereitung|$)',
            r'(?:Ingredients|INGREDIENTS):(.*?)(?:Instructions|INSTRUCTIONS|Preparation|Method|$)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                ingredient_section = match.group(1).strip()
                break
        
        if ingredient_section:
            # Zutaten nach Zeilenumbrüchen aufteilen
            ingredient_lines = ingredient_section.split('\n')
            for line in ingredient_lines:
                line = line.strip()
                if line and not line.lower().startswith(('zutaten', 'ingredients')):
                    # Versuchen, Menge und Zutat zu trennen
                    ingredient_data = self._parse_ingredient_line(line)
                    if ingredient_data:
                        ingredients.append(ingredient_data)
        
        return ingredients
    
    def _parse_ingredient_line(self, line):
        """Einzelne Zutatenlinie parsen"""
        # Einfaches Pattern für Mengen wie "200 g" oder "2 EL"
        match = re.match(r'([\d.,/\s]+)\s*([a-zA-ZäöüÄÖÜß]+)?\s+(.*)', line)
        if match:
            amount = match.group(1).strip()
            unit = match.group(2) if match.group(2) else ''
            name = match.group(3).strip()
            return {
                'amount': amount,
                'unit': unit,
                'name': name
            }
        return {'name': line}  # Fallback, wenn keine strukturierten Daten erkannt werden
    
    def _extract_instructions(self, text):
        """Zubereitungsanweisungen aus dem Text extrahieren"""
        instructions = ""
        
        # Suche nach Abschnitten wie "Zubereitung:" oder "Instructions:"
        patterns = [
            r'(?:Zubereitung|ZUBEREITUNG):(.*?)(?:$)',
            r'(?:Instructions|INSTRUCTIONS|Preparation|Method):(.*?)(?:$)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                instructions = match.group(1).strip()
                break
        
        return instructions
    
    def _extract_first_image(self, pdf, pdf_path):
        """Erstes Bild aus PDF extrahieren und speichern"""
        try:
            # Basis-Dateiname ohne Erweiterung
            base_path = os.path.splitext(pdf_path)[0]
            image_path = f"{base_path}.jpg"
            
            # Durchlaufen aller Seiten und nach Bildern suchen
            for i, page in enumerate(pdf.pages):
                for img in page.images:
                    # Bild aus dem PDF extrahieren
                    image_data = img["stream"].get_data()
                    image = Image.open(io.BytesIO(image_data))
                    
                    # Bild speichern
                    image.save(image_path, "JPEG")
                    return image_path
        except Exception as e:
            print(f"Fehler beim Extrahieren des Bildes: {e}")
        
        return None

@celery.task
def process_pdf_async(pdf_path):
    """Asynchrone Verarbeitung eines PDF-Dokuments"""
    storage_path = os.environ.get('PDF_STORAGE_PATH', '/app/pdf_storage')
    pdf_service = PDFService(storage_path)
    
    # Rezeptdaten extrahieren
    recipe_data = pdf_service.extract_recipe_from_pdf(pdf_path)
    
    # Rezept in der Datenbank speichern (hier nur beispielhaft)
    # In der realen Implementierung müsste dies an die Datenbank angebunden sein
    return recipe_data