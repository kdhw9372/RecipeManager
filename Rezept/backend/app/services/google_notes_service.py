import os
import json
import pickle
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

class GoogleNotesService:
    """
    Service für die Integration mit Google Keep/Notes API.
    """
    SCOPES = ['https://www.googleapis.com/auth/keep']
    TOKEN_PATH = 'token.pickle'
    CREDENTIALS_PATH = '/app/credentials/google_credentials.json'
    
    def __init__(self):
        self.service = None
        
    def authenticate(self):
        """Google API Authentifizierung"""
        creds = None
        
        # Token aus Datei laden, falls vorhanden
        if os.path.exists(self.TOKEN_PATH):
            with open(self.TOKEN_PATH, 'rb') as token:
                creds = pickle.load(token)
        
        # Token erneuern, falls abgelaufen
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # Neue Authentifizierung durchführen
            flow = InstalledAppFlow.from_client_secrets_file(
                self.CREDENTIALS_PATH, self.SCOPES)
            creds = flow.run_local_server(port=0)
            
            # Token für zukünftige Verwendung speichern
            with open(self.TOKEN_PATH, 'wb') as token:
                pickle.dump(creds, token)
        
        # Google Keep API Service erstellen
        self.service = build('keep', 'v1', credentials=creds)
        return self.service
    
    def create_shopping_list(self, title, items):
        """
        Erstellt eine neue Einkaufsliste in Google Notizen
        
        Args:
            title (str): Titel der Einkaufsliste
            items (list): Liste der Einträge in der Form [{"name": "Zutat", "amount": "200", "unit": "g"}]
            
        Returns:
            str: ID der erstellten Notiz
        """
        if not self.service:
            self.authenticate()
            
        try:
            # Formatieren der Elemente für die Einkaufsliste
            list_items = []
            for item in items:
                # Formatierung des Textes (z.B. "200g Mehl")
                item_text = f"{item.get('amount', '')} {item.get('unit', '')} {item['name']}".strip()
                list_items.append({
                    'text': item_text,
                    'checked': False
                })
            
            # Neue Notiz erstellen
            note = {
                'title': title,
                'listContent': list_items
            }
            
            # API-Aufruf zum Erstellen der Notiz
            created_note = self.service.notes().create(body=note).execute()
            return created_note.get('id')
            
        except HttpError as error:
            print(f"Ein Fehler ist aufgetreten: {error}")
            return None
    
    def update_shopping_list(self, note_id, new_items):
        """
        Aktualisiert eine bestehende Einkaufsliste in Google Notizen
        
        Args:
            note_id (str): ID der zu aktualisierenden Notiz
            new_items (list): Liste der neuen/zusätzlichen Einträge
            
        Returns:
            bool: True bei Erfolg, False bei Fehler
        """
        if not self.service:
            self.authenticate()
            
        try:
            # Bestehende Notiz abrufen
            note = self.service.notes().get(noteId=note_id).execute()
            
            # Bestehende Liste abrufen
            existing_items = note.get('listContent', [])
            existing_texts = [item['text'] for item in existing_items]
            
            # Neue Einträge hinzufügen, wenn sie noch nicht existieren
            for item in new_items:
                item_text = f"{item.get('amount', '')} {item.get('unit', '')} {item['name']}".strip()
                if item_text not in existing_texts:
                    existing_items.append({
                        'text': item_text,
                        'checked': False
                    })
            
            # Notiz aktualisieren
            note['listContent'] = existing_items
            self.service.notes().update(noteId=note_id, body=note).execute()
            return True
            
        except HttpError as error:
            print(f"Ein Fehler ist aufgetreten: {error}")
            return False