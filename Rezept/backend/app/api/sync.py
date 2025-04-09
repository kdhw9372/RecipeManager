from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
import os
import json
import datetime
from app import db
from app.models import Recipe, RecipeIngredient, Ingredient, Category, MealPlan, SyncLog
from sqlalchemy import func

sync_bp = Blueprint('sync', __name__)

@sync_bp.route('/status', methods=['GET'])
@jwt_required()
def get_sync_status():
    """Synchronisationsstatus des Benutzers abrufen"""
    user_id = get_jwt_identity()
    
    # Letzter Sync-Zeitpunkt
    last_sync = SyncLog.query.filter_by(user_id=user_id).order_by(SyncLog.created_at.desc()).first()
    
    # Anzahl der Änderungen seit dem letzten Sync
    changes_since_last_sync = 0
    
    if last_sync:
        # Anzahl der Rezepte, die seit dem letzten Sync geändert wurden
        recipe_changes = Recipe.query.filter(Recipe.updated_at > last_sync.created_at).count()
        
        # Anzahl der Kategorien, die seit dem letzten Sync geändert wurden
        category_changes = Category.query.filter(Category.updated_at > last_sync.created_at).count()
        
        # Anzahl der Menüpläne, die seit dem letzten Sync geändert wurden
        meal_plan_changes = MealPlan.query.filter(
            MealPlan.user_id == user_id,
            MealPlan.updated_at > last_sync.created_at
        ).count()
        
        changes_since_last_sync = recipe_changes + category_changes + meal_plan_changes
    
    return jsonify({
        'last_sync': last_sync.created_at.isoformat() if last_sync else None,
        'changes_since_last_sync': changes_since_last_sync,
        'sync_required': changes_since_last_sync > 0 or not last_sync
    })

@sync_bp.route('/recipes', methods=['GET'])
@jwt_required()
def sync_recipes():
    """Rezepte für die Offline-Nutzung synchronisieren"""
    user_id = get_jwt_identity()
    
    # Abfrageparameter
    last_sync_str = request.args.get('last_sync')
    limit = request.args.get('limit', 100, type=int)
    
    query = Recipe.query
    
    # Nur Änderungen seit dem letzten Sync
    if last_sync_str:
        try:
            last_sync = datetime.datetime.fromisoformat(last_sync_str)
            query = query.filter(Recipe.updated_at > last_sync)
        except ValueError:
            return jsonify({'error': 'Ungültiges Datumsformat für last_sync'}), 400
    
    # Anzahl der zu synchronisierenden Rezepte begrenzen
    recipes = query.order_by(Recipe.updated_at.desc()).limit(limit).all()
    
    # Ergebnisse formatieren
    result = []
    for recipe in recipes:
        # Zutaten laden
        ingredients = []
        for recipe_ingredient in recipe.recipe_ingredients:
            ingredients.append({
                'id': recipe_ingredient.ingredient.id,
                'name': recipe_ingredient.ingredient.name,
                'amount': recipe_ingredient.amount,
                'unit': recipe_ingredient.unit,
                'notes': recipe_ingredient.notes
            })
        
        # Kategorien laden
        categories = [{'id': c.id, 'name': c.name} for c in recipe.categories]
        
        # Nährwerte
        nutrition = None
        if recipe.nutrition:
            nutrition = {
                'calories': recipe.nutrition.calories,
                'protein': recipe.nutrition.protein,
                'carbs': recipe.nutrition.carbs,
                'fat': recipe.nutrition.fat,
                'fiber': recipe.nutrition.fiber,
                'sugar': recipe.nutrition.sugar
            }
        
        result.append({
            'id': recipe.id,
            'title': recipe.title,
            'description': recipe.description,
            'preparation_time': recipe.preparation_time,
            'cooking_time': recipe.cooking_time,
            'servings': recipe.servings,
            'difficulty': recipe.difficulty,
            'image_path': recipe.image_path,
            'instructions': recipe.instructions,
            'notes': recipe.notes,
            'is_favorite': recipe.is_favorite,
            'created_by': recipe.created_by,
            'created_at': recipe.created_at.isoformat(),
            'updated_at': recipe.updated_at.isoformat(),
            'ingredients': ingredients,
            'categories': categories,
            'nutrition': nutrition
        })
    
    # Sync-Log erstellen
    sync_log = SyncLog(
        user_id=user_id,
        action='sync_recipes',
        items_count=len(result)
    )
    db.session.add(sync_log)
    db.session.commit()
    
    return jsonify({
        'count': len(result),
        'recipes': result,
        'sync_timestamp': datetime.datetime.now().isoformat()
    })

