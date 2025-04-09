from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db
from app.models import ShoppingList, ShoppingListItem, Ingredient, Recipe, MealPlan
from app.services.google_notes_service import GoogleNotesService
from app.schemas import ShoppingListSchema

shopping_lists_bp = Blueprint('shopping_lists', __name__)
shopping_list_schema = ShoppingListSchema()
shopping_lists_schema = ShoppingListSchema(many=True)

# Google Notes Service instanziieren
google_notes = GoogleNotesService()

@shopping_lists_bp.route('', methods=['GET'])
@jwt_required()
def get_shopping_lists():
    """Alle Einkaufslisten des Benutzers abrufen"""
    user_id = get_jwt_identity()
    shopping_lists = ShoppingList.query.filter_by(user_id=user_id).order_by(ShoppingList.created_at.desc()).all()
    return jsonify(shopping_lists_schema.dump(shopping_lists))

@shopping_lists_bp.route('/<int:list_id>', methods=['GET'])
@jwt_required()
def get_shopping_list(list_id):
    """Einzelne Einkaufsliste abrufen"""
    user_id = get_jwt_identity()
    shopping_list = ShoppingList.query.filter_by(id=list_id, user_id=user_id).first_or_404()
    return jsonify(shopping_list_schema.dump(shopping_list))

@shopping_lists_bp.route('', methods=['POST'])
@jwt_required()
def create_shopping_list():
    """Neue Einkaufsliste erstellen"""
    user_id = get_jwt_identity()
    data = request.get_json()
    
    shopping_list = ShoppingList(
        name=data['name'],
        user_id=user_id
    )
    
    # Einträge hinzufügen, falls vorhanden
    if 'items' in data:
        for item_data in data['items']:
            ingredient_id = item_data.get('ingredient_id')
            
            # Zutat aus der Datenbank laden oder neue erstellen
            if ingredient_id:
                ingredient = Ingredient.query.get(ingredient_id)
            else:
                ingredient = Ingredient.query.filter_by(name=item_data['name']).first()
                if not ingredient:
                    ingredient = Ingredient(
                        name=item_data['name'],
                        unit=item_data.get('unit')
                    )
                    db.session.add(ingredient)
                    db.session.flush()
            
            # Eintrag zur Einkaufsliste hinzufügen
            item = ShoppingListItem(
                shopping_list=shopping_list,
                ingredient=ingredient,
                amount=item_data['amount'],
                unit=item_data.get('unit'),
                notes=item_data.get('notes')
            )
            shopping_list.items.append(item)
    
    db.session.add(shopping_list)
    db.session.commit()
    
    return jsonify(shopping_list_schema.dump(shopping_list)), 201

@shopping_lists_bp.route('/generate', methods=['POST'])
@jwt_required()
def generate_shopping_list():
    """Einkaufsliste aus Menüplan generieren"""
    user_id = get_jwt_identity()
    data = request.get_json()
    
    start_date = data['start_date']
    end_date = data['end_date']
    name = data['name']
    
    # Menüplan für den angegebenen Zeitraum laden
    meal_plans = MealPlan.query.filter(
        MealPlan.user_id == user_id,
        MealPlan.date >= start_date,
        MealPlan.date <= end_date
    ).all()
    
    if not meal_plans:
        return jsonify({'message': 'Keine Menüplanung für diesen Zeitraum gefunden'}), 404
    
    # Neue Einkaufsliste erstellen
    shopping_list = ShoppingList(
        name=name,
        user_id=user_id
    )
    db.session.add(shopping_list)
    
    # Zutaten aus allen geplanten Rezepten sammeln und zusammenführen
    ingredients_map = {}  # Map zum Zusammenführen gleicher Zutaten
    
    for meal in meal_plans:
        recipe = Recipe.query.get(meal.recipe_id)
        if not recipe:
            continue
        
        # Skalierungsfaktor berechnen (Portionen im Menüplan / Portionen im Rezept)
        scaling_factor = meal.servings / recipe.servings
        
        # Zutaten durchlaufen und zur Map hinzufügen
        for recipe_ingredient in recipe.recipe_ingredients:
            ingredient = recipe_ingredient.ingredient
            amount = recipe_ingredient.amount * scaling_factor
            
            if ingredient.id in ingredients_map:
                # Vorhandene Zutat - Menge addieren
                ingredients_map[ingredient.id]['amount'] += amount
            else:
                # Neue Zutat hinzufügen
                ingredients_map[ingredient.id] = {
                    'ingredient': ingredient,
                    'amount': amount,
                    'unit': recipe_ingredient.unit or ingredient.unit
                }
    
    # Einträge zur Einkaufsliste hinzufügen
    for item_data in ingredients_map.values():
        item = ShoppingListItem(
            shopping_list=shopping_list,
            ingredient=item_data['ingredient'],
            amount=item_data['amount'],
            unit=item_data['unit']
        )
        db.session.add(item)
    
    db.session.commit()
    
    return jsonify(shopping_list_schema.dump(shopping_list)), 201

