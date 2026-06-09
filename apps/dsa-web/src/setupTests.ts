import '@testing-library/jest-dom';
import { configure } from '@testing-library/react';

// Raise Testing Library's async timeout above its 1000ms default so that
// findBy*/waitFor for components with real polling (e.g. the 2000ms AlphaSift
// screen-task poll) do not flake under full-suite CPU load. Kept below
// vitest's 5000ms testTimeout so the outer test budget still bounds runs.
configure({ asyncUtilTimeout: 3000 });

class MemoryStorageMock implements Storage {
  private readonly values = new Map<string, string>();

  get length() {
    return this.values.size;
  }

  clear() {
    this.values.clear();
  }

  getItem(key: string) {
    return this.values.get(key) ?? null;
  }

  key(index: number) {
    return Array.from(this.values.keys())[index] ?? null;
  }

  removeItem(key: string) {
    this.values.delete(key);
  }

  setItem(key: string, value: string) {
    this.values.set(key, String(value));
  }
}

class IntersectionObserverMock implements IntersectionObserver {
  readonly root = null;
  readonly rootMargin = '';
  readonly thresholds = [0];

  disconnect() {}

  observe() {}

  takeRecords(): IntersectionObserverEntry[] {
    return [];
  }

  unobserve() {}
}

Object.defineProperty(globalThis, 'IntersectionObserver', {
  writable: true,
  value: IntersectionObserverMock,
});

const hasLocalStorage = (() => {
  try {
    return typeof globalThis.localStorage !== 'undefined';
  } catch {
    return false;
  }
})();

if (!hasLocalStorage) {
  Object.defineProperty(globalThis, 'localStorage', {
    configurable: true,
    value: new MemoryStorageMock(),
  });
}
