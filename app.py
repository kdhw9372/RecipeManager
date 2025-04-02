import os
import uuid
import re
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
import pdfplumber
from PIL import Image
import io

# App-Initialisierung
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev_key_for_development')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = False

# Erhöhe das maximale Upload-Limit auf 50 MB
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

# Stelle sicher, dass der Upload-Ordner existiert
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

# Erweiterungen initialisieren
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
CORS(app, 
     resources={r"/*": {"origins": "*"}}, 
     supports_credentials=True, 
     allow_headers=["Content-Type", "Authorization"],
     methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])

# Benutzermodell
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_admin = db.Column(db.Boolean, default=False)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def __repr__(self):
        return f'<User {self.username}>'

# Rezept-Modell
class Recipe(db.Model):
    __tablename__ = 'recipes'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    ingredients = db.Column(db.Text)
    instructions = db.Column(db.Text)
    prep_time = db.Column(db.Integer)  # in Minuten
    cook_time = db.Column(db.Integer)  # in Minuten
    servings = db.Column(db.Integer)
    calories = db.Column(db.Integer)
    protein = db.Column(db.Float)  # in Gramm
    fat = db.Column(db.Float)      # in Gramm
    carbs = db.Column(db.Float)    # in Gramm
    pdf_path = db.Column(db.String(255))
    image_path = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Fremdschlüssel zum Benutzer, der das Rezept hochgeladen hat
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    user = db.relationship('User', backref=db.backref('recipes', lazy=True))
    
    # Kategorien und Tags werden über separate Tabellen verknüpft
    
    def __repr__(self):
        return f'<Recipe {self.title}>'

# Hilfstabelle für die n:m-Beziehung zwischen Rezepten und Kategorien
recipe_categories = db.Table('recipe_categories',
    db.Column('recipe_id', db.Integer, db.ForeignKey('recipes.id'), primary_key=True),
    db.Column('category_id', db.Integer, db.ForeignKey('categories.id'), primary_key=True)
)

# Hilfstabelle für die n:m-Beziehung zwischen Rezepten und Tags
recipe_tags = db.Table('recipe_tags',
    db.Column('recipe_id', db.Integer, db.ForeignKey('recipes.id'), primary_key=True),
    db.Column('tag_id', db.Integer, db.ForeignKey('tags.id'), primary_key=True)
)

# Kategorien-Modell
class Category(db.Model):
    __tablename__ = 'categories'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)
    description = db.Column(db.String(255))
    
    # Beziehung zu Rezepten
    recipes = db.relationship('Recipe', secondary=recipe_categories, lazy='subquery',
                              backref=db.backref('categories', lazy=True))
    
    def __repr__(self):
        return f'<Category {self.name}>'

# Tags-Modell
class Tag(db.Model):
    __tablename__ = 'tags'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)
    
    # Beziehung zu Rezepten
    recipes = db.relationship('Recipe', secondary=recipe_tags, lazy='subquery',
                              backref=db.backref('tags', lazy=True))
    
    def __repr__(self):
        return f'<Tag {self.name}>'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Erlaubte Dateierweiterungen
