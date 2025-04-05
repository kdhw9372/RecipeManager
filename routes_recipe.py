"""
Routes für die Rezept-Funktionalitäten der App.
"""
import os
import uuid
from flask import request, jsonify, current_app, send_file
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from models import db, Recipe, Ingredient, Instruction
from optimized_recipe_extractor import extract_recipe_from_pdf  # Geändert von from optimized_recipe_extractor zu import extract_recipe_from_pdf
import logging

# Logging konfigurieren
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Pfad zum trainierten Modell (geändert zu enhanced)
MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'models/recipe_classifier_enhanced.joblib')

def register_recipe_routes(app):
    """
    Registriert alle API-Routen für Rezept-Funktionalitäten.
    """
    # Konfigurieren des Upload-Ordners
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
    
    # Modellverzeichnis erstellen, falls nicht vorhanden
    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    
    @app.route('/api/recipes/upload', methods=['POST'])
    @login_required
    def upload_recipe():
        """
        Endpunkt zum Hochladen und Verarbeiten von PDF-Rezepten.
        Verwendet ML zur automatischen Extraktion von Rezeptinformationen.
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
            
            # ML-gestützte Extraktion der Rezeptinformationen
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
            
            # Speichere das Rezept und die extrahierten Daten in der Datenbank
            recipe = Recipe(
                title=extracted_data['title'],
                file_path=filename,
                user_id=current_user.id
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
            
            return jsonify({
                'message': 'Rezept erfolgreich hochgeladen und verarbeitet',
                'recipe_id': recipe.id,
                'extracted_data': extracted_data
            }), 201
            
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
                    'created_at': recipe.created_at.isoformat(),
                    'ingredients': ingredients.text if ingredients else '',
                    'instructions': instructions.text if instructions else ''
                }
                result.append(recipe_data)
            
            return jsonify({'recipes': result}), 200
            
        except Exception as e:
            logger.error(f"Fehler beim Abrufen der Rezepte: {str(e)}")
            return jsonify({'error': f"Fehler beim Abrufen der Rezepte: {str(e)}"}), 500
    
    @app.route('/api/recipes/<int:recipe_id>', methods=['GET'])
    @login_required
    def get_recipe(recipe_id):
        """Gibt ein bestimmtes Rezept zurück."""
        try:
            recipe = Recipe.query.filter_by(id=recipe_id, user_id=current_user.id).first()
            
            if not recipe:
                return jsonify({'error': 'Rezept nicht gefunden'}), 404
            
            # Zutaten und Anweisungen abrufen
            ingredients = Ingredient.query.filter_by(recipe_id=recipe.id).first()
            instructions = Instruction.query.filter_by(recipe_id=recipe.id).first()
            
            recipe_data = {
                'id': recipe.id,
                'title': recipe.title,
                'file_path': recipe.file_path,
                'created_at': recipe.created_at.isoformat(),
                'ingredients': ingredients.text if ingredients else '',
                'instructions': instructions.text if instructions else ''
            }
            
            return jsonify({'recipe': recipe_data}), 200
            
        except Exception as e:
            logger.error(f"Fehler beim Abrufen des Rezepts: {str(e)}")
            return jsonify({'error': f"Fehler beim Abrufen des Rezepts: {str(e)}"}), 500
    
    @app.route('/api/recipes/<int:recipe_id>', methods=['PUT'])
    @login_required
    def update_recipe(recipe_id):
        """Aktualisiert ein Rezept."""
        try:
            recipe = Recipe.query.filter_by(id=recipe_id, user_id=current_user.id).first()
            
            if not recipe:
                return jsonify({'error': 'Rezept nicht gefunden'}), 404
            
            data = request.get_json()
            
            # Titel aktualisieren
            if 'title' in data:
                recipe.title = data['title']
            
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
            
            # Datei löschen, wenn vorhanden
            if recipe.file_path:
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], recipe.file_path)
                if os.path.exists(file_path):
                    os.remove(file_path)
            
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