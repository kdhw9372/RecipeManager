from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from app import db
from app.models import Ingredient

ingredients_bp = Blueprint('ingredients', __name__)

@ingredients_bp.route('', methods=['GET'])
@jwt_required()
def get_ingredients():
    """Alle Zutaten abrufen"""
    search = request.args.get('search', '')
    
    if search:
        ingredients = Ingredient.query.filter(Ingredient.name.ilike(f'%{search}%')).all()
    else:
        ingredients = Ingredient.query.all()
    
    return jsonify([
        {
            'id': ingredient.id,
            'name': ingredient.name,
            'unit': ingredient.unit
        }
        for ingredient in ingredients
    ])

@ingredients_bp.route('/<int:ingredient_id>', methods=['GET'])
@jwt_required()
def get_ingredient(ingredient_id):
    """Einzelne Zutat abrufen"""
    ingredient = Ingredient.query.get_or_404(ingredient_id)
    
    return jsonify({
        'id': ingredient.id,
        'name': ingredient.name,
        'unit': ingredient.unit
    })