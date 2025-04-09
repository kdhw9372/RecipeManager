from flask import Blueprint, request, jsonify, send_file, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from werkzeug.utils import secure_filename
import os
import pdfplumber
from app import db
from app.models import Recipe, PDFProcessingQueue

pdf_bp = Blueprint('pdf', __name__)

@pdf_bp.route('/upload', methods=['POST'])
@jwt_required()
def upload_pdf():
    """PDF-Datei hochladen"""
    user_id = get_jwt_identity()
    
    if 'pdf' not in request.files:
        return jsonify({'error': 'Keine PDF-Datei gefunden'}), 400
    
    pdf_file = request.files['pdf']
    
    if pdf_file.filename == '':
        return jsonify({'error': 'Keine Datei ausgewählt'}), 400
    
    if not pdf_file.filename.endswith('.pdf'):
        return jsonify({'error': 'Datei muss im PDF-Format sein'}), 400
    
    filename = secure_filename(pdf_file.filename)
    pdf_storage_path = current_app.config.get('PDF_STORAGE_PATH')
    
    # Verzeichnis erstellen, falls es nicht existiert
    os.makedirs(pdf_storage_path, exist_ok=True)
    
    # Eindeutigen Dateinamen generieren
    import uuid
    unique_filename = f"{uuid.uuid4()}_{filename}"
    filepath = os.path.join(pdf_storage_path, unique_filename)
    
    # Datei speichern
    pdf_file.save(filepath)
    
    # PDF zur Verarbeitungswarteschlange hinzufügen
    queue_item = PDFProcessingQueue(
        user_id=user_id,
        filepath=filepath,
        original_filename=filename,
        status='pending'
    )
    
    db.session.add(queue_item)
    db.session.commit()
    
    # Einfachen Text aus dem PDF extrahieren für direkte Vorschau
    preview_text = ""
    try:
        with pdfplumber.open(filepath) as pdf:
            for i, page in enumerate(pdf.pages):
                if i < 2:  # Nur die ersten beiden Seiten für die Vorschau
                    page_text = page.extract_text() or ""
                    preview_text += page_text
                else:
                    break
    except Exception as e:
        # Bei Fehler leeren Vorschautext zurückgeben
        preview_text = ""
    
    return jsonify({
        'message': 'PDF erfolgreich hochgeladen',
        'queue_id': queue_item.id,
        'filepath': unique_filename,
        'preview_text': preview_text[:1000]  # Nur die ersten 1000 Zeichen
    }), 201

@pdf_bp.route('/<path:filename>', methods=['GET'])
@jwt_required()
def get_pdf(filename):
    """PDF-Datei herunterladen"""
    pdf_storage_path = current_app.config.get('PDF_STORAGE_PATH')
    filepath = os.path.join(pdf_storage_path, filename)
    
    if not os.path.exists(filepath):
        return jsonify({'error': 'PDF nicht gefunden'}), 404
    
    return send_file(filepath, as_attachment=True)