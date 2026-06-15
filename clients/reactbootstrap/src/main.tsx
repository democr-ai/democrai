import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import 'bootstrap-italia/dist/css/bootstrap-italia.min.css';
import 'typeface-titillium-web';
import 'typeface-roboto-mono';
import 'typeface-lora';
import './index.css';
import '../public/fonts/remixicon.css';
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