@sync_bp.route('/meal-plans', methods=['GET'])
@jwt_required()
def sync_meal_plans():
    """Menüpläne für die Offline-Nutzung synchronisieren"""
    user_id = get_jwt_identity()
    
    # Abfrageparameter
    last_sync_str = request.args.get('last_sync')
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    
    query = MealPlan.query.filter_by(user_id=user_id)
    
    # Nur Änderungen seit dem letzten Sync
    if last_sync_str:
        try:
            last_sync = datetime.datetime.fromisoformat(last_sync_str)
            query = query.filter(MealPlan.updated_at > last_sync)
        except ValueError:
            return jsonify({'error': 'Ungültiges Datumsformat für last_sync'}), 400
    
    # Datumsbereich filtern
    if start_date_str:
        try:
            start_date = datetime.date.fromisoformat(start_date_str)
            query = query.filter(MealPlan.date >= start_date)
        except ValueError:
            return jsonify({'error': 'Ungültiges Datumsformat für start_date'}), 400
    
    if end_date_str:
        try:
            end_date = datetime.date.fromisoformat(end_date_str)
            query = query.filter(MealPlan.date <= end_date)
        except ValueError:
            return jsonify({'error': 'Ungültiges Datumsformat für end_date'}), 400
    
    # Menüpläne laden
    meal_plans = query.order_by(MealPlan.date.asc()).all()
    
    # Ergebnisse formatieren
    result = []
    for meal_plan in meal_plans:
        # Rezeptdaten laden
        recipe = Recipe.query.get(meal_plan.recipe_id)
        recipe_data = None
        
        if recipe:
            recipe_data = {
                'id': recipe.id,
                'title': recipe.title,
                'image_path': recipe.image_path
            }
        
        result.append({
            'id': meal_plan.id,
            'date': meal_plan.date.isoformat(),
            'meal_type': meal_plan.meal_type,
            'recipe': recipe_data,
            'servings': meal_plan.servings,
            'notes': meal_plan.notes,
            'created_at': meal_plan.created_at.isoformat(),
            'updated_at': meal_plan.updated_at.isoformat()
        })
    
    # Sync-Log erstellen
    sync_log = SyncLog(
        user_id=user_id,
        action='sync_meal_plans',
        items_count=len(result)
    )
    db.session.add(sync_log)
    db.session.commit()
    
    return jsonify({
        'count': len(result),
        'meal_plans': result,
        'sync_timestamp': datetime.datetime.now().isoformat()
    })

