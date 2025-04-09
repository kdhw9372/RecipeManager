import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager
from flask_cors import CORS
from celery import Celery

db = SQLAlchemy()
migrate = Migrate()
jwt = JWTManager()
celery = Celery()

def create_app():
    app = Flask(__name__)
    
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['JWT_SECRET_KEY'] = os.environ.get('SECRET_KEY')
    app.config['PDF_STORAGE_PATH'] = os.environ.get('PDF_STORAGE_PATH', '/app/pdf_storage')
    
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    CORS(app)
    
    celery.conf.update(
        broker_url=os.environ.get('REDIS_URL'),
        result_backend=os.environ.get('REDIS_URL')
    )
    
    # Blueprints registrieren
    from app.api.auth import auth_bp
    from app.api.recipes import recipes_bp
    from app.api.ingredients import ingredients_bp
    from app.api.meal_plans import meal_plans_bp
    from app.api.shopping_lists import shopping_lists_bp
    from app.api.pdf import pdf_bp
    
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(recipes_bp, url_prefix='/api/recipes')
    app.register_blueprint(ingredients_bp, url_prefix='/api/ingredients')
    app.register_blueprint(meal_plans_bp, url_prefix='/api/meal-plans')
    app.register_blueprint(shopping_lists_bp, url_prefix='/api/shopping-lists')
    app.register_blueprint(pdf_bp, url_prefix='/api/pdf')
    
    return app