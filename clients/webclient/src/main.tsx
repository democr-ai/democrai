import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './index.css';
import App from './App';
import { applyClientTheme, readStoredClientTheme } from './utils/theme';

if (typeof document !== 'undefined') {
  applyClientTheme(readStoredClientTheme());
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