ALLOWED_EXTENSIONS = {'pdf'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Funktion zum Extrahieren von Daten aus der PDF
def extract_data_from_pdf(pdf_path):
    extracted_data = {
        'title': '',
        'ingredients': '',
        'instructions': '',
        'prep_time': None,
        'cook_time': None,
        'servings': None,
        'calories': None,
        'protein': None,
        'fat': None,
        'carbs': None,
        'notes': '',
        'images': []
    }
    
    try:
        # Layout-Erkennung - Versuche, den Typ des PDFs zu erkennen
        layout_type = None
        source_website = None
        
        with pdfplumber.open(pdf_path) as pdf:
            all_text = ""
            page_texts = []
            
            # Extrahiere Text und Bilder von jeder Seite
            for i, page in enumerate(pdf.pages):
                page_text = page.extract_text() or ""
                all_text += page_text
                page_texts.append(page_text)
                
                # Bilder extrahieren
                try:
                    if hasattr(page, 'images') and page.images:
                        image_folder = os.path.join(app.config['UPLOAD_FOLDER'], 'images')
                        if not os.path.exists(image_folder):
                            os.makedirs(image_folder)
                            
                        for j, img in enumerate(page.images):
                            try:
                                image_filename = f"{os.path.basename(pdf_path).split('.')[0]}_img{j+1}.png"
                                image_path = os.path.join(image_folder, image_filename)
                                
                                img_data = img['stream'].get_data()
                                image = Image.open(io.BytesIO(img_data))
                                image.save(image_path)
                                
                                extracted_data['images'].append(image_filename)
                            except Exception as e:
                                print(f"Fehler beim Extrahieren des Bildes: {str(e)}")
                except Exception as e:
                    print(f"Fehler beim Zugriff auf Bilder: {str(e)}")
            
            # Layout-Typ erkennen
            if "lemenu.ch" in all_text.lower():
                layout_type = "lemenu"
                source_website = "lemenu.ch"
            elif "tiptopf" in all_text.lower() or "meintiptopf.ch" in all_text.lower():
                layout_type = "tiptopf"
                source_website = "meintiptopf.ch"
            elif "kochen" in all_text.lower():
                layout_type = "kochen"
                source_website = "kochen.ch"
            
            # Titel extrahieren (meistens am Anfang oder groß dargestellt)
            lines = all_text.split('\n')
            
            # Ignorierliste für Titelzeilen
            ignore_title_lines = ["www.", "http", "©", "erschienen in", "eigenschaften", "zutaten", "zubereitung"]
            
            # Erstes nicht-leeres Element, das nicht in der Ignorierliste ist
            for line in lines:
                if line.strip() and not any(ignore in line.lower() for ignore in ignore_title_lines):
                    extracted_data['title'] = line.strip()
                    break
            
            # Suche nach Zutaten- und Zubereitungsabschnitten
            zutaten_section = False
            zubereitung_section = False
            eigenschaften_section = False
            naehrwerte_section = False
            
            zutaten_lines = []
            zubereitung_lines = []
            eigenschaften_lines = []
            naehrwerte_lines = []
            
            # Keywords für verschiedene Abschnitte
            zutaten_keywords = ["zutaten", "zutaten:", "teig:", "für"]
            zubereitung_keywords = ["zubereitung", "zubereitung:", "backen", "vorgehen", "schritt"]
            eigenschaften_keywords = ["eigenschaften", "eigenschaften:"]
            naehrwerte_keywords = ["nährwerte", "nährwert", "pro portion", "kcal", "fett", "kohlenhydrate", "eiweiss"]
            
            # Spezifische Extraktion basierend auf dem Layout-Typ
            if layout_type == "lemenu":
                # Für lemenu.ch Layout
                current_section = None
                for line in lines:
                    line_lower = line.lower().strip()
                    
                    if not line_lower:
                        continue
                    
                    # Abschnittserkennung
                    if "zutaten" in line_lower and not "zubereitung" in line_lower:
                        current_section = "zutaten"
                        continue
                    elif "zubereitung" in line_lower:
                        current_section = "zubereitung"
                        continue
                    elif any(keyword in line_lower for keyword in naehrwerte_keywords):
                        current_section = "naehrwerte"
                        naehrwerte_lines.append(line)
                        continue
                    
                    # Zeilen zum entsprechenden Abschnitt hinzufügen
                    if current_section == "zutaten":
                        zutaten_lines.append(line)
                    elif current_section == "zubereitung":
                        zubereitung_lines.append(line)
                    elif current_section == "naehrwerte":
                        naehrwerte_lines.append(line)
                
                # Nährwerte extrahieren
                if naehrwerte_lines:
                    naehrwerte_text = ' '.join(naehrwerte_lines)
                    kcal_match = re.search(r'kcal\s+(\d+)', naehrwerte_text)
                    if kcal_match:
                        extracted_data['calories'] = int(kcal_match.group(1))
                    
                    fett_match = re.search(r'Fett\s+(\d+)g', naehrwerte_text)
                    if fett_match:
                        extracted_data['fat'] = int(fett_match.group(1))
                    
                    carbs_match = re.search(r'Kohlenhydrate\s+(\d+)g', naehrwerte_text)
                    if carbs_match:
                        extracted_data['carbs'] = int(carbs_match.group(1))
                    
                    protein_match = re.search(r'Eiweiss\s+(\d+)g', naehrwerte_text)
                    if protein_match:
                        extracted_data['protein'] = int(protein_match.group(1))
                
                # Portionen extrahieren
                for line in zutaten_lines:
                    if "für" in line.lower() and any(c.isdigit() for c in line):
                        persons_match = re.search(r'für\s+(\d+)-?(\d*)\s+(personen|stück|portionen)', line.lower())
                        if persons_match:
                            if persons_match.group(2):  # Bereich (z.B. 4-6)
                                extracted_data['servings'] = f"{persons_match.group(1)}-{persons_match.group(2)}"
                            else:  # Einzelne Zahl
                                extracted_data['servings'] = persons_match.group(1)
                            break
                
            elif layout_type == "tiptopf":
                # Für tiptopf Layout
                # Bei diesem Layout sind Zutaten und Anweisungen oft in Tabellen
                zutaten_started = False
                
                for i, line in enumerate(lines):
                    line_lower = line.lower().strip()
                    
                    if not line_lower:
                        continue
                    
                    # Zeit-Informationen
                    if "min" in line_lower and any(word in line_lower for word in ["backen", "vor- und zubereiten", "gesamtzeit"]):
                        time_match = re.search(r'(\d+)\s*min', line_lower)
                        if time_match and "backen" in line_lower:
                            extracted_data['cook_time'] = int(time_match.group(1))
                        elif time_match and "vor- und zubereiten" in line_lower:
                            extracted_data['prep_time'] = int(time_match.group(1))
                    
                    # Zutaten identifizieren
                    if re.match(r'^\d+\s*g\s+|^\d+\s+|^[a-zA-Z]+\s+vorbereiten', line_lower):
                        zutaten_started = True
                        zutaten_lines.append(line)
                    
                    # Anweisungen identifizieren (normalerweise mit Verben)
                    if zutaten_started and any(verb in line_lower for verb in ["geben", "mischen", "rühren", "backen", "schmelzen", "hacken"]):
                        zubereitung_lines.append(line)
                
            elif layout_type == "kochen":
                # Für kochen.ch Layout
                current_section = None
                
                for line in lines:
                    line_lower = line.lower().strip()
                    
                    if not line_lower:
                        continue
                    
                    # Abschnittserkennung
                    if "zutaten" in line_lower and len(line_lower) < 20:  # Vermeidet längere Texte mit "zutaten" darin
                        current_section = "zutaten"
                        continue
                    elif "zubereitung" in line_lower and len(line_lower) < 20:
                        current_section = "zubereitung"
                        continue
                    elif "eigenschaften" in line_lower:
                        current_section = "eigenschaften"
                        continue
                    elif any(keyword in line_lower for keyword in naehrwerte_keywords):
                        current_section = "naehrwerte"
                        continue
                    
                    # Zeilen zum entsprechenden Abschnitt hinzufügen
                    if current_section == "zutaten":
                        zutaten_lines.append(line)
                    elif current_section == "zubereitung":
                        zubereitung_lines.append(line)
                    elif current_section == "eigenschaften":
                        eigenschaften_lines.append(line)
                    elif current_section == "naehrwerte":
                        naehrwerte_lines.append(line)
                
                # Nummern in Zubereitungsschritten entfernen
                zubereitung_lines = [re.sub(r'^\d+\s+', '', line) for line in zubereitung_lines]
                
            else:
                # Generischer Ansatz für unbekannte Layouts
                current_section = None
                
                for line in lines:
                    line_lower = line.lower().strip()
                    
                    if not line_lower:
                        continue
                    
                    # Abschnittserkennung
                    if any(keyword in line_lower for keyword in zutaten_keywords) and not any(keyword in line_lower for keyword in zubereitung_keywords):
                        current_section = "zutaten"
                        continue
                    elif any(keyword in line_lower for keyword in zubereitung_keywords):
                        current_section = "zubereitung"
                        continue
                    elif any(keyword in line_lower for keyword in eigenschaften_keywords):
                        current_section = "eigenschaften"
                        continue
                    elif any(keyword in line_lower for keyword in naehrwerte_keywords):
                        current_section = "naehrwerte"
                        naehrwerte_lines.append(line)
                        continue
                    
                    # Zeilen zum entsprechenden Abschnitt hinzufügen
                    if current_section == "zutaten":
                        zutaten_lines.append(line)
                    elif current_section == "zubereitung":
                        zubereitung_lines.append(line)
                    elif current_section == "eigenschaften":
                        eigenschaften_lines.append(line)
                    elif current_section == "naehrwerte":
                        naehrwerte_lines.append(line)
                
                # Zutatenliste durch Texterkennung verbessern
                if not zutaten_lines:
                    potential_ingredients = []
                    for line in lines:
                        # Typisches Muster für Zutaten: Menge + Einheit + Zutat
                        if re.search(r'^\d+\s*(g|kg|ml|l|dl|EL|TL|Prise|Stück|Zehe)', line) or \
                           re.search(r'^\d+(\.\d+)?\s+(g|kg|ml|l|dl|EL|TL)', line):
                            potential_ingredients.append(line)
                    
                    if potential_ingredients:
                        zutaten_lines = potential_ingredients
                
                # Zubereitungsschritte durch Texterkennung verbessern
                if not zubereitung_lines:
                    # Suche nach nummerierten Anweisungen
                    numbered_instructions = []
                    for line in lines:
                        if re.match(r'^\d+\.', line):
                            numbered_instructions.append(line)
                    
                    if numbered_instructions:
                        zubereitung_lines = numbered_instructions
            
            # Formatieren und in extrahierte Daten einfügen
            extracted_data['ingredients'] = '\n'.join(zutaten_lines)
            extracted_data['instructions'] = '\n'.join(zubereitung_lines)
            
            # Sicherstellen, dass wir nicht den Titel in den Zutaten haben
            if extracted_data['title'] in extracted_data['ingredients']:
                extracted_data['ingredients'] = extracted_data['ingredients'].replace(extracted_data['title'], '').strip()
            
            # Sofern wir die Quelle erkannt haben, fügen wir sie hinzu
            if source_website:
                extracted_data['notes'] += f"Quelle: {source_website}\n"
            
            # Nährwerte
            if naehrwerte_lines:
                naehrwerte_text = ' '.join(naehrwerte_lines)
                
                # Kalorien
                kcal_match = re.search(r'kcal\s*(\d+)', naehrwerte_text)
                if kcal_match:
                    extracted_data['calories'] = int(kcal_match.group(1))
                
                # Fett
                fett_match = re.search(r'Fett\s*(\d+)g', naehrwerte_text)
                if fett_match:
                    extracted_data['fat'] = int(fett_match.group(1))
                
                # Kohlenhydrate
                carbs_match = re.search(r'Kohlenhydrate\s*(\d+)g', naehrwerte_text)
                if carbs_match:
                    extracted_data['carbs'] = int(carbs_match.group(1))
                
                # Eiweiß
                protein_match = re.search(r'Eiweiss\s*(\d+)g', naehrwerte_text)
                if protein_match:
                    extracted_data['protein'] = int(protein_match.group(1))
            
            # Zeitangaben
            if not extracted_data['prep_time']:
                for line in lines:
                    if "vorbereiten" in line.lower() or "vorbereitungszeit" in line.lower():
                        time_match = re.search(r'(\d+)\s*Min', line)
                        if time_match:
                            extracted_data['prep_time'] = int(time_match.group(1))
                            break
            
            if not extracted_data['cook_time']:
                for line in lines:
                    if "backen" in line.lower() or "kochen" in line.lower() or "garzeit" in line.lower():
                        time_match = re.search(r'(\d+)\s*Min', line)
                        if time_match:
                            extracted_data['cook_time'] = int(time_match.group(1))
                            break
        
        return extracted_data
    
    except Exception as e:
        print(f"Fehler bei der Datenextraktion: {str(e)}")
        return extracted_data

# Routen
@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "message": "Backend is running"}), 200

