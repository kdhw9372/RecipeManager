import os
import re
import uuid
import tempfile
import logging
import pytesseract
import numpy as np
import pdfplumber
from PIL import Image
import io
from pdf2image import convert_from_path, convert_from_bytes
from werkzeug.utils import secure_filename
from concurrent.futures import ThreadPoolExecutor
from app import db, celery
from app.models import Recipe, Ingredient, RecipeIngredient, RecipeNutrition, PDFProcessingQueue

# Logger konfigurieren
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PDFProcessingService:
    """Service zur optimierten Verarbeitung von PDF-Dateien mit OCR"""
    
    def __init__(self, storage_path, max_workers=4, dpi=300):
        self.storage_path = storage_path
        self.max_workers = max_workers  # Anzahl paralleler Worker
        self.dpi = dpi                  # Auflösung für die Bildkonvertierung
        
        # Einstellungen für Tesseract OCR
        self.tesseract_config = r'--oem 3 --psm 6 -l deu+eng'
        
        # Verzeichnisse erstellen, falls sie nicht existieren
        os.makedirs(storage_path, exist_ok=True)
        os.makedirs(os.path.join(storage_path, 'images'), exist_ok=True)
    
    def save_pdf(self, pdf_file):
        """PDF speichern und eindeutigen Dateinamen erstellen"""
        if not pdf_file:
            return None
            
        filename = secure_filename(pdf_file.filename)
        # Eindeutigen Dateinamen erstellen
        unique_filename = f"{uuid.uuid4()}_{filename}"
        pdf_path = os.path.join(self.storage_path, unique_filename)
        
        # Datei speichern
        pdf_file.save(pdf_path)
        
        # Eintrag in die Verarbeitungswarteschlange erstellen
        queue_item = PDFProcessingQueue(
            file_path=pdf_path,
            original_filename=filename,
            status='pending'
        )
        db.session.add(queue_item)
        db.session.commit()
        
        # Asynchrone Verarbeitung starten
        process_pdf_async.delay(queue_item.id)
        
        return {
            'queue_id': queue_item.id,
            'filename': filename,
            'status': 'queued'
        }
    
    def get_text_with_ocr(self, image):
        """Text aus einem Bild mit OCR extrahieren"""
        try:
            text = pytesseract.image_to_string(image, config=self.tesseract_config)
            return text
        except Exception as e:
            logger.error(f"OCR-Fehler: {str(e)}")
            return ""
    
    def preprocess_image(self, image):
        """Bildvorverarbeitung für bessere OCR-Ergebnisse"""
        # In Graustufen umwandeln
        if image.mode != 'L':
            image = image.convert('L')
        
        # Kontrast erhöhen
        import cv2
        import numpy as np
        
        img_np = np.array(image)
        
        # Adaptive Thresholding
        processed = cv2.adaptiveThreshold(
            img_np, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
            cv2.THRESH_BINARY, 11, 2
        )
        
        # Rauschen entfernen
        kernel = np.ones((1, 1), np.uint8)
        processed = cv2.morphologyEx(processed, cv2.MORPH_CLOSE, kernel)
        
        return Image.fromarray(processed)
    
    def extract_recipe_from_pdf(self, pdf_path):
        """Rezept aus PDF extrahieren mit verbesserter OCR"""
        result = {
            'title': '',
            'ingredients': [],
            'instructions': '',
            'image_path': None,
            'error': None
        }
        
        try:
            # 1. Versuchen, mit pdfplumber Text zu extrahieren
            extracted_text = ""
            extracted_title = ""
            
            try:
                with pdfplumber.open(pdf_path) as pdf:
                    # Titel von der ersten Seite extrahieren
                    if len(pdf.pages) > 0:
                        first_page_text = pdf.pages[0].extract_text()
                        if first_page_text:
                            lines = first_page_text.split('\n')
                            # Erste nichtleere Zeile als Titel verwenden
                            for line in lines:
                                if line.strip():
                                    extracted_title = line.strip()
                                    break
                    
                    # Text aus allen Seiten extrahieren
                    for page in pdf.pages:
                        page_text = page.extract_text()
                        if page_text:
                            extracted_text += page_text + '\n'
            except Exception as e:
                logger.warning(f"pdfplumber konnte Text nicht extrahieren: {str(e)}")
            
            # 2. Falls pdfplumber keinen Text extrahieren konnte oder zu wenig Text gefunden wurde,
            # verwenden wir OCR auf konvertierten Bildern
            if not extracted_text or len(extracted_text) < 100:
                logger.info(f"Verwende OCR für {pdf_path}")
                
                # PDF in Bilder umwandeln
                images = []
                try:
                    images = convert_from_path(pdf_path, dpi=self.dpi)
                except Exception as e:
                    logger.error(f"Fehler bei der PDF-Konvertierung: {str(e)}")
                    return {**result, 'error': f"PDF konnte nicht konvertiert werden: {str(e)}"}
                
                # Bild für die Rezeptvorschau speichern (erstes Bild)
                if images:
                    image_filename = f"{os.path.splitext(os.path.basename(pdf_path))[0]}.jpg"
                    image_path = os.path.join(self.storage_path, 'images', image_filename)
                    images[0].save(image_path, "JPEG")
                    result['image_path'] = image_path
                
                # Text mit OCR aus allen Seiten extrahieren
                all_text = ""
                
                # Parallele Verarbeitung der Bilder
                def process_image(img):
                    processed_img = self.preprocess_image(img)
                    return self.get_text_with_ocr(processed_img)
                
                with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                    ocr_results = list(executor.map(process_image, images))
                
                all_text = "\n".join(ocr_results)
                
                # Titel aus der ersten Seite extrahieren, falls noch nicht vorhanden
                if not extracted_title and ocr_results:
                    lines = ocr_results[0].split('\n')
                    # Erste nichtleere Zeile als Titel verwenden
                    for line in lines:
                        if line.strip():
                            extracted_title = line.strip()
                            break
                
                # OCR-Text verwenden, wenn genug extrahiert wurde
                if len(all_text) > len(extracted_text):
                    extracted_text = all_text
            else:
                # Bild extrahieren, falls noch nicht geschehen
                if not result['image_path']:
                    image_path = self._extract_first_image(pdf_path)
                    result['image_path'] = image_path
            
            # Titel setzen
            result['title'] = extracted_title
            
            # Zutaten und Anleitung extrahieren
            result['ingredients'] = self._extract_ingredients(extracted_text)
            result['instructions'] = self._extract_instructions(extracted_text)
            
            return result
            
        except Exception as e:
            logger.error(f"Fehler bei der PDF-Verarbeitung: {str(e)}")
            return {**result, 'error': f"PDF konnte nicht verarbeitet werden: {str(e)}"}
    
    def _extract_ingredients(self, text):
        """Zutaten aus dem Text extrahieren mit verbesserten Patterns"""
        ingredients = []
        
        # Suche nach Zutatenlisten mit verschiedenen Patterns
        ingredient_section = None
        
        # Deutsche und englische Muster für den Zutatenabschnitt
        patterns = [
            # Deutsche Patterns
            r'(?:Zutaten|ZUTATEN|Ingredients|INGREDIENTS)[\s:]+(.*?)(?:Zubereitung|ZUBEREITUNG|Anleitung|ANLEITUNG|Vorbereitung|Instructions|Method|$)',
            r'(?:Einkaufsliste|EINKAUFSLISTE|Shopping list)[\s:]+(.*?)(?:Zubereitung|ZUBEREITUNG|Anleitung|ANLEITUNG|$)',
            # Fallback: Suche nach typischen Zutatenformaten
            r'((?:\d+[\s-]*(?:g|kg|ml|l|EL|TL|Stück|Stk|Prise|Bund|Dose|Packung|Pck)\s+[A-Za-zäöüÄÖÜß]+(?:\s+[A-Za-zäöüÄÖÜß]+)*[\r\n]+)+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
            if match:
                ingredient_section = match.group(1).strip()
                break
        
        if ingredient_section:
            # Zutaten nach Zeilenumbrüchen aufteilen
            ingredient_lines = re.split(r'[\r\n]+', ingredient_section)
            for line in ingredient_lines:
                line = line.strip()
                if line and not re.match(r'^(?:Zutaten|ZUTATEN|Ingredients|INGREDIENTS|Einkaufsliste|EINKAUFSLISTE)[\s:]*$', line, re.IGNORECASE):
                    # Versuchen, Menge und Zutat zu trennen
                    ingredient_data = self._parse_ingredient_line(line)
                    if ingredient_data:
                        ingredients.append(ingredient_data)
                        
        # Fallback: Wenn keine Zutaten gefunden wurden, nach typischen Mengenangaben suchen
        if not ingredients:
            # Suche nach Zeilen mit Mengenangaben
            lines = re.split(r'[\r\n]+', text)
            for line in lines:
                line = line.strip()
                if line and re.search(r'\d+\s*(?:g|kg|ml|l|EL|TL|Stück|Stk|Prise|Bund)', line, re.IGNORECASE):
                    ingredient_data = self._parse_ingredient_line(line)
                    if ingredient_data:
                        ingredients.append(ingredient_data)
        
        return ingredients
    
    def _parse_ingredient_line(self, line):
        """Einzelne Zutatenlinie parsen mit verbesserten Regex-Patterns"""
        # Verschiedene Patterns für Zutatenzeilen
        patterns = [
            # Pattern für "200 g Mehl"
            r'^([\d.,/\s]+)\s*([a-zA-ZäöüÄÖÜß]+)?\s+(.+)$',
            # Pattern für "Mehl, 200 g"
            r'^([a-zA-ZäöüÄÖÜß\s]+),\s*([\d.,/\s]+)\s*([a-zA-ZäöüÄÖÜß]+)?$',
            # Pattern für Zutaten ohne Mengenangabe
            r'^([a-zA-ZäöüÄÖÜß\s]+)$'
        ]
        
        for pattern in patterns:
            match = re.match(pattern, line)
            if match:
                if pattern == patterns[0]:  # "200 g Mehl"
                    amount = match.group(1).strip()
                    unit = match.group(2) if match.group(2) else ''
                    name = match.group(3).strip()
                    return {
                        'amount': amount,
                        'unit': unit,
                        'name': name
                    }
                elif pattern == patterns[1]:  # "Mehl, 200 g"
                    name = match.group(1).strip()
                    amount = match.group(2).strip()
                    unit = match.group(3) if match.group(3) else ''
                    return {
                        'amount': amount,
                        'unit': unit,
                        'name': name
                    }
                else:  # Zutat ohne Mengenangabe
                    return {
                        'amount': '',
                        'unit': '',
                        'name': match.group(1).strip()
                    }
        
        # Fallback: Wenn kein Pattern passt, Zeile als Zutatennamen behandeln
        return {
            'amount': '',
            'unit': '',
            'name': line.strip()
        }
    
    def _extract_instructions(self, text):
        """Zubereitungsanweisungen aus dem Text extrahieren mit verbesserten Patterns"""
        instructions = ""
        
        # Verschiedene Patterns für den Zubereitungsabschnitt
        patterns = [
            # Deutsche Patterns
            r'(?:Zubereitung|ZUBEREITUNG)[\s:]+(.*?)(?:Tipps|TIPPS|Hinweise|Notes|$)',
            r'(?:Anleitung|ANLEITUNG)[\s:]+(.*?)(?:Tipps|TIPPS|Hinweise|Notes|$)',
            # Englische Patterns
            r'(?:Instructions|INSTRUCTIONS)[\s:]+(.*?)(?:Tips|TIPS|Notes|$)',
            r'(?:Preparation|PREPARATION|Method|METHOD)[\s:]+(.*?)(?:Tips|TIPS|Notes|$)',
            # Fallback: Suche nach nummerierten Schritten
            r'((?:\d+\.\s+[A-Za-zäöüÄÖÜß].*[\r\n]+)+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
            if match:
                instructions = match.group(1).strip()
                break
        
        # Fallback: Wenn keine Anleitung gefunden wurde, versuche den Text nach den Zutaten zu extrahieren
        if not instructions:
            ingredients_match = re.search(r'(?:Zutaten|ZUTATEN|Ingredients|INGREDIENTS)[\s:]+(.*)', text, re.DOTALL | re.IGNORECASE)
            if ingredients_match:
                ingredients_pos = ingredients_match.end(0)
                # Text nach den Zutaten nehmen
                remaining_text = text[ingredients_pos:].strip()
                
                # Zutaten-Linien entfernen (typischerweise Mengenangaben)
                lines = re.split(r'[\r\n]+', remaining_text)
                instruction_lines = []
                
                # Zutatenzeilen überspringen (enthalten typischerweise Mengenangaben)
                skip_line = True
                for line in lines:
                    # Zeile enthält wahrscheinlich eine Zutat, wenn sie eine Mengenangabe enthält
                    if re.search(r'\d+\s*(?:g|kg|ml|l|EL|TL|Stück|Stk|Prise|Bund)', line, re.IGNORECASE):
                        skip_line = True
                        continue
                    
                    # Leere Zeile könnte das Ende der Zutatenliste markieren
                    if not line.strip():
                        skip_line = False
                        continue
                    
                    # Ab hier könnten Anweisungen beginnen
                    if not skip_line:
                        instruction_lines.append(line)
                
                if instruction_lines:
                    instructions = '\n'.join(instruction_lines)
        
        return instructions
    
    def _extract_first_image(self, pdf_path):
        """Erstes Bild aus PDF extrahieren und speichern"""
        try:
            # Basisname ohne Erweiterung
            base_name = os.path.splitext(os.path.basename(pdf_path))[0]
            image_filename = f"{base_name}.jpg"
            image_path = os.path.join(self.storage_path, 'images', image_filename)
            
            # PDF in Bilder umwandeln
            images = convert_from_path(pdf_path, dpi=self.dpi, first_page=1, last_page=1)
            
            if images:
                # Erstes Bild speichern
                images[0].save(image_path, "JPEG")
                return image_path
            
            return None
        except Exception as e:
            logger.error(f"Fehler beim Extrahieren des Bildes: {str(e)}")
            return None

@celery.task
def process_pdf_async(queue_item_id):
    """Asynchrone Verarbeitung eines PDF-Dokuments"""
    storage_path = os.environ.get('PDF_STORAGE_PATH', '/app/pdf_storage')
    
    try:
        # Eintrag aus der Warteschlange laden
        queue_item = PDFProcessingQueue.query.get(queue_item_id)
        if not queue_item:
            logger.error(f"Queue-Item {queue_item_id} nicht gefunden")
            return {'error': 'Queue-Item nicht gefunden'}
        
        # Status aktualisieren
        queue_item.status = 'processing'
        db.session.commit()
        
        # PDF-Processing-Service initialisieren
        pdf_service = PDFProcessingService(storage_path)
        
        # Rezeptdaten extrahieren
        recipe_data = pdf_service.extract_recipe_from_pdf(queue_item.file_path)
        
        if recipe_data.get('error'):
            # Fehler bei der Verarbeitung
            queue_item.status = 'error'
            queue_item.error_message = recipe_data['error']
            db.session.commit()
            return {'error': recipe_data['error']}
        
        # Rezept in der Datenbank speichern
        recipe = Recipe(
            title=recipe_data['title'] or os.path.splitext(os.path.basename(queue_item.original_filename))[0],
            instructions=recipe_data['instructions'] or '',
            image_path=recipe