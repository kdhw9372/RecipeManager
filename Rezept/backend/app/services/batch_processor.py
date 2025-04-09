import os
import shutil
import logging
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor
from app import db, celery
from app.models import PDFProcessingQueue, ProcessingBatch
from app.services.pdf_processing_service import PDFProcessingService

logger = logging.getLogger(__name__)

class BatchProcessor:
    """Service zum effizienten Batch-Processing großer PDF-Mengen"""
    
    def __init__(self, 
                 storage_path='/app/pdf_storage', 
                 batch_size=100, 
                 max_workers=4,
                 dpi=200):  # Niedrigere DPI für schnellere Verarbeitung
        self.storage_path = storage_path
        self.batch_size = batch_size
        self.max_workers = max_workers
        self.dpi = dpi
        self.pdf_service = PDFProcessingService(storage_path, max_workers, dpi)
    
    def create_batch(self, files, name=None):
        """Erstellt einen neuen Batch aus einer Liste von Dateien"""
        if not name:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            name = f"Batch_{timestamp}"
        
        # Batch in der Datenbank erstellen
        batch = ProcessingBatch(
            name=name,
            total_files=len(files),
            processed_files=0,
            status='pending'
        )
        db.session.add(batch)
        db.session.flush()
        
        # Batch-Verzeichnis erstellen
        batch_dir = os.path.join(self.storage_path, f"batch_{batch.id}")
        os.makedirs(batch_dir, exist_ok=True)
        
        # Dateien ins Batch-Verzeichnis kopieren und zur Verarbeitungswarteschlange hinzufügen
        for file_path in files:
            if os.path.exists(file_path) and file_path.lower().endswith('.pdf'):
                filename = os.path.basename(file_path)
                dest_path = os.path.join(batch_dir, filename)
                
                # Datei kopieren
                shutil.copy2(file_path, dest_path)
                
                # Eintrag in der Warteschlange erstellen
                queue_item = PDFProcessingQueue(
                    file_path=dest_path,
                    original_filename=filename,
                    status='pending',
                    batch_id=batch.id
                )
                db.session.add(queue_item)
        
        # Batch starten
        batch.status = 'processing'
        db.session.commit()
        
        # Asynchrone Verarbeitung starten
        process_batch.delay(batch.id)
        
        return batch
    
    def process_batch_files(self, batch_id):
        """Verarbeitet alle Dateien eines Batches"""
        batch = ProcessingBatch.query.get(batch_id)
        if not batch:
            logger.error(f"Batch {batch_id} nicht gefunden")
            return
        
        # Alle ausstehenden Dateien im Batch abrufen
        queue_items = PDFProcessingQueue.query.filter_by(
            batch_id=batch_id,
            status='pending'
        ).limit(self.batch_size).all()
        
        if not queue_items:
            # Prüfen, ob noch verarbeitete Dateien übrig sind
            remaining = PDFProcessingQueue.query.filter_by(
                batch_id=batch_id,
                status='processing'
            ).count()
            
            if remaining == 0:
                # Alle Dateien wurden verarbeitet
                batch.status = 'completed'
                batch.completed_at = datetime.now()
                db.session.commit()
            
            return
        
        # Status aktualisieren
        for item in queue_items:
            item.status = 'processing'
        db.session.commit()
        
        # Dateien parallel verarbeiten
        file_paths = [item.file_path for item in queue_items]
        item_ids = [item.id for item in queue_items]
        
        with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
            for i, result in enumerate(executor.map(self._process_single_file, file_paths)):
                item_id = item_ids[i]
                queue_item = PDFProcessingQueue.query.get(item_id)
                
                if result.get('error'):
                    queue_item.status = 'error'
                    queue_item.error_message = result['error']
                else:
                    queue_item.status = 'completed'
                    batch.processed_files += 1
                
                db.session.commit()
        
        # Nächsten Batch starten
        process_batch.delay(batch_id)
    
    def _process_single_file(self, file_path):
        """Verarbeitet eine einzelne PDF-Datei"""
        try:
            return self.pdf_service.extract_recipe_from_pdf(file_path)
        except Exception as e:
            logger.error(f"Fehler bei der Verarbeitung von {file_path}: {str(e)}")
            return {'error': str(e)}

@celery.task
def process_batch(batch_id):
    """Celery-Task zum Verarbeiten eines Batches"""
    storage_path = os.environ.get('PDF_STORAGE_PATH', '/app/pdf_storage')
    processor = BatchProcessor(storage_path)
    processor.process_batch_files(batch_id)