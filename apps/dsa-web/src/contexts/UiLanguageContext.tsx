import type React from 'react';
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { formatUiText, UI_TEXT, type UiLanguage, type UiTextKey, type UiTextParams } from '../i18n/uiText';
import { getRuntimeInitialLanguage, getUiLanguageStorage, persistUiLanguage } from '../utils/uiLanguage';
import { startHantDom, stopHantDom, toHant } from '../utils/zhHant';

type UiLanguageContextValue = {
  language: UiLanguage;
  setLanguage: (language: UiLanguage) => void;
  t: (key: UiTextKey, params?: UiTextParams) => string;
};

const fallbackContext: UiLanguageContextValue = {
  language: 'zh',
  setLanguage: () => undefined,
  t: (key, params) => formatUiText(UI_TEXT.zh[key], params),
};

const UiLanguageContext = createContext<UiLanguageContextValue | null>(null);

export const UiLanguageProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [language, setLanguageState] = useState<UiLanguage>(getRuntimeInitialLanguage);

  const setLanguage = useCallback((nextLanguage: UiLanguage) => {
    setLanguageState(nextLanguage);
    persistUiLanguage(getUiLanguageStorage(), nextLanguage);
  }, []);

  useEffect(() => {
    if (typeof document !== 'undefined') {
      const htmlLang = language === 'en' ? 'en' : language === 'zh-Hant' ? 'zh-TW' : 'zh-CN';
      document.documentElement.lang = htmlLang;
    }
  }, [language]);

  // zh-Hant: convert the whole document (hardcoded literals + backend text that
  // never goes through t()) to Traditional, and keep newly-rendered DOM converted.
  useEffect(() => {
    if (typeof document === 'undefined') return undefined;
    if (language === 'zh-Hant') {
      startHantDom();
      return () => stopHantDom();
    }
    stopHantDom();
    return undefined;
  }, [language]);

  const value = useMemo<UiLanguageContextValue>(() => ({
    language,
    setLanguage,
    // For zh-Hant also run locale strings through OpenCC so any entry that
    // still carries Simplified text is normalized to Traditional.
    t: (key, params) => {
      const text = formatUiText(UI_TEXT[language][key], params);
      return language === 'zh-Hant' ? toHant(text) : text;
    },
  }), [language, setLanguage]);

  return (
    <UiLanguageContext.Provider value={value}>
      {children}
    </UiLanguageContext.Provider>
  );
};

// eslint-disable-next-line react-refresh/only-export-components -- useUiLanguage is a hook, co-located for context access
export function useUiLanguage(): UiLanguageContextValue {
  return useContext(UiLanguageContext) ?? fallbackContext;
}
