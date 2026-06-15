import React from 'react';
import {
  createTheme,
  initializeIcons,
  ThemeProvider,
  type IPartialTheme,
} from '@fluentui/react';
import { readStoredClientTheme, type ClientTheme } from '@/utils/theme';

initializeIcons(undefined, { disableWarnings: true });

const clientFontFamilyBase =
  "'Segoe UI', 'Segoe UI Web (West European)', -apple-system, BlinkMacSystemFont, Roboto, 'Helvetica Neue', 'Source Sans 3 Variable', sans-serif";

const clientFontFamilyNumeric =
  "Bahnschrift, 'Segoe UI', 'Segoe UI Web (West European)', -apple-system, BlinkMacSystemFont, Roboto, 'Helvetica Neue', 'Source Sans 3 Variable', sans-serif";

const readCurrentTheme = (): ClientTheme => {
  if (typeof document === 'undefined') return 'dark';
  const attr = document.documentElement.getAttribute('data-client-theme');
  if (attr === 'light' || attr === 'dark') return attr;
  return readStoredClientTheme();
};

export const ClientRoot: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [clientTheme, setClientTheme] = React.useState<ClientTheme>(() => readCurrentTheme());

  React.useEffect(() => {
    const root = document.documentElement;
    const observer = new MutationObserver(() => {
      setClientTheme(readCurrentTheme());
    });

    observer.observe(root, {
      attributeFilter: ['class', 'data-client-theme'],
      attributes: true,
    });

    return () => observer.disconnect();
  }, []);

  const clientThemeObject = React.useMemo(() => {
    const isLight = clientTheme === 'light';
    const partialTheme: IPartialTheme = {
      palette: {
        themePrimary: '#0078d4',
        themeLighterAlt: '#eff6fc',
        themeLighter: '#deecf9',
        themeLight: '#c7e0f4',
        themeTertiary: '#71afe5',
        themeSecondary: '#2b88d8',
        themeDarkAlt: '#106ebe',
        themeDark: '#005a9e',
        themeDarker: '#004578',
        neutralLighterAlt: isLight ? '#faf9f8' : '#201f1e',
        neutralLighter: isLight ? '#f3f2f1' : '#292827',
        neutralLight: isLight ? '#edebe9' : '#323130',
        neutralQuaternaryAlt: isLight ? '#e1dfdd' : '#3b3a39',
        neutralQuaternary: isLight ? '#d0d0d0' : '#484644',
        neutralTertiaryAlt: isLight ? '#c8c6c4' : '#605e5c',
        neutralTertiary: isLight ? '#a19f9d' : '#a19f9d',
        neutralSecondary: isLight ? '#605e5c' : '#c8c6c4',
        neutralPrimaryAlt: isLight ? '#3b3a39' : '#edebe9',
        neutralPrimary: isLight ? '#323130' : '#f3f2f1',
        neutralDark: isLight ? '#201f1e' : '#faf9f8',
        white: isLight ? '#ffffff' : '#1b1a19',
        black: isLight ? '#000000' : '#ffffff',
      },
      fonts: {
        small: { fontFamily: clientFontFamilyBase },
        medium: { fontFamily: clientFontFamilyBase },
        large: { fontFamily: clientFontFamilyBase },
        xLarge: { fontFamily: clientFontFamilyBase },
      },
      semanticColors: {
        bodyBackground: isLight ? '#f5f5f5' : '#1b1a19',
        bodyText: isLight ? '#323130' : '#f3f2f1',
        disabledBodyText: isLight ? '#a19f9d' : '#797775',
        inputBackground: isLight ? '#ffffff' : '#201f1e',
        inputText: isLight ? '#323130' : '#f3f2f1',
        primaryButtonText: '#ffffff',
        primaryButtonTextHovered: '#ffffff',
        primaryButtonTextPressed: '#ffffff',
        primaryButtonTextDisabled: isLight ? '#a19f9d' : '#797775',
      },
    };
    return createTheme(partialTheme);
  }, [clientTheme]);

  return (
    <ThemeProvider theme={clientThemeObject} applyTo="none">
      <div className="client-root">
        {children}
      </div>
    </ThemeProvider>
  );
};