@sync_bp.route('/categories', methods=['GET'])
@jwt_required()
def sync_categories():
    """Kategorien für die Offline-Nutzung synchronisieren"""
    user_id = get_jwt_identity()
    
    # Abfrageparameter
    last_sync_str = request.args.get('last_sync')
    
    query = Category.query
    
    # Nur Änderungen seit dem letzten Sync
    if last_sync_str:
        try:
            last_sync = datetime.datetime.fromisoformat(last_sync_str)
            query = query.filter(Category.updated_at > last_sync)
        except ValueError:
            return jsonify({'error': 'Ungültiges Datumsformat für last_sync'}), 400
    
    # Kategorien laden
    categories = query.order_by(Category.name).all()
    
    # Ergebnisse formatieren
    result = [
        {
            'id': category.id,
            'name': category.name,
            'description': category.description,
            'created_at': category.created_at.isoformat(),
            'updated_at': category.updated_at.isoformat()
        }
        for category in categories
    ]
    
    # Sync-Log erstellen
    sync_log = SyncLog(
        user_id=user_id,
        action='sync_categories',
        items_count=len(result)
    )
    db.session.add(sync_log)
    db.session.commit()
    
    return jsonify({
        'count': len(result),
        'categories': result,
        'sync_timestamp': datetime.datetime.now().isoformat()
    })

@sync_bp.route('/upload', methods=['POST'])
@jwt_required()
def upload_changes():
    """Lokale Änderungen hochladen"""
    user_id = get_jwt_identity()
    
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'Keine Daten zum Synchronisieren'}), 400
    
    # Favoriten aktualisieren
    if 'favorites' in data:
        for favorite in data['favorites']:
            recipe_id = favorite.get('recipe_id')
            is_favorite = favorite.get('is_favorite', False)
            
            if recipe_id:
                recipe = Recipe.query.get(recipe_id)
                if recipe:
                    recipe.is_favorite = is_favorite
    
    # Neue Menüpläne hinzufügen
    if 'meal_plans' in data:
        for meal_plan_data in data['meal_plans']:
            # Lokale ID entfernen (kann auf dem Client anders sein)
            if 'local_id' in meal_plan_data:
                del meal_plan_data['local_id']
            
            # Prüfen, ob es sich um eine Aktualisierung oder einen neuen Eintrag handelt
            if 'id' in meal_plan_data and meal_plan_data['id']:
                meal_plan = MealPlan.query.get(meal_plan_data['id'])
                if meal_plan and meal_plan.user_id == user_id:
                    # Existierenden Menüplan aktualisieren
                    if 'date' in meal_plan_data:
                        meal_plan.date = datetime.date.fromisoformat(meal_plan_data['date'])
                    if 'meal_type' in meal_plan_data:
                        meal_plan.meal_type = meal_plan_data['meal_type']
                    if 'recipe_id' in meal_plan_data:
                        meal_plan.recipe_id = meal_plan_data['recipe_id']
                    if 'servings' in meal_plan_data:
                        meal_plan.servings = meal_plan_data['servings']
                    if 'notes' in meal_plan_data:
                        meal_plan.notes = meal_plan_data['notes']
            else:
                # Neuen Menüplan erstellen
                try:
                    new_meal_plan = MealPlan(
                        user_id=user_id,
                        date=datetime.date.fromisoformat(meal_plan_data['date']),
                        meal_type=meal_plan_data['meal_type'],
                        recipe_id=meal_plan_data['recipe_id'],
                        servings=meal_plan_data.get('servings', 1),
                        notes=meal_plan_data.get('notes')
                    )
                    db.session.add(new_meal_plan)
                except (KeyError, ValueError) as e:
                    continue  # Ungültige Daten überspringen
    
    # Notizen aktualisieren
    if 'recipe_notes' in data:
        for note in data['recipe_notes']:
            recipe_id = note.get('recipe_id')
            notes_text = note.get('notes')
            
            if recipe_id and notes_text is not None:
                recipe = Recipe.query.get(recipe_id)
                if recipe:
                    recipe.notes = notes_text
    
    # Änderungen speichern
    db.session.commit()
    
    # Sync-Log erstellen
    sync_log = SyncLog(
        user_id=user_id,
        action='upload_changes',
        items_count=len(data.get('favorites', [])) + len(data.get('meal_plans', [])) + len(data.get('recipe_notes', []))
    )
    db.session.add(sync_log)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Änderungen wurden erfolgreich synchronisiert',
        'sync_timestamp': datetime.datetime.now().isoformat()
    })