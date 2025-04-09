from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db
from app.models import Recipe, RecipeIngredient, Ingredient, Category
from app.services.nutrition_service import calculate_recipe_nutrition
from app.schemas import RecipeSchema

recipes_bp = Blueprint('recipes', __name__)
recipe_schema = RecipeSchema()
recipes_schema = RecipeSchema(many=True)

@recipes_bp.route('', methods=['GET'])
@jwt_required()
def get_recipes():
    """Alle Rezepte abrufen"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    
    # Filtern nach Kategorie, falls angegeben
    category_id = request.args.get('category_id', type=int)
    query = Recipe.query
    
    if category_id:
        query = query.join(Recipe.categories).filter(Category.id == category_id)
    
    # Volltextsuche, falls angegeben
    search = request.args.get('search', type=str)
    if search:
        query = query.filter(Recipe.title.ilike(f'%{search}%'))
    
    # Sortierung
    sort_by = request.args.get('sort_by', 'created_at')
    sort_order = request.args.get('sort_order', 'desc')
    
    if sort_order == 'desc':
        query = query.order_by(getattr(Recipe, sort_by).desc())
    else:
        query = query.order_by(getattr(Recipe, sort_by))
    
    # Pagination
    pagination = query.paginate(page=page, per_page=per_page)
    
    return jsonify({
        'items': recipes_schema.dump(pagination.items),
        'total': pagination.total,
        'pages': pagination.pages,
        'page': page
    })

@recipes_bp.route('/<int:recipe_id>', methods=['GET'])
@jwt_required()
def get_recipe(recipe_id):
    """Einzelnes Rezept abrufen"""
    recipe = Recipe.query.get_or_404(recipe_id)
    return jsonify(recipe_schema.dump(recipe))

@recipes_bp.route('', methods=['POST'])
@jwt_required()
def create_recipe():
    """Neues Rezept erstellen"""
    data = request.get_json()
    user_id = get_jwt_identity()
    
    # Basisdaten für Rezept
    recipe = Recipe(
        title=data['title'],
        description=data.get('description', ''),
        preparation_time=data.get('preparation_time'),
        cooking_time=data.get('cooking_time'),
        servings=data['servings'],
        difficulty=data.get('difficulty'),
        image_path=data.get('image_path'),
        pdf_path=data.get('pdf_path'),
        instructions=data['instructions'],
        notes=data.get('notes', ''),
        created_by=user_id
    )
    
    # Kategorien zuordnen
    if 'categories' in data:
        categories = Category.query.filter(Category.id.in_(data['categories'])).all()
        recipe.categories = categories
    
    # Zutaten hinzufügen
    if 'ingredients' in data:
        for ingredient_data in data['ingredients']:
            # Prüfen, ob Zutat bereits existiert
            ingredient = Ingredient.query.filter_by(name=ingredient_data['name']).first()
            if not ingredient:
                # Neue Zutat anlegen
                ingredient = Ingredient(
                    name=ingredient_data['name'],
                    unit=ingredient_data.get('unit')
                )
                db.session.add(ingredient)
                db.session.flush()  # ID generieren
            
            # Zutat dem Rezept zuordnen
            recipe_ingredient = RecipeIngredient(
                recipe=recipe,
                ingredient=ingredient,
                amount=ingredient_data['amount'],
                unit=ingredient_data.get('unit'),
                notes=ingredient_data.get('notes')
            )
            recipe.recipe_ingredients.append(recipe_ingredient)
    
    db.session.add(recipe)
    db.session.commit()
    
    # Nährwerte berechnen
    calculate_recipe_nutrition(recipe.id)
    
    return jsonify(recipe_schema.dump(recipe)), 201

@recipes_bp.route('/<int:recipe_id>', methods=['PUT'])
@jwt_required()
def update_recipe(recipe_id):
    """Rezept aktualisieren"""
    recipe = Recipe.query.get_or_404(recipe_id)
    data = request.get_json()
    
    # Basisdaten aktualisieren
    recipe.title = data.get('title', recipe.title)
    recipe.description = data.get('description', recipe.description)
    recipe.preparation_time = data.get('preparation_time', recipe.preparation_time)
    recipe.cooking_time = data.get('cooking_time', recipe.cooking_time)
    recipe.servings = data.get('servings', recipe.servings)
    recipe.difficulty = data.get('difficulty', recipe.difficulty)
    recipe.image_path = data.get('image_path', recipe.image_path)
    recipe.instructions = data.get('instructions', recipe.instructions)
    recipe.notes = data.get('notes', recipe.notes)
    
    # Kategorien aktualisieren, falls angegeben
    if 'categories' in data:
        categories = Category.query.filter(Category.id.in_(data['categories'])).all()
        recipe.categories = categories
    
    # Zutaten aktualisieren, falls angegeben
    if 'ingredients' in data:
        # Bestehende Zutaten entfernen
        RecipeIngredient.query.filter_by(recipe_id=recipe.id).delete()
        
        # Neue Zutaten hinzufügen
        for ingredient_data in data['ingredients']:
            # Prüfen, ob Zutat bereits existiert
            ingredient = Ingredient.query.filter_by(name=ingredient_data['name']).first()
            if not ingredient:
                # Neue Zutat anlegen
                ingredient = Ingredient(
                    name=ingredient_data['name'],
                    unit=ingredient_data.get('unit')
                )
                db.session.add(ingredient)
                db.session.flush()  # ID generieren
            
            # Zutat dem Rezept zuordnen
            recipe_ingredient = RecipeIngredient(
                recipe=recipe,
                ingredient=ingredient,
                amount=ingredient_data['amount'],
                unit=ingredient_data.get('unit'),
                notes=ingredient_data.get('notes')
            )
            db.session.add(recipe_ingredient)
    
    db.session.commit()
    
    # Nährwerte neu berechnen
    calculate_recipe_nutrition(recipe.id)
    
    return jsonify(recipe_schema.dump(recipe))

@recipes_bp.route('/<int:recipe_id>', methods=['DELETE'])
@jwt_required()
def delete_recipe(recipe_id):
    """Rezept löschen"""
    recipe = Recipe.query.get_or_404(recipe_id)
    db.session.delete(recipe)
    db.session.commit()
    return '', 204

@recipes_bp.route('/<int:recipe_id>/scale', methods=['GET'])
@jwt_required()
def scale_recipe(recipe_id):
    """Rezept für eine bestimmte Anzahl Portionen skalieren"""
    recipe = Recipe.query.get_or_404(recipe_id)
    servings = request.args.get('servings', type=int)
    
    if not servings or servings <= 0:
        return jsonify({'error': 'Ungültige Portionenzahl'}), 400
    
    # Skalierungsfaktor berechnen
    scaling_factor = servings / recipe.servings
    
    # Rezeptdaten abrufen
    recipe_data = recipe_schema.dump(recipe)
    
    # Zutatenmengen skalieren
    for ingredient in recipe_data['ingredients']:
        ingredient['amount'] = float(ingredient['amount']) * scaling_factor
    
    # Nährwerte skalieren, falls vorhanden
    if recipe_data.get('nutrition'):
        for key, value in recipe_data['nutrition'].items():
            if key not in ['id', 'recipe_id', 'created_at', 'updated_at']:
                recipe_data['nutrition'][key] = float(value) * scaling_factor
    
    return jsonify(recipe_data)

@recipes_bp.route('/favorites', methods=['GET'])
@jwt_required()
def get_favorite_recipes():
    """Favorisierte Rezepte abrufen"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    
    query = Recipe.query.filter_by(is_favorite=True)
    pagination = query.paginate(page=page, per_page=per_page)
    
    return jsonify({
        'items': recipes_schema.dump(pagination.items),
        'total': pagination.total,
        'pages': pagination.pages,
        'page': page
    })

@recipes_bp.route('/<int:recipe_id>/favorite', methods=['POST'])
@jwt_required()
def toggle_favorite(recipe_id):
    """Rezept als Favorit markieren/demarkieren"""
    recipe = Recipe.query.get_or_404(recipe_id)
    recipe.is_favorite = not recipe.is_favorite
    db.session.commit()
    
    return jsonify({'is_favorite': recipe.is_favorite})