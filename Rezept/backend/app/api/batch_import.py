from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from werkzeug.utils import secure_filename
import os
from app import db
from app.models import User, ProcessingBatch, PDFProcessingQueue
from app.services.batch_processor import BatchProcessor

batch_import_bp = Blueprint('batch_import', __name__)

@batch_import_bp.route('/upload', methods=['POST'])
@jwt_required()
def upload_batch():
    """Upload mehrerer PDF-Dateien auf einmal"""
    # Nur Administratoren dürfen Batch-Uploads durchführen
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    
    if not user or not user.is_admin:
        return jsonify({'error': 'Nicht autorisiert'}), 403
    
    if 'files[]' not in request.files:
        return jsonify({'error': 'Keine Dateien gefunden'}), 400
    
    files = request.files.getlist('files[]')
    
    if not files or len(files) == 0:
        return jsonify({'error': 'Keine Dateien gefunden'}), 400
    
    # Batch-Name (optional)
    batch_name = request.form.get('name', None)
    
    # Temporäre Speicherung der hochgeladenen Dateien
    storage_path = current_app.config.get('PDF_STORAGE_PATH', '/app/pdf_storage')
    temp_dir = os.path.join(storage_path, 'temp_uploads')
    os.makedirs(temp_dir, exist_ok=True)
    
    file_paths = []
    
    for file in files:
        if file.filename == '':
            continue
        
        if file and file.filename.lower().endswith('.pdf'):
            filename = secure_filename(file.filename)
            file_path = os.path.join(temp_dir, filename)
            file.save(file_path)
            file_paths.append(file_path)
    
    if not file_paths:
        return jsonify({'error': 'Keine gültigen PDF-Dateien gefunden'}), 400
    
    # Batch-Processor initialisieren und Batch erstellen
    processor = BatchProcessor(storage_path)
    batch = processor.create_batch(file_paths, batch_name)
    
    return jsonify({
        'message': f'{len(file_paths)} Dateien wurden hochgeladen und werden verarbeitet',
        'batch_id': batch.id,
        'batch_name': batch.name,
        'total_files': batch.total_files
    })

@batch_import_bp.route('/import-directory', methods=['POST'])
@jwt_required()
def import_from_directory():
    """PDFs aus einem Verzeichnis auf dem Server importieren"""
    # Nur Administratoren dürfen Directory-Imports durchführen
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    
    if not user or not user.is_admin:
        return jsonify({'error': 'Nicht autorisiert'}), 403
    
    data = request.get_json()
    
    if 'directory' not in data:
        return jsonify({'error': 'Kein Verzeichnis angegeben'}), 400
    
    directory = data['directory']
    batch_name = data.get('name', None)
    
    # Prüfen, ob das Verzeichnis existiert
    if not os.path.exists(directory) or not os.path.isdir(directory):
        return jsonify({'error': 'Verzeichnis nicht gefunden oder kein Verzeichnis'}), 400
    
    # PDF-Dateien im Verzeichnis finden
    file_paths = []
    for root, _, files in os.walk(directory):
        for file in files:
            if file.lower().endswith('.pdf'):
                file_path = os.path.join(root, file)
                file_paths.append(file_path)
    
    if not file_paths:
        return jsonify({'error': 'Keine PDF-Dateien im angegebenen Verzeichnis gefunden'}), 400
    
    # Batch-Processor initialisieren und Batch erstellen
    storage_path = current_app.config.get('PDF_STORAGE_PATH', '/app/pdf_storage')
    processor = BatchProcessor(storage_path)
    batch = processor.create_batch(file_paths, batch_name)
    
    return jsonify({
        'message': f'{len(file_paths)} Dateien wurden gefunden und werden verarbeitet',
        'batch_id': batch.id,
        'batch_name': batch.name,
        'total_files': batch.total_files
    })

@batch_import_bp.route('/status/<int:batch_id>', methods=['GET'])
@jwt_required()
def get_batch_status(batch_id):
    """Status eines Batch-Imports abrufen"""
    batch = ProcessingBatch.query.get_or_404(batch_id)
    
    # Statistik zu Fehlern abrufen
    error_count = PDFProcessingQueue.query.filter_by(
        batch_id=batch_id,
        status='error'
    ).count()
    
    return jsonify({
        'id': batch.id,
        'name': batch.name,
        'total_files': batch.total_files,
        'processed_files': batch.processed_files,
        'error_files': error_count,
        'status': batch.status,
        'created_at': batch.created_at.isoformat(),
        'completed_at': batch.completed_at.isoformat() if batch.completed_at else None,
        'progress': round((batch.processed_files / batch.total_files) * 100, 2) if batch.total_files > 0 else 0
    })

@batch_import_bp.route('/errors/<int:batch_id>', methods=['GET'])
@jwt_required()
def get_batch_errors(batch_id):
    """Fehler eines Batch-Imports abrufen"""
    ProcessingBatch.query.get_or_404(batch_id)
    
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    
    errors = PDFProcessingQueue.query.filter_by(
        batch_id=batch_id,
        status='error'
    ).paginate(page=page, per_page=per_page)
    
    return jsonify({
        'items': [{
            'id': item.id,
            'filename': item.original_filename,
            'error_message': item.error_message,
            'created_at': item.created_at.isoformat()
        } for item in errors.items],
        'total': errors.total,
        'pages': errors.pages,
        'page': page
    })