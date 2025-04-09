from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db
from app.models import MealPlan, Recipe
import datetime

meal_plans_bp = Blueprint('meal_plans', __name__)

@meal_plans_bp.route('', methods=['GET'])
@jwt_required()
def get_meal_plans():
    """Menüplan für einen Zeitraum abrufen"""
    user_id = get_jwt_identity()
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    query = MealPlan.query.filter_by(user_id=user_id)
    
    if start_date:
        query = query.filter(MealPlan.date >= start_date)
    if end_date:
        query = query.filter(MealPlan.date <= end_date)
    
    meal_plans = query.order_by(MealPlan.date).all()
    
    result = []
    for meal_plan in meal_plans:
        recipe = Recipe.query.get(meal_plan.recipe_id)
        result.append({
            'id': meal_plan.id,
            'date': meal_plan.date.isoformat(),
            'meal_type': meal_plan.meal_type,
            'recipe': {
                'id': recipe.id,
                'title': recipe.title,
                'image_path': recipe.image_path
            } if recipe else None,
            'servings': meal_plan.servings,
            'notes': meal_plan.notes
        })
    
    return jsonify(result)

@meal_plans_bp.route('', methods=['POST'])
@jwt_required()
def create_meal_plan():
    """Mahlzeit zum Menüplan hinzufügen"""
    user_id = get_jwt_identity()
    data = request.get_json()
    
    meal_plan = MealPlan(
        user_id=user_id,
        date=datetime.datetime.fromisoformat(data['date']),
        meal_type=data['meal_type'],
        recipe_id=data['recipe_id'],
        servings=data.get('servings', 1),
        notes=data.get('notes', '')
    )
    
    db.session.add(meal_plan)
    db.session.commit()
    
    recipe = Recipe.query.get(meal_plan.recipe_id)
    
    return jsonify({
        'id': meal_plan.id,
        'date': meal_plan.date.isoformat(),
        'meal_type': meal_plan.meal_type,
        'recipe': {
            'id': recipe.id,
            'title': recipe.title,
            'image_path': recipe.image_path
        } if recipe else None,
        'servings': meal_plan.servings,
        'notes': meal_plan.notes
    }), 201

@meal_plans_bp.route('/<int:meal_plan_id>', methods=['PUT'])
@jwt_required()
def update_meal_plan(meal_plan_id):
    """Mahlzeit im Menüplan aktualisieren"""
    user_id = get_jwt_identity()
    meal_plan = MealPlan.query.filter_by(id=meal_plan_id, user_id=user_id).first_or_404()
    
    data = request.get_json()
    
    if 'date' in data:
        meal_plan.date = datetime.datetime.fromisoformat(data['date'])
    if 'meal_type' in data:
        meal_plan.meal_type = data['meal_type']
    if 'recipe_id' in data:
        meal_plan.recipe_id = data['recipe_id']
    if 'servings' in data:
        meal_plan.servings = data['servings']
    if 'notes' in data:
        meal_plan.notes = data['notes']
    
    db.session.commit()
    
    recipe = Recipe.query.get(meal_plan.recipe_id)
    
    return jsonify({
        'id': meal_plan.id,
        'date': meal_plan.date.isoformat(),
        'meal_type': meal_plan.meal_type,
        'recipe': {
            'id': recipe.id,
            'title': recipe.title,
            'image_path': recipe.image_path
        } if recipe else None,
        'servings': meal_plan.servings,
        'notes': meal_plan.notes
    })

@meal_plans_bp.route('/<int:meal_plan_id>', methods=['DELETE'])
@jwt_required()
def delete_meal_plan(meal_plan_id):
    """Mahlzeit aus Menüplan entfernen"""
    user_id = get_jwt_identity()
    meal_plan = MealPlan.query.filter_by(id=meal_plan_id, user_id=user_id).first_or_404()
    
    db.session.delete(meal_plan)
    db.session.commit()
    
    return '', 204