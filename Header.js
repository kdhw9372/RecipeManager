import React from 'react';
import { Link, useNavigate } from 'react-router-dom';
import axios from 'axios';

function Header({ user, setUser, apiUrl }) {
  const navigate = useNavigate();

  const handleLogout = async () => {
    try {
      console.log("Logout wird versucht...");
      const response = await axios.post(`${apiUrl}/logout`, {}, { 
        withCredentials: true,
        headers: {
          'Content-Type': 'application/json'
        }
      });
      console.log("Logout-Antwort:", response);
      setUser(null);
      navigate('/login');
    } catch (error) {
      console.error('Abmeldung fehlgeschlagen', error);
      // Auch bei Fehler ausloggen im Frontend
      setUser(null);
      navigate('/login');
    }
  };

  return (
    <header>
      <nav>
        <div className="logo">Rezepte-App</div>
        <div className="nav-links">
          {user ? (
            <>
              <Link to="/">Home</Link>
              <Link to="/upload">Rezept hochladen</Link>
              {user.is_admin && <Link to="/admin">Admin-Dashboard</Link>}
              <button onClick={handleLogout}>Abmelden</button>
            </>
          ) : (
            <>
              <Link to="/login">Anmelden</Link>
              <Link to="/register">Registrieren</Link>
            </>
          )}
        </div>
      </nav>
    </header>
  );
}

export default Header;