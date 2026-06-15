import React from 'react';

import { readClientStateValue, useClientStateSnapshot } from '@/state/clientState';

type Locale = 'en' | 'it' | 'es' | 'fr' | 'de' | 'zh';

type Messages = {
  blockedUrl: string;
  reload: string;
  noImage: string;
  missingVideoSource: string;
  pdfSourceUnavailable: string;
};

const SUPPORTED_LANGUAGES: readonly Locale[] = ['en', 'it', 'es', 'fr', 'de', 'zh'] as const;

const MESSAGES: Record<Locale, Messages> = {
  en: {
    blockedUrl: 'URL blocked',
    reload: 'Reload',
    noImage: 'No image',
    missingVideoSource: 'Missing video source',
    pdfSourceUnavailable: 'PDF source not available in this client.',
  },
  it: {
    blockedUrl: 'URL bloccato',
    reload: 'Ricarica',
    noImage: 'Nessuna immagine',
    missingVideoSource: 'Sorgente video mancante',
    pdfSourceUnavailable: 'Sorgente PDF non disponibile in questo client.',
  },
  es: {
    blockedUrl: 'URL bloqueada',
    reload: 'Recargar',
    noImage: 'Sin imagen',
    missingVideoSource: 'Falta la fuente de video',
    pdfSourceUnavailable: 'La fuente PDF no está disponible en este cliente.',
  },
  fr: {
    blockedUrl: 'URL bloquee',
    reload: 'Recharger',
    noImage: 'Aucune image',
    missingVideoSource: 'Source video manquante',
    pdfSourceUnavailable: "La source PDF n'est pas disponible dans ce client.",
  },
  de: {
    blockedUrl: 'URL blockiert',
    reload: 'Neu laden',
    noImage: 'Kein Bild',
    missingVideoSource: 'Videoquelle fehlt',
    pdfSourceUnavailable: 'PDF-Quelle ist in diesem Client nicht verfugbar.',
  },
  zh: {
    blockedUrl: 'URL 已阻止',
    reload: '重新加载',
    noImage: '无图像',
    missingVideoSource: '缺少视频源',
    pdfSourceUnavailable: '此客户端中 PDF 源不可用。',
  },
};

function normalizeLanguage(value: unknown): Locale {
  const raw = String(value || 'en').trim().toLowerCase();
  return SUPPORTED_LANGUAGES.includes(raw as Locale) ? (raw as Locale) : 'en';
}

export function useI18n(stateModel?: any): Messages {
  const contextState = useClientStateSnapshot();
  const resolvedState = stateModel || contextState;

  const language = React.useMemo(
    () => normalizeLanguage(readClientStateValue(resolvedState, 'global', '/core/user/language')),
    [resolvedState],
  );

  return MESSAGES[language];
}
