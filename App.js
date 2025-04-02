import React, { useState, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import axios from 'axios';

// Komponenten importieren
import Header from './components/Header';
import Login from './components/Login';
import Register from './components/Register';
import Home from './components/Home';
import AdminDashboard from './components/AdminDashboard';
import RecipeUpload from './components/RecipeUpload';

// API-Basis-URL
const API_URL = '/api';

function App() {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Beim Laden der App versuchen, den aktuellen Benutzer abzurufen
    const checkAuth = async () => {
      try {
        const response = await axios.get(`${API_URL}/current_user`, { withCredentials: true });
        setUser(response.data.user);
        // Für den Benutzerzugriff im Modal
        window.currentUser = response.data.user;
      } catch (error) {
        console.log('Nicht angemeldet');
      } finally {
        setLoading(false);
      }
    };

    checkAuth();
  }, []);

  // Private Route-Komponente für geschützte Routen
  const PrivateRoute = ({ children, adminOnly = false }) => {
    if (loading) return <div>Laden...</div>;
    
    if (!user) return <Navigate to="/login" />;
    
    if (adminOnly && !user.is_admin) return <Navigate to="/" />;
    
    return children;
  };

  if (loading) {
    return <div>Laden...</div>;
  }

  return (
    <Router>
      <div className="App">
        <Header user={user} setUser={setUser} apiUrl={API_URL} />
        <main className="container">
          <Routes>
            <Route path="/login" element={<Login setUser={setUser} apiUrl={API_URL} />} />
            <Route path="/register" element={<Register setUser={setUser} apiUrl={API_URL} />} />
            <Route path="/admin" element={
              <PrivateRoute adminOnly={true}>
                <AdminDashboard apiUrl={API_URL} user={user} />
              </PrivateRoute>
            } />
            <Route path="/upload" element={
              <PrivateRoute>
                <RecipeUpload apiUrl={API_URL} />
              </PrivateRoute>
            } />
            <Route path="/" element={
              <PrivateRoute>
                <Home />
              </PrivateRoute>
            } />
          </Routes>
        </main>
      </div>
    </Router>
  );
}

export default App;