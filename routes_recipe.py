"""
Routes für die Rezept-Funktionalitäten der App.
"""
import os
import uuid
from flask import request, jsonify, current_app, send_file, send_from_directory
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from models import db, Recipe, Ingredient, Instruction
from source_specific_recipe_extractor import extract_recipe_from_pdf
from pdf_image_extractor import extract_images_from_pdf, extract_main_image
import logging

# Logging konfigurieren
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Pfad zum trainierten Modell (falls verwendet)
MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'models/recipe_classifier_enhanced.joblib')

def register_recipe_routes(app):
    """
    Registriert alle API-Routen für Rezept-Funktionalitäten.
    """
    # Konfigurieren der Ordner
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
    IMAGES_FOLDER = os.path.join(UPLOAD_FOLDER, 'images')
    
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(IMAGES_FOLDER, exist_ok=True)
    
    app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
    app.config['IMAGES_FOLDER'] = IMAGES_FOLDER
    
    # Erhöhe das maximale Upload-Limit auf 20 MB
    app.config['MAX_CONTENT_LENGTH'] = 20 * 1024 * 1024
    
    # Modellverzeichnis erstellen, falls nicht vorhanden
    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    
    @app.route('/api/recipes/upload', methods=['POST'])
    @login_required
    def upload_recipe():
        """
        Endpunkt zum Hochladen und Verarbeiten von PDF-Rezepten.
        Verwendet quellspezifische Extraktion für Rezeptinformationen und extrahiert Bilder.
        """
        if 'file' not in request.files:
            return jsonify({'error': 'Keine Datei in der Anfrage gefunden'}), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({'error': 'Kein Dateiname angegeben'}), 400
        
        if not file.filename.lower().endswith('.pdf'):
            return jsonify({'error': 'Nur PDF-Dateien werden unterstützt'}), 400
        
        try:
            # Generiere einen eindeutigen Dateinamen
            original_filename = secure_filename(file.filename)
            filename = f"{uuid.uuid4().hex}_{original_filename}"
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            
            # Datei speichern
            file.save(file_path)
            logger.info(f"Datei gespeichert: {file_path}")
            
            # Extraktion der Rezeptinformationen
            model_exists = os.path.exists(MODEL_PATH)
            model_path = MODEL_PATH if model_exists else None
            
            if not model_exists:
                logger.warning("Kein trainiertes ML-Modell gefunden, verwende regelbasierte Extraktion")
            
            extraction_result = extract_recipe_from_pdf(file_path, model_path)
            
            if not extraction_result['success']:
                return jsonify({
                    'error': f"Fehler bei der Extraktion: {extraction_result.get('error', 'Unbekannter Fehler')}"
                }), 500
            
            extracted_data = extraction_result['data']
            
            # Extrahiere Bilder aus der PDF
            extracted_images = extract_images_from_pdf(file_path, app.config['IMAGES_FOLDER'])
            logger.info(f"Extrahierte Bilder: {len(extracted_images)}")
            
            # Extrahiere das Hauptbild
            main_image = extract_main_image(file_path, app.config['IMAGES_FOLDER'])
            logger.info(f"Hauptbild extrahiert: {main_image}")
            
            # Pfade relativ zum IMAGES_FOLDER machen
            relative_image_paths = []
            for img_path in extracted_images:
                try:
                    relative_path = os.path.relpath(img_path, app.config['UPLOAD_FOLDER'])
                    relative_image_paths.append(relative_path)
                    logger.debug(f"Relativer Bildpfad hinzugefügt: {relative_path}")
                except Exception as e:
                    logger.error(f"Fehler beim Erstellen des relativen Pfads für {img_path}: {str(e)}")
            
            relative_main_image = ""
            if main_image:
                try:
                    relative_main_image = os.path.relpath(main_image, app.config['UPLOAD_FOLDER'])
                    logger.debug(f"Relativer Hauptbildpfad: {relative_main_image}")
                except Exception as e:
                    logger.error(f"Fehler beim Erstellen des relativen Hauptbildpfads: {str(e)}")
            
            # Speichere das Rezept und die extrahierten Daten in der Datenbank
            try:
                # Überprüfe auf leere oder ungültige Werte
                title = extracted_data.get('title', "")
                if not title or len(title.strip()) == 0:
                    title = os.path.splitext(original_filename)[0]  # Verwende Dateinamen als Fallback
                
                # Erstelle ein neues Rezeptobjekt mit den extrahierten Daten
                recipe = Recipe(
                    title=title,
                    file_path=filename,
                    user_id=current_user.id,
                    image_path=relative_main_image if main_image else None,
                    prep_time=extracted_data.get('prep_time'),
                    cook_time=extracted_data.get('cook_time'),
                    servings=extracted_data.get('servings'),
                    calories=extracted_data.get('calories'),
                    protein=extracted_data.get('protein'),
                    fat=extracted_data.get('fat'),
                    carbs=extracted_data.get('carbs')
                )
                
                db.session.add(recipe)
                db.session.flush()  # Weise recipe.id zu, ohne zu committen
                
                # Speichere die Zutaten (falls vorhanden)
                ingredients_text = extracted_data.get('ingredients', '')
                if ingredients_text:
                    ingredient = Ingredient(
                        recipe_id=recipe.id,
                        text=ingredients_text
                    )
                    db.session.add(ingredient)
                
                # Speichere die Anweisungen (falls vorhanden)
                instructions_text = extracted_data.get('instructions', '')
                if instructions_text:
                    instruction = Instruction(
                        recipe_id=recipe.id,
                        text=instructions_text
                    )
                    db.session.add(instruction)
                
                db.session.commit()
                logger.info(f"Rezept {recipe.id} erfolgreich in der Datenbank gespeichert")
                
                # Rückgabe der Ergebnisinformationen
                return jsonify({
                    'message': 'Rezept erfolgreich hochgeladen und verarbeitet',
                    'recipe_id': recipe.id,
                    'extracted_data': {
                        'title': recipe.title,
                        'ingredients': ingredients_text,
                        'instructions': instructions_text,
                        'prep_time': recipe.prep_time,
                        'cook_time': recipe.cook_time,
                        'servings': recipe.servings,
                        'calories': recipe.calories,
                        'protein': recipe.protein,
                        'fat': recipe.fat,
                        'carbs': recipe.carbs
                    },
                    'images': relative_image_paths,
                    'main_image': relative_main_image
                }), 201
                
            except Exception as db_error:
                logger.error(f"Datenbankfehler: {str(db_error)}")
                db.session.rollback()
                return jsonify({
                    'error': f"Fehler beim Speichern in der Datenbank: {str(db_error)}"
                }), 500
                
        except Exception as e:
            logger.error(f"Fehler beim Hochladen des Rezepts: {str(e)}")
            return jsonify({'error': f"Fehler beim Hochladen: {str(e)}"}), 500
    
    @app.route('/api/recipes', methods=['GET'])
    @login_required
    def get_recipes():
        """Gibt alle Rezepte des aktuellen Benutzers zurück."""
        try:
            recipes = Recipe.query.filter_by(user_id=current_user.id).all()
            result = []
            
            for recipe in recipes:
                # Zutaten und Anweisungen abrufen
                ingredients = Ingredient.query.filter_by(recipe_id=recipe.id).first()
                instructions = Instruction.query.filter_by(recipe_id=recipe.id).first()
                
                recipe_data = {
                    'id': recipe.id,
                    'title': recipe.title,
                    'file_path': recipe.file_path,
                    'image_path': recipe.image_path,
                    'created_at': recipe.created_at.isoformat(),
                    'ingredients': ingredients.text if ingredients else '',
                    'instructions': instructions.text if instructions else '',
                    'prep_time': recipe.prep_time,
                    'cook_time': recipe.cook_time,
                    'servings': recipe.servings,
                    'calories': recipe.calories,
                    'protein': recipe.protein,
                    'fat': recipe.fat,
                    'carbs': recipe.carbs
                }
                result.append(recipe_data)
            
            return jsonify({'recipes': result}), 200
            
        except Exception as e:
            logger.error(f"Fehler beim Abrufen der Rezepte: {str(e)}")
            return jsonify({'error': f"Fehler beim Abrufen der Rezepte: {str(e)}"}), 500
    
    @app.route('/api/recipes/<int:recipe_id>', methods=['GET'])
    @login_required
    def get_recipe(recipe_id):
        """Gibt ein bestimmtes Rezept zurück mit verbesserten Fehlerprüfungen."""
        try:
            recipe = Recipe.query.filter_by(id=recipe_id, user_id=current_user.id).first()
            
            if not recipe:
                return jsonify({'error': 'Rezept nicht gefunden'}), 404
            
            # Zutaten und Anweisungen abrufen
            ingredients = Ingredient.query.filter_by(recipe_id=recipe.id).first()
            instructions = Instruction.query.filter_by(recipe_id=recipe.id).first()
            
            # Bilder im Verzeichnis suchen
            image_dir = app.config['IMAGES_FOLDER']
            pdf_base = os.path.splitext(recipe.file_path)[0].split('_')[1]  # Basis-Dateiname des PDFs
            logger.debug(f"Suche Bilder für PDF-Basis: {pdf_base}")
            
            # Alle Bilder im Verzeichnis durchsuchen
            recipe_images = []
            if os.path.exists(image_dir):
                for filename in os.listdir(image_dir):
                    # Bilder suchen, die zum Rezept gehören könnten
                    if pdf_base in filename:
                        image_path = f"images/{filename}"  # Relativer Pfad für das Frontend
                        recipe_images.append(image_path)
                        logger.debug(f"Bild für Rezept gefunden: {image_path}")
            
            # Hauptbild bestimmen
            main_image = None
            if recipe.image_path and os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], recipe.image_path)):
                main_image = recipe.image_path
                logger.debug(f"Hauptbild aus Datenbank verwendet: {main_image}")
            elif recipe_images:
                # Erstes gefundenes Bild als Fallback
                main_image = recipe_images[0]
                logger.debug(f"Hauptbild als Fallback verwendet: {main_image}")
            
            # Entferne mögliche None-Werte und setze Standardwerte
            recipe_data = {
                'id': recipe.id,
                'title': recipe.title or "Unbenanntes Rezept",
                'file_path': recipe.file_path,
                'image_path': main_image,
                'images': recipe_images,
                'created_at': recipe.created_at.isoformat(),
                'ingredients': ingredients.text if ingredients else '',
                'instructions': instructions.text if instructions else '',
                'prep_time': recipe.prep_time or 0,
                'cook_time': recipe.cook_time or 0,
                'servings': recipe.servings or '',
                'calories': recipe.calories or 0,
                'protein': recipe.protein or 0,
                'fat': recipe.fat or 0,
                'carbs': recipe.carbs or 0
            }
            
            # Debug-Informationen ins Log schreiben
            logger.debug(f"Rezeptdaten für ID {recipe_id}: {recipe_data}")
            
            return jsonify({'recipe': recipe_data}), 200
            
        except Exception as e:
            logger.error(f"Fehler beim Abrufen des Rezepts {recipe_id}: {str(e)}")
            return jsonify({
                'error': f"Fehler beim Abrufen des Rezepts: {str(e)}",
                'recipe': {
                    'id': recipe_id,
                    'title': "Fehler beim Laden",
                    'ingredients': '',
                    'instructions': ''
                }
            }), 500
    
    @app.route('/api/recipes/<int:recipe_id>', methods=['PUT'])
    @login_required
    def update_recipe(recipe_id):
        """Aktualisiert ein Rezept."""
        try:
            recipe = Recipe.query.filter_by(id=recipe_id, user_id=current_user.id).first()
            
            if not recipe:
                return jsonify({'error': 'Rezept nicht gefunden'}), 404
            
            data = request.get_json()
            
            # Aktualisiere Rezeptdaten
            if 'title' in data:
                recipe.title = data['title']
            if 'prep_time' in data:
                recipe.prep_time = data['prep_time']
            if 'cook_time' in data:
                recipe.cook_time = data['cook_time']
            if 'servings' in data:
                recipe.servings = data['servings']
            if 'calories' in data:
                recipe.calories = data['calories']
            if 'protein' in data:
                recipe.protein = data['protein']
            if 'fat' in data:
                recipe.fat = data['fat']
            if 'carbs' in data:
                recipe.carbs = data['carbs']
            
            # Zutaten aktualisieren
            if 'ingredients' in data:
                ingredient = Ingredient.query.filter_by(recipe_id=recipe.id).first()
                if ingredient:
                    ingredient.text = data['ingredients']
                else:
                    ingredient = Ingredient(recipe_id=recipe.id, text=data['ingredients'])
                    db.session.add(ingredient)
            
            # Anweisungen aktualisieren
            if 'instructions' in data:
                instruction = Instruction.query.filter_by(recipe_id=recipe.id).first()
                if instruction:
                    instruction.text = data['instructions']
                else:
                    instruction = Instruction(recipe_id=recipe.id, text=data['instructions'])
                    db.session.add(instruction)
            
            db.session.commit()
            
            return jsonify({'message': 'Rezept erfolgreich aktualisiert'}), 200
            
        except Exception as e:
            logger.error(f"Fehler beim Aktualisieren des Rezepts: {str(e)}")
            return jsonify({'error': f"Fehler beim Aktualisieren des Rezepts: {str(e)}"}), 500
    
    @app.route('/api/recipes/<int:recipe_id>', methods=['DELETE'])
    @login_required
    def delete_recipe(recipe_id):
        """Löscht ein Rezept."""
        try:
            recipe = Recipe.query.filter_by(id=recipe_id, user_id=current_user.id).first()
            
            if not recipe:
                return jsonify({'error': 'Rezept nicht gefunden'}), 404
            
            # Zuerst die zugehörigen Datensätze löschen
            Ingredient.query.filter_by(recipe_id=recipe.id).delete()
            Instruction.query.filter_by(recipe_id=recipe.id).delete()
            
            # PDF-Datei löschen, wenn vorhanden
            if recipe.file_path:
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], recipe.file_path)
                if os.path.exists(file_path):
                    os.remove(file_path)
            
            # Bild löschen, wenn vorhanden
            if recipe.image_path:
                image_path = os.path.join(app.config['UPLOAD_FOLDER'], recipe.image_path)
                if os.path.exists(image_path):
                    os.remove(image_path)
            
            # Rezept löschen
            db.session.delete(recipe)
            db.session.commit()
            
            return jsonify({'message': 'Rezept erfolgreich gelöscht'}), 200
            
        except Exception as e:
            logger.error(f"Fehler beim Löschen des Rezepts: {str(e)}")
            return jsonify({'error': f"Fehler beim Löschen des Rezepts: {str(e)}"}), 500

    @app.route('/api/recipes/<int:recipe_id>/pdf', methods=['GET'])
    @login_required
    def get_recipe_pdf(recipe_id):
        """Gibt die Original-PDF-Datei eines Rezepts zurück."""
        try:
            recipe = Recipe.query.filter_by(id=recipe_id, user_id=current_user.id).first()
            
            if not recipe or not recipe.file_path:
                return jsonify({'error': 'PDF nicht gefunden'}), 404
            
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], recipe.file_path)
            if not os.path.exists(file_path):
                return jsonify({'error': 'PDF-Datei nicht mehr vorhanden'}), 404
            
            # Originalnamen (ohne UUID) extrahieren
            original_filename = recipe.file_path.split('_', 1)[1] if '_' in recipe.file_path else recipe.file_path
            
            return send_file(file_path, 
                          download_name=original_filename,
                          as_attachment=True)
            
        except Exception as e:
            logger.error(f"Fehler beim Abrufen der PDF-Datei: {str(e)}")
            return jsonify({'error': f"Fehler beim Abrufen der PDF-Datei: {str(e)}"}), 500
    
    @app.route('/api/uploads/<path:file_path>', methods=['GET'])
    def serve_uploaded_file(file_path):
        """
        Dient hochgeladene Dateien und Bilder aus dem Upload-Verzeichnis.
        Verbesserte Version mit besserer Fehlerbehandlung und Logging.
        """
        try:
            # Sicherheitsüberprüfung: Stellt sicher, dass keine Parent-Verzeichnisse durchlaufen werden
            normalized_path = os.path.normpath(file_path)
            if normalized_path.startswith('..') or normalized_path.startswith('/'):
                logger.warning(f"Sicherheitsrisiko: Pfad {file_path} versucht, Verzeichnis zu verlassen")
                return jsonify({'error': 'Ungültiger Dateipfad'}), 403
            
            # Fullpath zum angeforderten Dateipfad
            full_path = os.path.join(app.config['UPLOAD_FOLDER'], normalized_path)
            
            # Überprüfen, ob die Datei existiert
            if not os.path.exists(full_path) or not os.path.isfile(full_path):
                logger.warning(f"Angeforderte Datei existiert nicht: {full_path}")
                return jsonify({'error': 'Datei nicht gefunden'}), 404
            
            # Dateityp bestimmen
            file_name, file_extension = os.path.splitext(full_path)
            content_type = None
            
            # Unterstützte Bildformate zuordnen
            if file_extension.lower() in ['.jpg', '.jpeg']:
                content_type = 'image/jpeg'
            elif file_extension.lower() == '.png':
                content_type = 'image/png'
            elif file_extension.lower() == '.gif':
                content_type = 'image/gif'
            elif file_extension.lower() == '.pdf':
                content_type = 'application/pdf'
            
            # Wenn der Dateityp unterstützt wird, sende die Datei
            if content_type:
                logger.debug(f"Serving {content_type} file: {full_path}")
                response = send_file(full_path, mimetype=content_type)
                # Cache-Control-Header für Bilder setzen (1 Tag)
                if content_type.startswith('image/'):
                    response.headers['Cache-Control'] = 'public, max-age=86400'
                return response
            else:
                logger.warning(f"Nicht unterstützter Dateityp: {file_extension}")
                return jsonify({'error': 'Nicht unterstützter Dateityp'}), 415
        
        except Exception as e:
            logger.error(f"Fehler beim Bereitstellen der Datei {file_path}: {str(e)}")
            return jsonify({'error': f"Fehler beim Bereitstellen der Datei: {str(e)}"}), 500
    
    @app.route('/api/images/<path:filename>', methods=['GET'])
    def serve_image(filename):
        """Stellt ein Bild direkt aus dem Images-Verzeichnis bereit."""
        try:
            return send_from_directory(app.config['IMAGES_FOLDER'], filename)
        except Exception as e:
            logger.error(f"Fehler beim Bereitstellen des Bildes {filename}: {str(e)}")
            return jsonify({'error': f"Fehler beim Bereitstellen des Bildes: {str(e)}"}), 500
    
    @app.route('/api/debug/images', methods=['GET'])
    def debug_images():
        """Zeigt alle verfügbaren Bilder an - Hilfsfunktion für Debug."""
        images_folder = app.config['IMAGES_FOLDER']
        available_images = []
        
        if os.path.exists(images_folder):
            for filename in os.listdir(images_folder):
                if filename.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
                    available_images.append({
                        'filename': filename,
                        'path': f"images/{filename}",
                        'full_path': os.path.join(images_folder, filename)
                    })
        
        return jsonify({
            'images_folder': images_folder,
            'exists': os.path.exists(images_folder),
            'count': len(available_images),
            'images': available_images
        })