@shopping_lists_bp.route('/add-recipe', methods=['POST'])
@jwt_required()
def add_recipe_to_shopping_list():
    """Zutaten eines Rezepts zur Einkaufsliste hinzufügen"""
    user_id = get_jwt_identity()
    data = request.get_json()
    
    recipe_id = data['recipe_id']
    servings = data.get('servings', None)
    shopping_list_id = data.get('shopping_list_id', None)
    
    # Rezept laden
    recipe = Recipe.query.get_or_404(recipe_id)
    
    # Skalierungsfaktor berechnen, wenn Portionen angegeben wurden
    scaling_factor = 1.0
    if servings:
        scaling_factor = servings / recipe.servings
    
    # Bestehende oder neue Einkaufsliste verwenden
    if shopping_list_id:
        shopping_list = ShoppingList.query.filter_by(id=shopping_list_id, user_id=user_id).first_or_404()
    else:
        # Neueste Einkaufsliste des Benutzers verwenden oder neue erstellen
        shopping_list = ShoppingList.query.filter_by(user_id=user_id).order_by(ShoppingList.created_at.desc()).first()
        
        if not shopping_list:
            shopping_list = ShoppingList(
                name=f"Einkaufsliste für {recipe.title}",
                user_id=user_id
            )
            db.session.add(shopping_list)
            db.session.flush()
    
    # Bestehende Einträge in der Einkaufsliste
    existing_items = {item.ingredient_id: item for item in shopping_list.items}
    
    # Zutaten des Rezepts zur Einkaufsliste hinzufügen
    for recipe_ingredient in recipe.recipe_ingredients:
        ingredient = recipe_ingredient.ingredient
        amount = recipe_ingredient.amount * scaling_factor
        
        if ingredient.id in existing_items:
            # Vorhandene Zutat - Menge addieren
            existing_items[ingredient.id].amount += amount
        else:
            # Neue Zutat hinzufügen
            item = ShoppingListItem(
                shopping_list=shopping_list,
                ingredient=ingredient,
                amount=amount,
                unit=recipe_ingredient.unit or ingredient.unit
            )
            db.session.add(item)
    
    db.session.commit()
    
    return jsonify(shopping_list_schema.dump(shopping_list)), 200

@shopping_lists_bp.route('/<int:list_id>/google-notes', methods=['POST'])
@jwt_required()
def export_to_google_notes(list_id):
    """Einkaufsliste zu Google Notizen exportieren"""
    user_id = get_jwt_identity()
    shopping_list = ShoppingList.query.filter_by(id=list_id, user_id=user_id).first_or_404()
    
    # Einträge für Google Notes formatieren
    items = []
    for item in shopping_list.items:
        items.append({
            'name': item.ingredient.name,
            'amount': str(item.amount),
            'unit': item.unit or item.ingredient.unit or ''
        })
    
    # Google Notes Service initialisieren
    if not google_notes:
        return jsonify({'error': 'Google Notes Service nicht verfügbar'}), 500
    
    # Einkaufsliste erstellen
    note_id = google_notes.create_shopping_list(shopping_list.name, items)
    
    if note_id:
        # Notiz-ID in der Datenbank speichern
        shopping_list.google_notes_id = note_id
        db.session.commit()
        
        return jsonify({
            'message': 'Einkaufsliste wurde zu Google Notizen exportiert',
            'google_notes_id': note_id
        })
    else:
        return jsonify({'error': 'Fehler beim Export zu Google Notizen'}), 500

@shopping_lists_bp.route('/<int:list_id>/google-notes/update', methods=['POST'])
@jwt_required()
def update_google_notes(list_id):
    """Bestehende Google Notiz mit aktueller Einkaufsliste aktualisieren"""
    user_id = get_jwt_identity()
    shopping_list = ShoppingList.query.filter_by(id=list_id, user_id=user_id).first_or_404()
    
    # Prüfen, ob eine Google Notes ID vorhanden ist
    if not shopping_list.google_notes_id:
        return jsonify({'error': 'Diese Einkaufsliste wurde noch nicht zu Google Notizen exportiert'}), 400
    
    # Einträge für Google Notes formatieren
    items = []
    for item in shopping_list.items:
        items.append({
            'name': item.ingredient.name,
            'amount': str(item.amount),
            'unit': item.unit or item.ingredient.unit or ''
        })
    
    # Google Notes Service initialisieren
    if not google_notes:
        return jsonify({'error': 'Google Notes Service nicht verfügbar'}), 500
    
    # Einkaufsliste aktualisieren
    success = google_notes.update_shopping_list(shopping_list.google_notes_id, items)
    
    if success:
        return jsonify({'message': 'Einkaufsliste in Google Notizen wurde aktualisiert'})
    else:
        return jsonify({'error': 'Fehler beim Aktualisieren der Einkaufsliste in Google Notizen'}), 500