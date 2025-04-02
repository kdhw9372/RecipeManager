import React, { useState } from 'react';
import axios from 'axios';
import './RecipeUpload.css';

function RecipeUpload({ apiUrl }) {
  const [files, setFiles] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState({});
  const [uploadResults, setUploadResults] = useState([]);
  const [error, setError] = useState(null);

  const handleFileChange = (e) => {
    // Nur PDF-Dateien akzeptieren
    const selectedFiles = Array.from(e.target.files).filter(
      file => file.type === 'application/pdf'
    );
    
    if (selectedFiles.length !== e.target.files.length) {
      setError('Nur PDF-Dateien werden unterstützt. Nicht-PDF-Dateien wurden ignoriert.');
    }
    
    if (selectedFiles.length > 0) {
      setFiles(currentFiles => [...currentFiles, ...selectedFiles]);
      setError(null);
    }
  };

  const removeFile = (index) => {
    setFiles(files.filter((_, i) => i !== index));
  };

  const uploadFile = async (file, index) => {
    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await axios.post(`${apiUrl}/recipes/upload`, formData, {
        headers: {
          'Content-Type': 'multipart/form-data'
        },
        withCredentials: true,
        onUploadProgress: (progressEvent) => {
          const percentCompleted = Math.round((progressEvent.loaded * 100) / progressEvent.total);
          setUploadProgress(prev => ({
            ...prev,
            [index]: percentCompleted
          }));
        }
      });

      return {
        success: true,
        filename: file.name,
        data: response.data
      };
    } catch (err) {
      return {
        success: false,
        filename: file.name,
        error: err.response?.data?.error || 'Upload fehlgeschlagen'
      };
    }
  };

  const handleUploadAll = async () => {
    if (files.length === 0) {
      setError('Bitte füge zuerst PDF-Dateien hinzu.');
      return;
    }

    setUploading(true);
    setError(null);
    setUploadResults([]);
    setUploadProgress({});

    const results = [];

    // Dateien nacheinander hochladen
    for (let i = 0; i < files.length; i++) {
      const result = await uploadFile(files[i], i);
      results.push(result);
    }

    setUploadResults(results);
    setFiles([]);
    setUploading(false);
  };

  return (
    <div className="recipe-upload">
      <h2>Rezepte hochladen</h2>
      
      <div className="upload-container">
        <div className="file-input-container">
          <input 
            type="file" 
            onChange={handleFileChange} 
            accept=".pdf"
            multiple
            id="recipe-file-input"
            className="file-input"
          />
          <label htmlFor="recipe-file-input" className="file-input-label">
            {files.length > 0 
              ? `${files.length} Dateien ausgewählt` 
              : 'PDF-Dateien auswählen'}
          </label>
        </div>
        
        <button 
          onClick={handleUploadAll} 
          disabled={files.length === 0 || uploading}
          className="upload-button"
        >
          {uploading ? 'Wird hochgeladen...' : 'Alle Dateien hochladen'}
        </button>
      </div>
      
      {error && <div className="error-message">{error}</div>}
      
      {files.length > 0 && (
        <div className="file-list">
          <h3>Ausgewählte Dateien ({files.length})</h3>
          <ul>
            {files.map((file, index) => (
              <li key={index} className="file-item">
                <div className="file-info">
                  <span className="file-name">{file.name}</span>
                  <span className="file-size">({(file.size / 1024).toFixed(1)} KB)</span>
                </div>
                {uploadProgress[index] !== undefined && (
                  <div className="progress-bar-container">
                    <div 
                      className="progress-bar" 
                      style={{ width: `${uploadProgress[index]}%` }}
                    />
                    <span className="progress-text">{uploadProgress[index]}%</span>
                  </div>
                )}
                <button 
                  className="remove-button" 
                  onClick={() => removeFile(index)}
                  disabled={uploading}
                >
                  Entfernen
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
      
      {uploadResults.length > 0 && (
        <div className="upload-results">
          <h3>Upload-Ergebnisse</h3>
          <ul>
            {uploadResults.map((result, index) => (
              <li key={index} className={`result-item ${result.success ? 'success' : 'error'}`}>
                <div className="result-header">
                  <span className="result-filename">{result.filename}</span>
                  <span className="result-status">
                    {result.success ? 'Erfolgreich' : 'Fehler'}
                  </span>
                </div>
                {result.success ? (
                  <div className="result-data">
                    <p><strong>Titel:</strong> {result.data.extracted_data.title}</p>
                    <button 
                      className="toggle-details-button"
                      onClick={() => {
                        const detailsEl = document.getElementById(`details-${index}`);
                        if (detailsEl) {
                          detailsEl.style.display = detailsEl.style.display === 'none' ? 'block' : 'none';
                        }
                      }}
                    >
                      Details anzeigen/ausblenden
                    </button>
                    <div id={`details-${index}`} className="details" style={{ display: 'none' }}>
                      <div className="extracted-section">
                        <h5>Zutaten:</h5>
                        <pre>{result.data.extracted_data.ingredients}</pre>
                      </div>
                      <div className="extracted-section">
                        <h5>Zubereitung:</h5>
                        <pre>{result.data.extracted_data.instructions}</pre>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="result-error">
                    <p>{result.error}</p>
                  </div>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export default RecipeUpload;