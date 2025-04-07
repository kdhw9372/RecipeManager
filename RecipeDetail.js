import React, { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import axios from 'axios';
import './RecipeDetail.css';

function RecipeDetail({ apiUrl }) {
  const { id } = useParams();
  const [recipe, setRecipe] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selectedImage, setSelectedImage] = useState(null);

  useEffect(() => {
    const fetchRecipe = async () => {
      try {
        setLoading(true);
        const response = await axios.get(`${apiUrl}/recipes/${id}`, { withCredentials: true });
        
        // Überprüfen, ob die Antwort das erwartete Format hat
        if (response.data && response.data.recipe) {
          setRecipe(response.data.recipe);
          
          // Setze das Hauptbild als ausgewähltes Bild, falls vorhanden
          if (response.data.recipe.image_path) {
            setSelectedImage(response.data.recipe.image_path);
          } else if (response.data.recipe.images && response.data.recipe.images.length > 0) {
            setSelectedImage(response.data.recipe.images[0]);
          }
        } else {
          setError('Unerwartetes Antwortformat vom Server');
        }
      } catch (err) {
        console.error('Fehler beim Laden des Rezepts:', err);
        setError(`Fehler beim Laden des Rezepts: ${err.response?.data?.error || err.message}`);
      } finally {
        setLoading(false);
      }
    };

    fetchRecipe();
  }, [apiUrl, id]);

  const handleImageClick = (imagePath) => {
    setSelectedImage(imagePath);
  };

  if (loading) return <div className="loading">Rezept wird geladen...</div>;
  
  if (error) return (
    <div className="error-container">
      <h2>Ein Fehler ist aufgetreten</h2>
      <p>{error}</p>
      <Link to="/" className="back-link">Zurück zur Übersicht</Link>
    </div>
  );

  // Fallback für den Fall, dass recipe null ist
  if (!recipe) return (
    <div className="error-container">
      <h2>Rezept nicht gefunden</h2>
      <Link to="/" className="back-link">Zurück zur Übersicht</Link>
    </div>
  );

  // Sicherstellen, dass alle Eigenschaften vorhanden sind
  const title = recipe.title || 'Unbenanntes Rezept';
  const ingredients = recipe.ingredients || '';
  const instructions = recipe.instructions || '';
  const images = recipe.images || [];
  const mainImage = recipe.image_path || (images.length > 0 ? images[0] : null);
  
  // Formatierung von Nährwerten und Zeiten
  const formatTime = (minutes) => {
    if (!minutes || minutes <= 0) return 'Nicht angegeben';
    if (minutes < 60) return `${minutes} Minuten`;
    const hours = Math.floor(minutes / 60);
    const remainingMinutes = minutes % 60;
    return remainingMinutes > 0 
      ? `${hours} Stunde${hours > 1 ? 'n' : ''} ${remainingMinutes} Minuten` 
      : `${hours} Stunde${hours > 1 ? 'n' : ''}`;
  };

  return (
    <div className="recipe-detail">
      <h1 className="recipe-title">{title}</h1>
      
      <div className="recipe-content">
        <div className="recipe-images-container">
          {/* Hauptbild */}
          <div className="main-image-container">
            {selectedImage ? (
				<img 
    src={`/api/images/${selectedImage.split('/').pop()}`}  // Hier den Pfad anpassen
    alt={title} 
    className="main-image"
    onError={(e) => {
      console.error('Bildfehler:', e);
      e.target.src = '/placeholder-recipe.jpg';
      e.target.alt = 'Bild konnte nicht geladen werden';
    }}
  />
) : (
  <div className="no-image">Kein Bild verfügbar</div>
)}
              />
            ) : (
              <div className="no-image">Kein Bild verfügbar</div>
            )}
          </div>
          
          {/* Thumbnails der anderen Bilder */}
          {images.length > 1 && (
            <div className="image-thumbnails">
              {images.map((img, index) => (
                <img
                  key={index}
                  src={`${apiUrl}/uploads/${img}`}
                  alt={`${title} - Bild ${index + 1}`}
                  className={`thumbnail ${selectedImage === img ? 'active' : ''}`}
                  onClick={() => handleImageClick(img)}
                  onError={(e) => {
                    e.target.style.display = 'none'; // Verstecke fehlerhafte Thumbnails
                  }}
                />
              ))}
            </div>
          )}
        </div>
        
        <div className="recipe-info">
          {/* Metadaten */}
          <div className="recipe-metadata">
            {recipe.servings && (
              <div className="metadata-item">
                <span className="metadata-label">Portionen:</span>
                <span className="metadata-value">{recipe.servings}</span>
              </div>
            )}
            
            {recipe.prep_time > 0 && (
              <div className="metadata-item">
                <span className="metadata-label">Zubereitungszeit:</span>
                <span className="metadata-value">{formatTime(recipe.prep_time)}</span>
              </div>
            )}
            
            {recipe.cook_time > 0 && (
              <div className="metadata-item">
                <span className="metadata-label">Kochzeit:</span>
                <span className="metadata-value">{formatTime(recipe.cook_time)}</span>
              </div>
            )}
            
            {recipe.calories > 0 && (
              <div className="metadata-item">
                <span className="metadata-label">Kalorien:</span>
                <span className="metadata-value">{recipe.calories} kcal</span>
              </div>
            )}
            
            {/* Nährwerte */}
            {(recipe.protein > 0 || recipe.fat > 0 || recipe.carbs > 0) && (
              <div className="nutrition-info">
                <h3>Nährwerte pro Portion</h3>
                <div className="nutrition-grid">
                  {recipe.protein > 0 && (
                    <div className="nutrition-item">
                      <span className="nutrition-value">{recipe.protein}g</span>
                      <span className="nutrition-label">Eiweiß</span>
                    </div>
                  )}
                  
                  {recipe.fat > 0 && (
                    <div className="nutrition-item">
                      <span className="nutrition-value">{recipe.fat}g</span>
                      <span className="nutrition-label">Fett</span>
                    </div>
                  )}
                  
                  {recipe.carbs > 0 && (
                    <div className="nutrition-item">
                      <span className="nutrition-value">{recipe.carbs}g</span>
                      <span className="nutrition-label">Kohlenhydrate</span>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
          
          {/* Zutaten */}
          <div className="recipe-ingredients">
            <h2>Zutaten</h2>
            <div className="ingredients-content">
              {ingredients ? (
                <pre className="ingredients-text">{ingredients}</pre>
              ) : (
                <p className="empty-section">Keine Zutaten verfügbar.</p>
              )}
            </div>
          </div>
          
          {/* Anweisungen */}
          <div className="recipe-instructions">
            <h2>Zubereitung</h2>
            <div className="instructions-content">
              {instructions ? (
                <pre className="instructions-text">{instructions}</pre>
              ) : (
                <p className="empty-section">Keine Zubereitungsanweisungen verfügbar.</p>
              )}
            </div>
          </div>
        </div>
      </div>
      
      {/* Original-PDF-Download */}
      <div className="pdf-download">
        <a href={`${apiUrl}/recipes/${id}/pdf`} target="_blank" rel="noopener noreferrer" className="pdf-button">
          Original-PDF herunterladen
        </a>
      </div>
      
      <div className="navigation-links">
        <Link to="/" className="back-link">Zurück zur Übersicht</Link>
      </div>
    </div>
  );
}

export default RecipeDetail;