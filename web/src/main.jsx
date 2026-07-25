import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App.jsx';
import './index.css';

/* Apply persisted theme before first paint (avoids a flash of the wrong theme). */
document.documentElement.setAttribute('data-theme', localStorage.getItem('theme') || 'dark');

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
