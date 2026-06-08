/**
 * Simplified -> Traditional (Taiwan) conversion for the zh-Hant UI language.
 *
 * Mirrors the backend's OpenCC ``s2twp`` (used for report bodies) so that when
 * the UI language is ``zh-Hant`` ALL on-screen Chinese renders Traditional —
 * including hundreds of hardcoded Simplified literals that never went through
 * the i18n system. Two layers use this:
 *   1. the central ``t()`` accessor (locale strings), and
 *   2. a guarded DOM converter (text nodes + a few display attributes) for
 *      literals/backend text that don't go through ``t()``.
 */

import { Converter } from 'opencc-js';
import { applyZhHantPhraseFixes } from './zhHantPhraseFixes';

let _convert: ((text: string) => string) | null = null;

function converter(): (text: string) => string {
  if (!_convert) {
    // cn -> twp: Simplified to Traditional with Taiwan idioms (== OpenCC s2twp).
    _convert = Converter({ from: 'cn', to: 'twp' });
  }
  return _convert;
}

// Has any CJK ideograph worth converting.
const CJK_RE = /[㐀-䶿一-鿿]/;

// Memoize conversions; UI text repeats heavily across renders.
const _cache = new Map<string, string>();
const _CACHE_LIMIT = 5000;

/**
 * Convert a Simplified string to Traditional (Taiwan). No-op for strings
 * without CJK. Idempotent for already-Traditional text. Cached.
 */
export function toHant(text: string): string {
  if (!text || !CJK_RE.test(text)) {
    return text;
  }
  const cached = _cache.get(text);
  if (cached !== undefined) {
    return cached;
  }
  const out = applyZhHantPhraseFixes(converter()(text));
  if (_cache.size < _CACHE_LIMIT) {
    _cache.set(text, out);
  }
  return out;
}

// ---------------------------------------------------------------------------
// DOM-level conversion (for hardcoded literals + backend-sourced chrome text)
// ---------------------------------------------------------------------------

// Text content we must never rewrite: code/script/style and editable fields
// (a <textarea>'s child text node IS its editable value).
const TEXT_SKIP_TAGS = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEXTAREA', 'CODE', 'PRE', 'SVG']);
// Attributes can be converted on any element (incl. <input> placeholder), only
// scripts/styles are off-limits.
const ATTR_SKIP_TAGS = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT']);
// Display-only attributes that frequently hold hardcoded Chinese.
const ATTRS = ['placeholder', 'aria-label', 'title', 'alt'];
const SKIP_ATTR = 'data-no-hant';

function shouldSkip(el: Element | null, tags: Set<string>): boolean {
  let node: Element | null = el;
  while (node) {
    if (tags.has(node.tagName)) return true;
    if (node.hasAttribute && node.hasAttribute(SKIP_ATTR)) return true;
    node = node.parentElement;
  }
  return false;
}

function convertTextNode(node: Text): void {
  const value = node.nodeValue;
  if (!value || !CJK_RE.test(value)) return;
  if (shouldSkip(node.parentElement, TEXT_SKIP_TAGS)) return;
  const converted = toHant(value);
  if (converted !== value) {
    node.nodeValue = converted;
  }
}

function convertElementAttrs(el: Element): void {
  if (shouldSkip(el, ATTR_SKIP_TAGS)) return;
  for (const attr of ATTRS) {
    const v = el.getAttribute(attr);
    if (v && CJK_RE.test(v)) {
      const converted = toHant(v);
      if (converted !== v) {
        el.setAttribute(attr, converted);
      }
    }
  }
}

/** Convert all text nodes + display attributes under a root element. */
export function convertTree(root: Node): void {
  if (root.nodeType === Node.TEXT_NODE) {
    convertTextNode(root as Text);
    return;
  }
  if (root.nodeType !== Node.ELEMENT_NODE) return;
  const el = root as Element;

  convertElementAttrs(el);
  const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT);
  let current: Node | null = walker.nextNode();
  while (current) {
    if (current.nodeType === Node.TEXT_NODE) {
      // convertTextNode re-checks ancestry, so excluded subtrees stay untouched.
      convertTextNode(current as Text);
    } else if (current.nodeType === Node.ELEMENT_NODE) {
      convertElementAttrs(current as Element);
    }
    current = walker.nextNode();
  }
}

let _observer: MutationObserver | null = null;
let _pending: Set<Node> | null = null;
let _flushScheduled = false;

function flush(): void {
  _flushScheduled = false;
  const nodes = _pending;
  _pending = null;
  if (!nodes || !_observer) return;
  // Pause observation while we mutate to avoid re-queueing our own writes.
  _observer.disconnect();
  for (const node of nodes) {
    try {
      convertTree(node);
    } catch {
      /* ignore a single bad node */
    }
  }
  _observer.observe(document.body, OBSERVE_OPTS);
}

const OBSERVE_OPTS: MutationObserverInit = {
  subtree: true,
  childList: true,
  characterData: true,
  attributes: true,
  attributeFilter: ATTRS,
};

function schedule(node: Node): void {
  if (!_pending) _pending = new Set();
  _pending.add(node);
  if (!_flushScheduled) {
    _flushScheduled = true;
    // Debounce to a frame; cheap, avoids per-mutation churn.
    if (typeof window.requestAnimationFrame === 'function') {
      window.requestAnimationFrame(() => flush());
    } else {
      window.setTimeout(() => flush(), 16);
    }
  }
}

/** Start converting the whole document to Traditional and keep new DOM converted. */
export function startHantDom(): void {
  if (_observer || typeof document === 'undefined') return;
  convertTree(document.body);
  _observer = new MutationObserver((mutations) => {
    for (const m of mutations) {
      if (m.type === 'characterData') {
        schedule(m.target);
      } else if (m.type === 'attributes' && m.target) {
        schedule(m.target);
      } else {
        m.addedNodes.forEach((n) => schedule(n));
      }
    }
  });
  _observer.observe(document.body, OBSERVE_OPTS);
}

/** Stop DOM conversion (when leaving zh-Hant). Already-converted text stays
 *  until React re-renders the affected components. */
export function stopHantDom(): void {
  if (_observer) {
    _observer.disconnect();
    _observer = null;
  }
  _pending = null;
  _flushScheduled = false;
}
