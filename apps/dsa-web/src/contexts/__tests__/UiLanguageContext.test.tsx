import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import {
  UiLanguageProvider,
} from '../UiLanguageContext';
import {
  getRuntimeInitialLanguage,
  persistUiLanguage,
  resolveInitialUiLanguage,
  UI_LANGUAGE_STORAGE_KEY,
} from '../../utils/uiLanguage';
import { UiLanguageToggle } from '../../components/i18n/UiLanguageToggle';

function createStorage(value: string | null): Storage {
  const store = new Map<string, string>();
  if (value !== null) {
    store.set(UI_LANGUAGE_STORAGE_KEY, value);
  }

  return {
    get length() {
      return store.size;
    },
    clear: () => store.clear(),
    getItem: (key: string) => store.get(key) ?? null,
    key: (index: number) => Array.from(store.keys())[index] ?? null,
    removeItem: (key: string) => {
      store.delete(key);
    },
    setItem: (key: string, nextValue: string) => {
      store.set(key, nextValue);
    },
  };
}

describe('UiLanguageContext', () => {
  it('resolves explicit storage choice before browser language', () => {
    expect(resolveInitialUiLanguage({
      storage: createStorage('zh'),
      navigatorLike: { language: 'en-US', languages: ['en-US'] },
    })).toBe('zh');

    expect(resolveInitialUiLanguage({
      storage: createStorage('en'),
      navigatorLike: { language: 'zh-CN', languages: ['zh-CN'] },
    })).toBe('en');
  });

  it('falls back from invalid storage to the first supported browser language and then zh', () => {
    expect(resolveInitialUiLanguage({
      storage: createStorage('fr'),
      navigatorLike: { language: 'en-US', languages: ['en-US'] },
    })).toBe('en');

    expect(resolveInitialUiLanguage({
      storage: createStorage('fr'),
      navigatorLike: { language: 'zh-CN', languages: ['zh-CN', 'en-US'] },
    })).toBe('zh');

    expect(resolveInitialUiLanguage({
      storage: createStorage(null),
      navigatorLike: { language: 'tr-TR', languages: ['tr-TR'] },
    })).toBe('zh');
  });

  it('falls back to browser language if storage getItem throws', () => {
    const throwingStorage = createStorage('en');
    throwingStorage.getItem = () => {
      throw new Error('Storage getItem disabled');
    };

    expect(resolveInitialUiLanguage({
      storage: throwingStorage,
      navigatorLike: { language: 'en-US', languages: ['en-US'] },
    })).toBe('en');
  });

  it('persists language preference via storage in a safe, non-throwing path', () => {
    const throwingStorage = createStorage('zh');
    throwingStorage.setItem = () => {
      throw new Error('Storage setItem disabled');
    };

    expect(() => persistUiLanguage(throwingStorage, 'en')).not.toThrow();
  });

  it('falls back safely when the localStorage accessor itself throws', () => {
    const originalDescriptor = Object.getOwnPropertyDescriptor(window, 'localStorage');
    Object.defineProperty(window, 'localStorage', {
      configurable: true,
      get: () => {
        throw new Error('localStorage disabled');
      },
    });

    try {
      expect(getRuntimeInitialLanguage()).toBe('en');
    } finally {
      if (originalDescriptor) {
        Object.defineProperty(window, 'localStorage', originalDescriptor);
      }
    }
  });

  it('resolves Traditional Chinese variants to zh-Hant', () => {
    expect(resolveInitialUiLanguage({
      storage: createStorage('zh-Hant'),
      navigatorLike: { language: 'en-US', languages: ['en-US'] },
    })).toBe('zh-Hant');

    expect(resolveInitialUiLanguage({
      storage: createStorage(null),
      navigatorLike: { language: 'zh-TW', languages: ['zh-TW'] },
    })).toBe('zh-Hant');

    expect(resolveInitialUiLanguage({
      storage: createStorage(null),
      navigatorLike: { language: 'zh-HK', languages: ['zh-HK'] },
    })).toBe('zh-Hant');

    // Generic / Simplified zh stays 'zh'
    expect(resolveInitialUiLanguage({
      storage: createStorage(null),
      navigatorLike: { language: 'zh-CN', languages: ['zh-CN'] },
    })).toBe('zh');
  });

  it('cycles UI language zh -> zh-Hant -> en -> zh and persists each step', () => {
    localStorage.setItem(UI_LANGUAGE_STORAGE_KEY, 'zh');

    render(
      <UiLanguageProvider>
        <UiLanguageToggle />
      </UiLanguageProvider>
    );

    // Label now shows the current language's own name (中文 / 繁體中文 / English)
    expect(screen.getByText('中文')).toBeInTheDocument();
    const toggle = screen.getByRole('button', { name: '切换界面语言' });

    // zh -> zh-Hant
    fireEvent.click(toggle);
    expect(localStorage.getItem(UI_LANGUAGE_STORAGE_KEY)).toBe('zh-Hant');
    expect(screen.getByText('繁體中文')).toBeInTheDocument();

    // zh-Hant -> en
    fireEvent.click(screen.getByRole('button'));
    expect(localStorage.getItem(UI_LANGUAGE_STORAGE_KEY)).toBe('en');
    expect(screen.getByText('English')).toBeInTheDocument();

    // en -> zh
    fireEvent.click(screen.getByRole('button', { name: 'Switch UI language' }));
    expect(localStorage.getItem(UI_LANGUAGE_STORAGE_KEY)).toBe('zh');
    expect(screen.getByText('中文')).toBeInTheDocument();
  });
});
