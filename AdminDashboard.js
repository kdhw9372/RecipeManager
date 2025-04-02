import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import './AdminDashboard.css';

function AdminDashboard({ apiUrl, user }) {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [editingUser, setEditingUser] = useState(null);
  const [newUser, setNewUser] = useState({
    username: '',
    email: '',
    password: '',
    is_admin: false
  });
  const navigate = useNavigate();

  // Überprüfen, ob der aktuelle Benutzer ein Admin ist
  useEffect(() => {
    if (!user || !user.is_admin) {
      navigate('/');
    } else {
      fetchUsers();
    }
  }, [user, navigate]);

  // Alle Benutzer abrufen
  const fetchUsers = async () => {
    try {
      setLoading(true);
      const response = await axios.get(`${apiUrl}/admin/users`, { withCredentials: true });
      setUsers(response.data.users);
      setError(null);
    } catch (err) {
      setError('Fehler beim Laden der Benutzer: ' + (err.response?.data?.error || err.message));
    } finally {
      setLoading(false);
    }
  };

  // Benutzer-Bearbeitungsmodus aktivieren
  const handleEdit = (user) => {
    setEditingUser({
      ...user,
      password: '' // Passwort nicht anzeigen
    });
  };

  // Bearbeitungsmodus abbrechen
  const handleCancelEdit = () => {
    setEditingUser(null);
  };

  // Benutzer aktualisieren
  const handleUpdateUser = async () => {
    try {
      await axios.put(
        `${apiUrl}/admin/users/${editingUser.id}`,
        {
          username: editingUser.username,
          email: editingUser.email,
          password: editingUser.password || undefined, // Nur senden, wenn ein Wert vorhanden ist
          is_admin: editingUser.is_admin
        },
        { withCredentials: true }
      );
      
      fetchUsers(); // Benutzerliste aktualisieren
      setEditingUser(null); // Bearbeitungsmodus beenden
    } catch (err) {
      setError('Fehler beim Aktualisieren des Benutzers: ' + (err.response?.data?.error || err.message));
    }
  };

  // Neuen Benutzer erstellen
  const handleCreateUser = async (e) => {
    e.preventDefault();
    try {
      await axios.post(
        `${apiUrl}/admin/users`,
        newUser,
        { withCredentials: true }
      );
      
      // Formular zurücksetzen und Benutzerliste aktualisieren
      setNewUser({
        username: '',
        email: '',
        password: '',
        is_admin: false
      });
      fetchUsers();
    } catch (err) {
      setError('Fehler beim Erstellen des Benutzers: ' + (err.response?.data?.error || err.message));
    }
  };

  // Benutzer löschen
  const handleDeleteUser = async (userId) => {
    if (window.confirm('Sind Sie sicher, dass Sie diesen Benutzer löschen möchten?')) {
      try {
        await axios.delete(`${apiUrl}/admin/users/${userId}`, { withCredentials: true });
        fetchUsers(); // Benutzerliste aktualisieren
      } catch (err) {
        setError('Fehler beim Löschen des Benutzers: ' + (err.response?.data?.error || err.message));
      }
    }
  };

  if (loading) return <div>Benutzer werden geladen...</div>;

  return (
    <div className="admin-dashboard">
      <h1>Benutzerverwaltung</h1>
      
      {error && <div className="error-message">{error}</div>}
      
      {/* Neuen Benutzer erstellen */}
      <div className="admin-form-container">
        <h2>Neuen Benutzer erstellen</h2>
        <form onSubmit={handleCreateUser} className="admin-form">
          <div className="form-group">
            <label htmlFor="new-username">Benutzername</label>
            <input
              id="new-username"
              type="text"
              value={newUser.username}
              onChange={(e) => setNewUser({...newUser, username: e.target.value})}
              required
            />
          </div>
          
          <div className="form-group">
            <label htmlFor="new-email">E-Mail</label>
            <input
              id="new-email"
              type="email"
              value={newUser.email}
              onChange={(e) => setNewUser({...newUser, email: e.target.value})}
              required
            />
          </div>
          
          <div className="form-group">
            <label htmlFor="new-password">Passwort</label>
            <input
              id="new-password"
              type="password"
              value={newUser.password}
              onChange={(e) => setNewUser({...newUser, password: e.target.value})}
              required
            />
          </div>
          
          <div className="form-group checkbox">
            <input
              id="new-is-admin"
              type="checkbox"
              checked={newUser.is_admin}
              onChange={(e) => setNewUser({...newUser, is_admin: e.target.checked})}
            />
            <label htmlFor="new-is-admin">Administrator</label>
          </div>
          
          <button type="submit" className="btn btn-primary">Benutzer erstellen</button>
        </form>
      </div>
      
      {/* Benutzerliste */}
      <div className="user-list-container">
        <h2>Benutzerliste</h2>
        <table className="user-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Benutzername</th>
              <th>E-Mail</th>
              <th>Admin</th>
              <th>Erstellt am</th>
              <th>Aktionen</th>
            </tr>
          </thead>
          <tbody>
            {users.map(user => (
              <tr key={user.id}>
                <td>{user.id}</td>
                <td>{user.username}</td>
                <td>{user.email}</td>
                <td>{user.is_admin ? 'Ja' : 'Nein'}</td>
                <td>{new Date(user.created_at).toLocaleString()}</td>
                <td>
                  <button 
                    className="btn btn-edit" 
                    onClick={() => handleEdit(user)}
                  >
                    Bearbeiten
                  </button>
                  <button 
                    className="btn btn-delete" 
                    onClick={() => handleDeleteUser(user.id)}
                    disabled={user.id === window.currentUser?.id}
                  >
                    Löschen
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      
      {/* Benutzer bearbeiten Modal */}
      {editingUser && (
        <div className="modal-backdrop">
          <div className="modal">
            <h2>Benutzer bearbeiten</h2>
            <div className="form-group">
              <label htmlFor="edit-username">Benutzername</label>
              <input
                id="edit-username"
                type="text"
                value={editingUser.username}
                onChange={(e) => setEditingUser({...editingUser, username: e.target.value})}
                required
              />
            </div>
            
            <div className="form-group">
              <label htmlFor="edit-email">E-Mail</label>
              <input
                id="edit-email"
                type="email"
                value={editingUser.email}
                onChange={(e) => setEditingUser({...editingUser, email: e.target.value})}
                required
              />
            </div>
            
            <div className="form-group">
              <label htmlFor="edit-password">Passwort (leer lassen, um nicht zu ändern)</label>
              <input
                id="edit-password"
                type="password"
                value={editingUser.password}
                onChange={(e) => setEditingUser({...editingUser, password: e.target.value})}
              />
            </div>
            
            <div className="form-group checkbox">
              <input
                id="edit-is-admin"
                type="checkbox"
                checked={editingUser.is_admin}
                onChange={(e) => setEditingUser({...editingUser, is_admin: e.target.checked})}
                disabled={editingUser.id === window.currentUser?.id} // Verhindere Änderung des eigenen Admin-Status
              />
              <label htmlFor="edit-is-admin">Administrator</label>
            </div>
            
            <div className="modal-actions">
              <button className="btn btn-primary" onClick={handleUpdateUser}>Speichern</button>
              <button className="btn btn-secondary" onClick={handleCancelEdit}>Abbrechen</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default AdminDashboard;