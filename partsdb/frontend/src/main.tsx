import React from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import './index.css';
import App from './App';
import { d } from './lib/debug';

d('main', 'initialization start');

// Add global error handler
window.showError = function(title: string, error: Error | string) {
  console.error('[ERROR]', title, error);
  
  // Create error overlay
  const overlay = document.createElement('div');
  overlay.style.position = 'fixed';
  overlay.style.top = '0';
  overlay.style.left = '0';
  overlay.style.right = '0';
  overlay.style.bottom = '0';
  overlay.style.backgroundColor = 'rgba(0, 0, 0, 0.8)';
  overlay.style.color = '#ff4d4f';
  overlay.style.padding = '20px';
  overlay.style.zIndex = '9999';
  overlay.style.overflow = 'auto';
  overlay.style.fontFamily = 'monospace';
  
  // Add error content
  overlay.innerHTML = `
    <div style="background: #1a1a1a; padding: 20px; border-radius: 4px; border-left: 4px solid #ff4d4f; margin-bottom: 20px;">
      <h2 style="margin-top: 0; color: #ff4d4f;">${title}</h2>
      <pre style="white-space: pre-wrap; color: #ddd; margin-bottom: 0;">${typeof error === 'string' ? error : error.stack || error.message}</pre>
    </div>
    <button id="error-dismiss" style="background: #333; color: #fff; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer;">Dismiss</button>
  `;
  
  document.body.appendChild(overlay);
  
  // Add dismiss handler
  document.getElementById('error-dismiss')?.addEventListener('click', () => {
    document.body.removeChild(overlay);
  });
};

const el = document.getElementById('root');
if (!el) {
  d('main', 'root element not found');
  throw new Error('Missing #root');
}

d('main', 'creating root and mounting App');
createRoot(el).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>
);

d('main', 'mount complete');

