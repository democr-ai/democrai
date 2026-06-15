import { createRoot } from 'react-dom/client';
import '@fontsource-variable/source-sans-3/wght.css';
import 'bootstrap/dist/css/bootstrap-utilities.min.css';
import './index.css';
import '../public/fonts/remixicon.css';
import App from './App';
import { applyClientTheme, readStoredClientTheme } from './utils/theme';
import { FluentRoot } from './fluent/FluentRoot';

if (typeof document !== 'undefined') {
  applyClientTheme(readStoredClientTheme());
}

createRoot(document.getElementById('root')!).render(
  <FluentRoot>
    <App />
  </FluentRoot>,
);
