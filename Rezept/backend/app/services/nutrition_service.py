import requests
import json
import os
import logging
from app import db, celery
from app.models import Recipe, RecipeIngredient, Ingredient, RecipeNutrition, Allergen, IngredientAllergen

logger = logging.getLogger(__name__)

class NutritionService:
    """Service zur Berechnung von Nährwerten und Allergenen"""
    
    def __init__(self, api_key=None):
        self.api_key = api_key or os.environ.get('NUTRITION_API_KEY')
        self.api_url = "https://api.edamam.com/api/nutrition-details"
        
        # Lokale Nährwertdatenbank (Fallback)
        self.nutrition_db = self._load_local_nutrition_db()
    
    def _load_local_nutrition_db(self):
        """Lädt die lokale Nährwertdatenbank"""
        db_path = os.path.join(os.path.dirname(__file__), 'nutrition_db.json')
        if os.path.exists(db_path):
            try:
                with open(db_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Fehler beim Laden der lokalen Nährwertdatenbank: {str(e)}")
        
        # Einfache Standard-Datenbank zurückgeben
        return {
            "mehl": {"calories": 364, "protein": 10.3, "carbs": 76.3, "fat": 1.0, "fiber": 2.7},
            "zucker": {"calories": 387, "protein": 0, "carbs": 99.8, "fat": 0, "fiber": 0},
            "butter": {"calories": 717, "protein": 0.9, "carbs": 0.1, "fat": 81.1, "fiber": 0},
            "milch": {"calories": 42, "protein": 3.4, "carbs": 4.8, "fat": 1.0, "fiber": 0},
            "ei": {"calories": 143, "protein": 12.6, "carbs": 0.7, "fat": 9.5, "fiber": 0},
            "kartoffel": {"calories": 77, "protein": 2.0, "carbs": 17.0, "fat": 0.1, "fiber": 2.2},
            "reis": {"calories": 130, "protein": 2.7, "carbs": 28.2, "fat": 0.3, "fiber": 0.4},
            "nudeln": {"calories": 158, "protein": 5.8, "carbs": 30.9, "fat": 0.9, "fiber": 1.8},
            "rind": {"calories": 250, "protein": 26.0, "carbs": 0, "fat": 17.0, "fiber": 0},
            "huhn": {"calories": 165, "protein": 31.0, "carbs": 0, "fat": 3.6, "fiber": 0},
            "lachs": {"calories": 206, "protein": 22.1, "carbs": 0, "fat": 13.4, "fiber": 0},
            "tomate": {"calories": 18, "protein": 0.9, "carbs": 3.9, "fat": 0.2, "fiber": 1.2},
            "gurke": {"calories": 12, "protein": 0.6, "carbs": 2.2, "fat": 0.1, "fiber": 0.7},
            "karotte": {"calories": 41, "protein": 0.9, "carbs": 9.6, "fat": 0.2, "fiber": 2.8},
            "zwiebel": {"calories": 40, "protein": 1.1, "carbs": 9.3, "fat": 0.1, "fiber": 1.7},
            "knoblauch": {"calories": 149, "protein": 6.4, "carbs": 33.1, "fat": 0.5, "fiber": 2.1},
            "olivenöl": {"calories": 884, "protein": 0, "carbs": 0, "fat": 100, "fiber": 0},
            "apfel": {"calories": 52, "protein": 0.3, "carbs": 13.8, "fat": 0.2, "fiber": 2.4},
            "banane": {"calories": 89, "protein": 1.1, "carbs": 22.8, "fat": 0.3, "fiber": 2.6},
            "orange": {"calories": 47, "protein": 0.9, "carbs": 11.8, "fat": 0.1, "fiber": 2.4}
        }
    
    def calculate_recipe_nutrition(self, recipe_id):
        """Berechnet die Nährwerte für ein Rezept"""
        recipe = Recipe.query.get(recipe_id)
        if not recipe:
            return {'error': 'Rezept nicht gefunden'}
        
        # Nährwerte zurücksetzen
        RecipeNutrition.query.filter_by(recipe_id=recipe_id).delete()
        
        # Zutaten des Rezepts laden
        ingredients = db.session.query(
            RecipeIngredient.amount,
            RecipeIngredient.unit,
            Ingredient.name
        ).join(
            Ingredient, RecipeIngredient.ingredient_id == Ingredient.id
        ).filter(
            RecipeIngredient.recipe_id == recipe_id
        ).all()
        
        if not ingredients:
            return {'error': 'Keine Zutaten gefunden'}
        
        # API-Anfrage vorbereiten
        if self.api_key:
            try:
                return self._calculate_nutrition_api(recipe, ingredients)
            except Exception as e:
                logger.error(f"API-Fehler bei der Nährwertberechnung: {str(e)}")
                # Fallback zur lokalen Berechnung
        
        # Lokale Berechnung
        return self._calculate_nutrition_local(recipe, ingredients)
    
    def _calculate_nutrition_api(self, recipe, ingredients):
        """Berechnet Nährwerte über eine externe API"""
        # Zutaten formatieren
        ing_list = []
        for amount, unit, name in ingredients:
            if amount and unit:
                ing_list.append(f"{amount} {unit} {name}")
            elif amount:
                ing_list.append(f"{amount} {name}")
            else:
                ing_list.append(name)
        
        # API-Anfrage
        payload = {
            "title": recipe.title,
            "ingr": ing_list,
            "prep": recipe.instructions if recipe.instructions else "",
            "yield": str(recipe.servings)
        }
        
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        params = {
            "app_id": os.environ.get('NUTRITION_APP_ID', 'default_app_id'),
            "app_key": self.api_key
        }
        
        response = requests.post(
            self.api_url,
            headers=headers,
            params=params,
            json=payload
        )
        
        if response.status_code != 200:
            logger.error(f"API-Fehler: {response.status_code} - {response.text}")
            raise Exception(f"API-Fehler: {response.status_code}")
        
        # Nährwerte auswerten
        data = response.json()
        
        nutrients = data.get('totalNutrients', {})
        per_serving = data.get('totalDaily', {})
        
        # Nährwerte pro Portion
        calories = nutrients.get('ENERC_KCAL', {}).get('quantity', 0)
        protein = nutrients.get('PROCNT', {}).get('quantity', 0)
        carbs = nutrients.get('CHOCDF', {}).get('quantity', 0)
        fat = nutrients.get('FAT', {}).get('quantity', 0)
        fiber = nutrients.get('FIBTG', {}).get('quantity', 0)
        sugar = nutrients.get('SUGAR', {}).get('quantity', 0)
        
        # Pro Portion
        per_serving = recipe.servings if recipe.servings and recipe.servings > 0 else 1
        calories_per_serving = calories / per_serving
        protein_per_serving = protein / per_serving
        carbs_per_serving = carbs / per_serving
        fat_per_serving = fat / per_serving
        fiber_per_serving = fiber / per_serving
        sugar_per_serving = sugar / per_serving
        
        # Nährwerte speichern
        nutrition = RecipeNutrition(
            recipe_id=recipe.id,
            calories=calories_per_serving,
            protein=protein_per_serving,
            carbs=carbs_per_serving,
            fat=fat_per_serving,
            fiber=fiber_per_serving,
            sugar=sugar_per_serving
        )
        
        db.session.add(nutrition)
        db.session.commit()
        
        return {
            'calories': calories_per_serving,
            'protein': protein_per_serving,
            'carbs': carbs_per_serving,
            'fat': fat_per_serving,
            'fiber': fiber_per_serving,
            'sugar': sugar_per_serving
        }
    
    def _calculate_nutrition_local(self, recipe, ingredients):
        """Berechnet Nährwerte lokal anhand der Datenbank"""
        total_calories = 0
        total_protein = 0
        total_carbs = 0
        total_fat = 0
        total_fiber = 0
        total_sugar = 0
        
        for amount, unit, name in ingredients:
            # Zutat in der lokalen Datenbank suchen
            ingredient_data = None
            
            # Verschiedene Schreibweisen durchsuchen
            name_lower = name.lower()
            for key in self.nutrition_db:
                if key in name_lower or name_lower in key:
                    ingredient_data = self.nutrition_db[key]
                    break
            
            if not ingredient_data:
                continue
            
            # Menge standardisieren (Annahme: Menge in g oder ml)
            try:
                qty = float(amount) if amount else 100
                
                # Einheit berücksichtigen
                if unit:
                    unit_lower = unit.lower()
                    
                    # Umrechnungsfaktoren
                    if unit_lower in ['kg', 'liter', 'l']:
                        qty *= 1000
                    elif unit_lower in ['g', 'ml']:
                        pass  # Standardeinheit
                    elif unit_lower in ['el', 'esslöffel']:
                        qty *= 15  # ca. 15g pro Esslöffel
                    elif unit_lower in ['tl', 'teelöffel']:
                        qty *= 5   # ca. 5g pro Teelöffel
                    elif unit_lower in ['stück', 'stk']:
                        if 'ei' in name_lower:
                            qty *= 60  # ca. 60g pro Ei
                        elif 'zwiebel' in name_lower:
                            qty *= 100  # ca. 100g pro Zwiebel
                        else:
                            qty *= 100  # Standardannahme
            except (ValueError, TypeError):
                qty = 100  # Fallback
            
            # Nährwerte addieren (pro 100g/ml)
            factor = qty / 100
            total_calories += ingredient_data.get('calories', 0) * factor
            total_protein += ingredient_data.get('protein', 0) * factor
            total_carbs += ingredient_data.get('carbs', 0) * factor
            total_fat += ingredient_data.get('fat', 0) * factor
            total_fiber += ingredient_data.get('fiber', 0) * factor
            total_sugar += ingredient_data.get('sugar', 0) * factor
        
        # Pro Portion
        per_serving = recipe.servings if recipe.servings and recipe.servings > 0 else 1
        calories_per_serving = total_calories / per_serving
        protein_per_serving = total_protein / per_serving
        carbs_per_serving = total_carbs / per_serving
        fat_per_serving = total_fat / per_serving
        fiber_per_serving = total_fiber / per_serving
        sugar_per_serving = total_sugar / per_serving
        
        # Nährwerte speichern
        nutrition = RecipeNutrition(
            recipe_id=recipe.id,
            calories=calories_per_serving,
            protein=protein_per_serving,
            carbs=carbs_per_serving,
            fat=fat_per_serving,
            fiber=fiber_per_serving,
            sugar=sugar_per_serving
        )
        
        db.session.add(nutrition)
        db.session.commit()
        
        return {
            'calories': calories_per_serving,
            'protein': protein_per_serving,
            'carbs': carbs_per_serving,
            'fat': fat_per_serving,
            'fiber': fiber_per_serving,
            'sugar': sugar_per_serving
        }
    
    def check_allergens(self, recipe_id):
        """Überprüft ein Rezept auf Allergene"""
        recipe = Recipe.query.get(recipe_id)
        if not recipe:
            return {'error': 'Rezept nicht gefunden'}
        
        # Zutaten des Rezepts laden
        ingredients = db.session.query(
            Ingredient.id,
            Ingredient.name
        ).join(
            RecipeIngredient, RecipeIngredient.ingredient_id == Ingredient.id
        ).filter(
            RecipeIngredient.recipe_id == recipe_id
        ).all()
        
        if not ingredients:
            return {'error': 'Keine Zutaten gefunden'}
        
        # Bekannte Allergene
        allergens = []
        
        for ingredient_id, ingredient_name in ingredients:
            # Bekannte Allergene für diese Zutat abfragen
            known_allergens = db.session.query(
                Allergen.id,
                Allergen.name,
                Allergen.description
            ).join(
                IngredientAllergen, IngredientAllergen.allergen_id == Allergen.id
            ).filter(
                IngredientAllergen.ingredient_id == ingredient_id
            ).all()
            
            # Zu den Ergebnissen hinzufügen
            for allergen_id, allergen_name, allergen_desc in known_allergens:
                allergens.append({
                    'ingredient_id': ingredient_id,
                    'ingredient_name': ingredient_name,
                    'allergen_id': allergen_id,
                    'allergen_name': allergen_name,
                    'allergen_description': allergen_desc
                })
            
            # Automatische Allergenerkennung basierend auf Keywords
            ingredient_lower = ingredient_name.lower()
            
            # Gluten
            if any(keyword in ingredient_lower for keyword in ['weizen', 'gerste', 'roggen', 'hafer', 'dinkel', 'gluten']):
                allergen = Allergen.query.filter_by(name='Gluten').first()
                if allergen and not any(a['allergen_id'] == allergen.id and a['ingredient_id'] == ingredient_id for a in allergens):
                    allergens.append({
                        'ingredient_id': ingredient_id,
                        'ingredient_name': ingredient_name,
                        'allergen_id': allergen.id,
                        'allergen_name': allergen.name,
                        'allergen_description': allergen.description
                    })
            
            # Laktose
            if any(keyword in ingredient_lower for keyword in ['milch', 'joghurt', 'käse', 'sahne', 'butter', 'quark']):
                allergen = Allergen.query.filter_by(name='Laktose').first()
                if allergen and not any(a['allergen_id'] == allergen.id and a['ingredient_id'] == ingredient_id for a in allergens):
                    allergens.append({
                        'ingredient_id': ingredient_id,
                        'ingredient_name': ingredient_name,
                        'allergen_id': allergen.id,
                        'allergen_name': allergen.name,
                        'allergen_description': allergen.description
                    })
            
            # Nüsse
            if any(keyword in ingredient_lower for keyword in ['nuss', 'nüsse', 'mandel', 'haselnuss', 'walnuss', 'cashew', 'pistazie']):
                allergen = Allergen.query.filter_by(name='Nüsse').first()
                if allergen and not any(a['allergen_id'] == allergen.id and a['ingredient_id'] == ingredient_id for a in allergens):
                    allergens.append({
                        'ingredient_id': ingredient_id,
                        'ingredient_name': ingredient_name,
                        'allergen_id': allergen.id,
                        'allergen_name': allergen.name,
                        'allergen_description': allergen.description
                    })
            
            # Eier
            if any(keyword in ingredient_lower for keyword in ['ei', 'eier', 'eigelb', 'eiweiß']):
                allergen = Allergen.query.filter_by(name='Eier').first()
                if allergen and not any(a['allergen_id'] == allergen.id and a['ingredient_id'] == ingredient_id for a in allergens):
                    allergens.append({
                        'ingredient_id': ingredient_id,
                        'ingredient_name': ingredient_name,
                        'allergen_id': allergen.id,
                        'allergen_name': allergen.name,
                        'allergen_description': allergen.description
                    })
            
            # Fisch
            if any(keyword in ingredient_lower for keyword in ['fisch', 'lachs', 'forelle', 'thunfisch', 'kabeljau']):
                allergen = Allergen.query.filter_by(name='Fisch').first()
                if allergen and not any(a['allergen_id'] == allergen.id and a['ingredient_id'] == ingredient_id for a in allergens):
                    allergens.append({
                        'ingredient_id': ingredient_id,
                        'ingredient_name': ingredient_name,
                        'allergen_id': allergen.id,
                        'allergen_name': allergen.name,
                        'allergen_description': allergen.description
                    })
            
            # Soja
            if any(keyword in ingredient_lower for keyword in ['soja', 'tofu', 'sojasauce', 'miso', 'edamame']):
                allergen = Allergen.query.filter_by(name='Soja').first()
                if allergen and not any(a['allergen_id'] == allergen.id and a['ingredient_id'] == ingredient_id for a in allergens):
                    allergens.append({
                        'ingredient_id': ingredient_id,
                        'ingredient_name': ingredient_name,
                        'allergen_id': allergen.id,
                        'allergen_name': allergen.name,
                        'allergen_description': allergen.description
                    })
        
        # Ergebnisse gruppieren
        result = {}
        for allergen in allergens:
            allergen_id = allergen['allergen_id']
            if allergen_id not in result:
                result[allergen_id] = {
                    'allergen_name': allergen['allergen_name'],
                    'allergen_description': allergen['allergen_description'],
                    'ingredients': []
                }
            
            result[allergen_id]['ingredients'].append({
                'id': allergen['ingredient_id'],
                'name': allergen['ingredient_name']
            })
        
        return {
            'recipe_id': recipe_id,
            'recipe_title': recipe.title,
            'allergens': list(result.values())
        }

@celery.task
def calculate_recipe_nutrition(recipe_id):
    """Celery-Task zur Berechnung von Nährwerten"""
    service = NutritionService()
    return service.calculate_recipe_nutrition(recipe_id)

@celery.task
def check_recipe_allergens(recipe_id):
    """Celery-Task zur Überprüfung von Allergenen"""
    service = NutritionService()
    return service.check_allergens(recipe_id)

@celery.task
def calculate_all_recipes_nutrition():
    """Berechnet Nährwerte für alle Rezepte, die noch keine haben"""
    service = NutritionService()
    
    # Rezepte ohne Nährwerte suchen
    recipe_ids = db.session.query(Recipe.id).outerjoin(
        RecipeNutrition,
        Recipe.id == RecipeNutrition.recipe_id
    ).filter(
        RecipeNutrition.recipe_id == None
    ).all()
    
    recipe_ids = [r[0] for r in recipe_ids]
    results = []
    
    for recipe_id in recipe_ids:
        try:
            result = service.calculate_recipe_nutrition(recipe_id)
            results.append({
                'recipe_id': recipe_id,
                'status': 'success',
                'data': result
            })
        except Exception as e:
            results.append({
                'recipe_id': recipe_id,
                'status': 'error',
                'message': str(e)
            })
    
    return {
        'total': len(recipe_ids),
        'results': results
    }