import os
import datetime
import subprocess
import shutil
import tarfile
import json
from app import db, celery
from app.models import Backup
from sqlalchemy import text
from celery.schedules import crontab

class BackupService:
    def __init__(self, db_host='db', db_port='5432', db_name='recipe_db', 
                 db_user='recipe_user', db_password='recipe_password',
                 backup_dir='/app/backups', pdf_dir='/app/pdf_storage'):
        self.db_host = db_host
        self.db_port = db_port
        self.db_name = db_name
        self.db_user = db_user
        self.db_password = db_password
        self.backup_dir = backup_dir
        self.pdf_dir = pdf_dir
        
        # Backup-Verzeichnis erstellen, falls es nicht existiert
        os.makedirs(self.backup_dir, exist_ok=True)
    
    def create_db_backup(self):
        """Erstellt ein Backup der PostgreSQL-Datenbank"""
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"db_backup_{timestamp}.sql"
        filepath = os.path.join(self.backup_dir, filename)
        
        # pg_dump ausführen
        command = [
            'pg_dump',
            f'--host={self.db_host}',
            f'--port={self.db_port}',
            f'--username={self.db_user}',
            f'--format=c',  # Custom format (komprimiert)
            f'--file={filepath}',
            self.db_name
        ]
        
        # Umgebungsvariable für Passwort setzen
        env = os.environ.copy()
        env['PGPASSWORD'] = self.db_password
        
        try:
            result = subprocess.run(command, env=env, check=True, capture_output=True)
            
            # Größe der Backup-Datei ermitteln
            size = os.path.getsize(filepath)
            
            # Backup in der Datenbank registrieren
            backup = Backup(filename=filename, size=size)
            db.session.add(backup)
            db.session.commit()
            
            return {
                'success': True,
                'filename': filename,
                'size': size,
                'path': filepath
            }
        except subprocess.CalledProcessError as e:
            return {
                'success': False,
                'error': f"Fehler beim Erstellen des Datenbank-Backups: {e.stderr.decode('utf-8')}"
            }
    
    def create_pdf_backup(self):
        """Erstellt ein Backup der PDF-Dateien"""
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"pdf_backup_{timestamp}.tar.gz"
        filepath = os.path.join(self.backup_dir, filename)
        
        try:
            # TAR-Archiv erstellen
            with tarfile.open(filepath, "w:gz") as tar:
                tar.add(self.pdf_dir, arcname=os.path.basename(self.pdf_dir))
            
            # Größe der Backup-Datei ermitteln
            size = os.path.getsize(filepath)
            
            # Backup in der Datenbank registrieren
            backup = Backup(filename=filename, size=size)
            db.session.add(backup)
            db.session.commit()
            
            return {
                'success': True,
                'filename': filename,
                'size': size,
                'path': filepath
            }
        except Exception as e:
            return {
                'success': False,
                'error': f"Fehler beim Erstellen des PDF-Backups: {str(e)}"
            }
    
    def create_full_backup(self):
        """Erstellt ein vollständiges Backup (Datenbank + PDFs)"""
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Temporäres Verzeichnis für das vollständige Backup
        temp_dir = os.path.join(self.backup_dir, f"temp_backup_{timestamp}")
        os.makedirs(temp_dir, exist_ok=True)
        
        try:
            # Datenbank-Backup erstellen
            db_result = self.create_db_backup()
            if not db_result['success']:
                raise Exception(db_result['error'])
            
            # PDF-Backup erstellen
            pdf_result = self.create_pdf_backup()
            if not pdf_result['success']:
                raise Exception(pdf_result['error'])
            
            # Backup-Metadaten
            metadata = {
                'timestamp': timestamp,
                'database': db_result['filename'],
                'pdfs': pdf_result['filename'],
                'version': '1.0'
            }
            
            # Metadaten-Datei erstellen
            metadata_file = os.path.join(temp_dir, 'backup_metadata.json')
            with open(metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)
            
            # Dateien ins temporäre Verzeichnis kopieren
            shutil.copy(os.path.join(self.backup_dir, db_result['filename']), temp_dir)
            shutil.copy(os.path.join(self.backup_dir, pdf_result['filename']), temp_dir)
            
            # Vollständiges Backup-Archiv erstellen
            full_backup_filename = f"full_backup_{timestamp}.tar.gz"
            full_backup_filepath = os.path.join(self.backup_dir, full_backup_filename)
            
            with tarfile.open(full_backup_filepath, "w:gz") as tar:
                tar.add(temp_dir, arcname=f"backup_{timestamp}")
            
            # Größe der Backup-Datei ermitteln
            size = os.path.getsize(full_backup_filepath)
            
            # Backup in der Datenbank registrieren
            backup = Backup(filename=full_backup_filename, size=size)
            db.session.add(backup)
            db.session.commit()
            
            # Temporäres Verzeichnis aufräumen
            shutil.rmtree(temp_dir)
            
            # Einzelne Backup-Dateien löschen (optional, da sie im vollständigen Backup enthalten sind)
            os.remove(os.path.join(self.backup_dir, db_result['filename']))
            os.remove(os.path.join(self.backup_dir, pdf_result['filename']))
            
            return {
                'success': True,
                'filename': full_backup_filename,
                'size': size,
                'path': full_backup_filepath
            }
        except Exception as e:
            # Aufräumen bei Fehler
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            
            return {
                'success': False,
                'error': f"Fehler beim Erstellen des vollständigen Backups: {str(e)}"
            }
    
    def restore_db_backup(self, filename):
        """Stellt ein Datenbank-Backup wieder her"""
        filepath = os.path.join(self.backup_dir, filename)
        
        if not os.path.exists(filepath):
            return {
                'success': False,
                'error': f"Backup-Datei {filename} nicht gefunden"
            }
        
        # pg_restore ausführen
        command = [
            'pg_restore',
            f'--host={self.db_host}',
            f'--port={self.db_port}',
            f'--username={self.db_user}',
            '--clean',  # Bestehende Daten löschen
            '--if-exists',  # Fehler vermeiden, wenn Objekte nicht existieren
            f'--dbname={self.db_name}',
            filepath
        ]
        
        # Umgebungsvariable für Passwort setzen
        env = os.environ.copy()
        env['PGPASSWORD'] = self.db_password
        
        try:
            result = subprocess.run(command, env=env, check=True, capture_output=True)
            return {
                'success': True,
                'message': 'Datenbank-Backup wurde erfolgreich wiederhergestellt'
            }
        except subprocess.CalledProcessError as e:
            return {
                'success': False,
                'error': f"Fehler beim Wiederherstellen des Datenbank-Backups: {e.stderr.decode('utf-8')}"
            }
    
    def restore_pdf_backup(self, filename):
        """Stellt ein PDF-Backup wieder her"""
        filepath = os.path.join(self.backup_dir, filename)
        
        if not os.path.exists(filepath):
            return {
                'success': False,
                'error': f"Backup-Datei {filename} nicht gefunden"
            }
        
        try:
            # Bestehende PDF-Dateien sichern
            timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            pdf_backup = f"{self.pdf_dir}_backup_{timestamp}"
            if os.path.exists(self.pdf_dir):
                shutil.move(self.pdf_dir, pdf_backup)
            
            # PDF-Verzeichnis neu erstellen
            os.makedirs(self.pdf_dir, exist_ok=True)
            
            # TAR-Archiv extrahieren
            with tarfile.open(filepath, "r:gz") as tar:
                tar.extractall(path=os.path.dirname(self.pdf_dir))
            
            return {
                'success': True,
                'message': 'PDF-Backup wurde erfolgreich wiederhergestellt'
            }
        except Exception as e:
            # Bei Fehler die Sicherung wiederherstellen
            if os.path.exists(pdf_backup):
                if os.path.exists(self.pdf_dir):
                    shutil.rmtree(self.pdf_dir)
                shutil.move(pdf_backup, self.pdf_dir)
            
            return {
                'success': False,
                'error': f"Fehler beim Wiederherstellen des PDF-Backups: {str(e)}"
            }
    
    def restore_full_backup(self, filename):
        """Stellt ein vollständiges Backup wieder her"""
        filepath = os.path.join(self.backup_dir, filename)
        
        if not os.path.exists(filepath):
            return {
                'success': False,
                'error': f"Backup-Datei {filename} nicht gefunden"
            }
        
        # Temporäres Verzeichnis für die Extraktion
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        temp_dir = os.path.join(self.backup_dir, f"temp_restore_{timestamp}")
        os.makedirs(temp_dir, exist_ok=True)
        
        try:
            # TAR-Archiv extrahieren
            with tarfile.open(filepath, "r:gz") as tar:
                tar.extractall(path=temp_dir)
            
            # Metadaten-Datei finden
            metadata_file = None
            for root, dirs, files in os.walk(temp_dir):
                if 'backup_metadata.json' in files:
                    metadata_file = os.path.join(root, 'backup_metadata.json')
                    break
            
            if not metadata_file:
                raise Exception("Keine Metadaten-Datei im Backup gefunden")
            
            # Metadaten lesen
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)
            
            # Pfad zum Backup-Verzeichnis bestimmen
            backup_dir = os.path.dirname(metadata_file)
            
            # Datenbank-Backup wiederherstellen
            db_backup_file = os.path.join(backup_dir, metadata['database'])
            if os.path.exists(db_backup_file):
                db_result = self.restore_db_backup(metadata['database'])
                if not db_result['success']:
                    raise Exception(db_result['error'])
            else:
                raise Exception(f"Datenbank-Backup {metadata['database']} nicht gefunden")
            
            # PDF-Backup wiederherstellen
            pdf_backup_file = os.path.join(backup_dir, metadata['pdfs'])
            if os.path.exists(pdf_backup_file):
                pdf_result = self.restore_pdf_backup(metadata['pdfs'])
                if not pdf_result['success']:
                    raise Exception(pdf_result['error'])
            else:
                raise Exception(f"PDF-Backup {metadata['pdfs']} nicht gefunden")
            
            # Temporäres Verzeichnis aufräumen
            shutil.rmtree(temp_dir)
            
            return {
                'success': True,
                'message': 'Vollständiges Backup wurde erfolgreich wiederhergestellt'
            }
        except Exception as e:
            # Aufräumen bei Fehler
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            
            return {
                'success': False,
                'error': f"Fehler beim Wiederherstellen des vollständigen Backups: {str(e)}"
            }
    
    def cleanup_old_backups(self, max_age_days=30, max_backups=10):
        """Löscht alte Backups basierend auf Alter und Anzahl"""
        try:
            # Alte Backups basierend auf Alter löschen
            cutoff_date = datetime.datetime.now() - datetime.timedelta(days=max_age_days)
            old_backups = Backup.query.filter(Backup.created_at < cutoff_date).all()
            
            for backup in old_backups:
                filepath = os.path.join(self.backup_dir, backup.filename)
                if os.path.exists(filepath):
                    os.remove(filepath)
                db.session.delete(backup)
            
            # Backups behalten, wenn zu viele vorhanden sind
            backups = Backup.query.order_by(Backup.created_at.desc()).all()
            if len(backups) > max_backups:
                for backup in backups[max_backups:]:
                    filepath = os.path.join(self.backup_dir, backup.filename)
                    if os.path.exists(filepath):
                        os.remove(filepath)
                    db.session.delete(backup)
            
            db.session.commit()
            
            return {
                'success': True,
                'message': f"Alte Backups wurden aufgeräumt. {len(old_backups)} basierend auf Alter, "
                          f"{max(0, len(backups) - max_backups)} basierend auf Anzahl."
            }
        except Exception as e:
            return {
                'success': False,
                'error': f"Fehler beim Aufräumen alter Backups: {str(e)}"
            }

# Celery-Aufgabe für automatische Backups
@celery.task
def create_automatic_backup():
    """Erstellt ein automatisches Backup via Celery-Task"""
    service = BackupService()
    result = service.create_full_backup()
    
    if result['success']:
        # Alte Backups aufräumen
        service.cleanup_old_backups()
    
    return result

# Celery-Aufgabe für inkrementelle Backups (nur Datenbank)
@celery.task
def create_incremental_backup():
    """Erstellt ein inkrementelles Backup (nur Datenbank)"""
    service = BackupService()
    return service.create_db_backup()

# Celery Beat-Konfiguration für geplante Backups
@celery.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    # Tägliches inkrementelles Backup um 3:00 Uhr
    sender.add_periodic_task(
        crontab(hour=3, minute=0),
        create_incremental_backup.s(),
        name='daily-incremental-backup'
    )
    
    # Wöchentliches vollständiges Backup am Sonntag um 2:00 Uhr
    sender.add_periodic_task(
        crontab(day_of_week=0, hour=2, minute=0),
        create_automatic_backup.s(),
        name='weekly-full-backup'
    )