@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    
    # Überprüfung, ob Benutzername oder E-Mail bereits existieren
    if User.query.filter_by(username=data.get('username')).first():
        return jsonify({"error": "Benutzername bereits vergeben"}), 400
    
    if User.query.filter_by(email=data.get('email')).first():
        return jsonify({"error": "E-Mail-Adresse bereits registriert"}), 400
    
    # Neuen Benutzer erstellen
    user = User(
        username=data.get('username'),
        email=data.get('email')
    )
    user.set_password(data.get('password'))
    
    # Den ersten registrierten Benutzer zum Admin machen
    if User.query.count() == 0:
        user.is_admin = True
    
    # Benutzer in der Datenbank speichern
    db.session.add(user)
    db.session.commit()
    
    return jsonify({"message": "Benutzer erfolgreich registriert"}), 201

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    
    # Benutzer nach Benutzername suchen
    user = User.query.filter_by(username=data.get('username')).first()
    
    # Überprüfen, ob der Benutzer existiert und das Passwort korrekt ist
    if user and user.check_password(data.get('password')):
        login_user(user)
        return jsonify({
            "message": "Erfolgreich angemeldet",
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "is_admin": user.is_admin
            }
        }), 200
    
    return jsonify({"error": "Ungültiger Benutzername oder Passwort"}), 401

