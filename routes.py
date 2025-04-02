from flask import request, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from models import User
from app import db

def register_routes(app):
    # Route für die Benutzerregistrierung
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

    # Route für die Benutzeranmeldung
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

    # Route für die Benutzerabmeldung
    @app.route('/api/logout', methods=['POST'])
    def logout():
        if current_user.is_authenticated:
            logout_user()
        return jsonify({"message": "Erfolgreich abgemeldet"}), 200

    # Route, um den aktuellen Benutzer abzurufen
    @app.route('/api/current_user', methods=['GET'])
    @login_required
    def get_current_user():
        return jsonify({
            "user": {
                "id": current_user.id,
                "username": current_user.username,
                "email": current_user.email,
                "is_admin": current_user.is_admin
            }
        }), 200