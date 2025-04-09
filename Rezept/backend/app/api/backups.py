from flask import Blueprint, request, jsonify, send_file, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db
from app.models import Backup, User
from app.services.backup_service import BackupService, create_automatic_backup
import os

backups_bp = Blueprint('backups', __name__)

@backups_bp.route('', methods=['GET'])
@jwt_required()
def get_backups():
    """Liste aller Backups abrufen"""
    # Nur Administratoren dürfen Backups verwalten
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    
    if not user or not user.is_admin:
        return jsonify({'error': 'Nicht autorisiert'}), 403
    
    backups = Backup.query.order_by(Backup.created_at.desc()).all()
    
    result = []
    for backup in backups:
        result.append({
            'id': backup.id,
            'filename': backup.filename,
            'size': backup.size,
            'created_at': backup.created_at.isoformat()
        })
    
    return jsonify(result)

@backups_bp.route('/create', methods=['POST'])
@jwt_required()
def create_backup():
    """Neues Backup erstellen"""
    # Nur Administratoren dürfen Backups erstellen
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    
    if not user or not user.is_admin:
        return jsonify({'error': 'Nicht autorisiert'}), 403
    
    data = request.get_json()
    backup_type = data.get('type', 'full')  # 'full', 'db', 'pdf'
    
    service = BackupService()
    
    if backup_type == 'full':
        result = service.create_full_backup()
    elif backup_type == 'db':
        result = service.create_db_backup()
    elif backup_type == 'pdf':
        result = service.create_pdf_backup()
    else:
        return jsonify({'error': 'Ungültiger Backup-Typ'}), 400
    
    if result['success']:
        return jsonify({
            'message': f"Backup wurde erfolgreich erstellt: {result['filename']}",
            'filename': result['filename'],
            'size': result['size']
        })
    else:
        return jsonify({'error': result['error']}), 500

@backups_bp.route('/restore/<int:backup_id>', methods=['POST'])
@jwt_required()
def restore_backup(backup_id):
    """Backup wiederherstellen"""
    # Nur Administratoren dürfen Backups wiederherstellen
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    
    if not user or not user.is_admin:
        return jsonify({'error': 'Nicht autorisiert'}), 403
    
    backup = Backup.query.get_or_404(backup_id)
    
    service = BackupService()
    
    # Backup-Typ basierend auf Dateinamen bestimmen
    if backup.filename.startswith('full_backup_'):
        result = service.restore_full_backup(backup.filename)
    elif backup.filename.startswith('db_backup_'):
        result = service.restore_db_backup(backup.filename)
    elif backup.filename.startswith('pdf_backup_'):
        result = service.restore_pdf_backup(backup.filename)
    else:
        return jsonify({'error': 'Unbekannter Backup-Typ'}), 400
    
    if result['success']:
        return jsonify({'message': result['message']})
    else:
        return jsonify({'error': result['error']}), 500

@backups_bp.route('/download/<int:backup_id>', methods=['GET'])
@jwt_required()
def download_backup(backup_id):
    """Backup-Datei herunterladen"""
    # Nur Administratoren dürfen Backups herunterladen
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    
    if not user or not user.is_admin:
        return jsonify({'error': 'Nicht autorisiert'}), 403
    
    backup = Backup.query.get_or_404(backup_id)
    
    backup_dir = current_app.config.get('BACKUP_DIR', '/app/backups')
    filepath = os.path.join(backup_dir, backup.filename)
    
    if not os.path.exists(filepath):
        return jsonify({'error': 'Backup-Datei nicht gefunden'}), 404
    
    return send_file(filepath, as_attachment=True)

@backups_bp.route('/<int:backup_id>', methods=['DELETE'])
@jwt_required()
def delete_backup(backup_id):
    """Backup löschen"""
    # Nur Administratoren dürfen Backups löschen
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    
    if not user or not user.is_admin:
        return jsonify({'error': 'Nicht autorisiert'}), 403
    
    backup = Backup.query.get_or_404(backup_id)
    
    backup_dir = current_app.config.get('BACKUP_DIR', '/app/backups')
    filepath = os.path.join(backup_dir, backup.filename)
    
    # Datei löschen, falls vorhanden
    if os.path.exists(filepath):
        os.remove(filepath)
    
    # Datenbankeintrag löschen
    db.session.delete(backup)
    db.session.commit()
    
    return jsonify({'message': f"Backup {backup.filename} wurde gelöscht"})

@backups_bp.route('/cleanup', methods=['POST'])
@jwt_required()
def cleanup_backups():
    """Alte Backups aufräumen"""
    # Nur Administratoren dürfen Backups aufräumen
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    
    if not user or not user.is_admin:
        return jsonify({'error': 'Nicht autorisiert'}), 403
    
    data = request.get_json()
    max_age_days = data.get('max_age_days', 30)
    max_backups = data.get('max_backups', 10)
    
    service = BackupService()
    result = service.cleanup_old_backups(max_age_days, max_backups)
    
    if result['success']:
        return jsonify({'message': result['message']})
    else:
        return jsonify({'error': result['error']}), 500