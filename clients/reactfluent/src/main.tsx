import { createRoot } from 'react-dom/client';
import '@fontsource-variable/source-sans-3/wght.css';
import './index.css';
import '../public/fonts/remixicon.css';
import App from './App';
import { applyClientTheme, readStoredClientTheme } from './utils/theme';
import { ClientRoot } from './design/ClientRoot';

if (typeof document !== 'undefined') {
  applyClientTheme(readStoredClientTheme());
}

createRoot(document.getElementById('root')!).render(
  <ClientRoot>
    <App />
  </ClientRoot>,
);
