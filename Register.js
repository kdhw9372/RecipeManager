import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import axios from 'axios';

function Register({ setUser, apiUrl }) {
  const [formData, setFormData] = useState({
    username: '',
    email: '',
    password: '',
    confirmPassword: ''
  });
  const [error, setError] = useState('');
  const navigate = useNavigate();

  const handleChange = (e) => {
    setFormData({
      ...formData,
      [e.target.name]: e.target.value
    });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    // Überprüfen, ob die Passwörter übereinstimmen
    if (formData.password !== formData.confirmPassword) {
      setError('Die Passwörter stimmen nicht überein');
      return;
    }
    
    try {
      await axios.post(`${apiUrl}/register`, {
        username: formData.username,
        email: formData.email,
        password: formData.password
      });
      
      // Nach erfolgreicher Registrierung anmelden
      const loginResponse = await axios.post(`${apiUrl}/login`, {
        username: formData.username,
        password: formData.password
      }, { withCredentials: true });
      
      setUser(loginResponse.data.user);
      navigate('/');
    } catch (error) {
      setError(error.response?.data?.error || 'Registrierung fehlgeschlagen');
    }
  };

  return (
    <div className="auth-form">
      <h2>Registrieren</h2>
      {error && <div className="error-message">{error}</div>}
      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label htmlFor="username">Benutzername</label>
          <input
            type="text"
            id="username"
            name="username"
            value={formData.username}
            onChange={handleChange}
            required
          />
        </div>
        <div className="form-group">
          <label htmlFor="email">E-Mail</label>
          <input
            type="email"
            id="email"
            name="email"
            value={formData.email}
            onChange={handleChange}
            required
          />
        </div>
        <div className="form-group">
          <label htmlFor="password">Passwort</label>
          <input
            type="password"
            id="password"
            name="password"
            value={formData.password}
            onChange={handleChange}
            required
          />
        </div>
        <div className="form-group">
          <label htmlFor="confirmPassword">Passwort bestätigen</label>
          <input
            type="password"
            id="confirmPassword"
            name="confirmPassword"
            value={formData.confirmPassword}
            onChange={handleChange}
            required
          />
        </div>
        <button type="submit">Registrieren</button>
      </form>
      <p>
        Bereits ein Konto? <Link to="/login">Jetzt anmelden</Link>
      </p>
    </div>
  );
}

export default Register;