@app.route('/api/logout', methods=['POST'])
def logout():
    if current_user.is_authenticated:
        logout_user()
    return jsonify({"message": "Erfolgreich abgemeldet"}), 200

@app.route('/api/current_user', methods=['GET'])
def get_current_user():
    if current_user.is_authenticated:
        return jsonify({
            "user": {
                "id": current_user.id,
                "username": current_user.username,
                "email": current_user.email,
                "is_admin": current_user.is_admin
            }
        }), 200
    return jsonify({"error": "Nicht angemeldet"}), 401

# Benutzeradministration - Alle Benutzer anzeigen (nur für Admins)
@app.route('/api/admin/users', methods=['GET'])
@login_required
def get_all_users():
    if not current_user.is_admin:
        return jsonify({"error": "Zugriff verweigert"}), 403
    
    users = User.query.all()
    return jsonify({
        "users": [
            {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "is_admin": user.is_admin,
                "created_at": user.created_at.isoformat()
            } for user in users
        ]
    }), 200

# Benutzeradministration - Benutzer erstellen (nur für Admins)
@app.route('/api/admin/users', methods=['POST'])
@login_required
def create_user():
    if not current_user.is_admin:
        return jsonify({"error": "Zugriff verweigert"}), 403
    
    data = request.get_json()
    
    # Überprüfung, ob Benutzername oder E-Mail bereits existieren
    if User.query.filter_by(username=data.get('username')).first():
        return jsonify({"error": "Benutzername bereits vergeben"}), 400
    
    if User.query.filter_by(email=data.get('email')).first():
        return jsonify({"error": "E-Mail-Adresse bereits registriert"}), 400
    
    # Neuen Benutzer erstellen
    user = User(
        username=data.get('username'),
        email=data.get('email'),
        is_admin=data.get('is_admin', False)
    )
    user.set_password(data.get('password'))
    
    # Benutzer in der Datenbank speichern
    db.session.add(user)
    db.session.commit()
    
    return jsonify({
        "message": "Benutzer erfolgreich erstellt",
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "is_admin": user.is_admin
        }
    }), 201

