"""
Datenbankmodelle für Rezepte und verwandte Funktionalitäten.
Diese Modelle erweitern die bestehenden User-Modelle in der Anwendung.
"""
from datetime import datetime
from app import db

class Recipe(db.Model):
    """Datenbankmodell für Rezepte."""
    __tablename__ = 'recipes'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(255), nullable=True)  # Pfad zur PDF-Datei
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Fremdschlüssel für den Benutzer
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Beziehungen
    ingredients = db.relationship('Ingredient', backref='recipe', lazy=True, cascade="all, delete-orphan")
    instructions = db.relationship('Instruction', backref='recipe', lazy=True, cascade="all, delete-orphan")
    tags = db.relationship('RecipeTag', backref='recipe', lazy=True, cascade="all, delete-orphan")
    
    def __repr__(self):
        return f'<Recipe {self.title}>'


class Ingredient(db.Model):
    """Datenbankmodell für Zutaten eines Rezepts."""
    __tablename__ = 'ingredients'
    
    id = db.Column(db.Integer, primary_key=True)
    recipe_id = db.Column(db.Integer, db.ForeignKey('recipes.id'), nullable=False)
    text = db.Column(db.Text, nullable=False)  # Vollständiger Text der Zutaten
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<Ingredient for Recipe {self.recipe_id}>'


class Instruction(db.Model):
    """Datenbankmodell für Zubereitungsanweisungen eines Rezepts."""
    __tablename__ = 'instructions'
    
    id = db.Column(db.Integer, primary_key=True)
    recipe_id = db.Column(db.Integer, db.ForeignKey('recipes.id'), nullable=False)
    text = db.Column(db.Text, nullable=False)  # Vollständiger Text der Anweisungen
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<Instruction for Recipe {self.recipe_id}>'


class Tag(db.Model):
    """Datenbankmodell für Tags/Kategorien."""
    __tablename__ = 'tags'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Beziehungen
    recipes = db.relationship('RecipeTag', backref='tag', lazy=True)
    
    def __repr__(self):
        return f'<Tag {self.name}>'


class RecipeTag(db.Model):
    """Verbindungstabelle zwischen Rezepten und Tags (Many-to-Many)."""
    __tablename__ = 'recipe_tags'
    
    id = db.Column(db.Integer, primary_key=True)
    recipe_id = db.Column(db.Integer, db.ForeignKey('recipes.id'), nullable=False)
    tag_id = db.Column(db.Integer, db.ForeignKey('tags.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Zusammengesetzter Unique-Constraint (ein Tag kann nur einmal pro Rezept vorkommen)
    __table_args__ = (db.UniqueConstraint('recipe_id', 'tag_id', name='uq_recipe_tag'),)
    
    def __repr__(self):
        return f'<RecipeTag {self.recipe_id}_{self.tag_id}>'