# Benutzeradministration - Benutzer aktualisieren (nur für Admins)
@app.route('/api/admin/users/<int:user_id>', methods=['PUT'])
@login_required
def update_user(user_id):
    if not current_user.is_admin:
        return jsonify({"error": "Zugriff verweigert"}), 403
    
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "Benutzer nicht gefunden"}), 404
    
    data = request.get_json()
    
    # Username und E-Mail-Updates überprüfen, um Duplikate zu vermeiden
    if 'username' in data and data['username'] != user.username:
        if User.query.filter_by(username=data['username']).first():
            return jsonify({"error": "Benutzername bereits vergeben"}), 400
        user.username = data['username']
    
    if 'email' in data and data['email'] != user.email:
        if User.query.filter_by(email=data['email']).first():
            return jsonify({"error": "E-Mail-Adresse bereits registriert"}), 400
        user.email = data['email']
    
    # Passwort aktualisieren, wenn angegeben
    if 'password' in data and data['password']:
        user.set_password(data['password'])
    
    # Admin-Status aktualisieren
    if 'is_admin' in data:
        user.is_admin = data['is_admin']
    
    db.session.commit()
    
    return jsonify({
        "message": "Benutzer erfolgreich aktualisiert",
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "is_admin": user.is_admin
        }
    }), 200

# Benutzeradministration - Benutzer löschen (nur für Admins)
@app.route('/api/admin/users/<int:user_id>', methods=['DELETE'])
@login_required
def delete_user(user_id):
    if not current_user.is_admin:
        return jsonify({"error": "Zugriff verweigert"}), 403
    
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "Benutzer nicht gefunden"}), 404
    
    # Verhindere, dass Administratoren sich selbst löschen
    if user.id == current_user.id:
        return jsonify({"error": "Sie können Ihr eigenes Konto nicht löschen"}), 400
    
    db.session.delete(user)
    db.session.commit()
    
    return jsonify({"message": "Benutzer erfolgreich gelöscht"}), 200

# Route zum Hochladen von PDFs
@app.route('/api/recipes/upload', methods=['POST'])
@login_required
def

