/**
 * Taiwan wording fixes applied after OpenCC s2twp.
 * Keep in sync with shared/zh_hant_phrase_fixes.json (single source of truth).
 */

import phraseFixes from '../../../../shared/zh_hant_phrase_fixes.json';

type PhrasePair = [string, string];

const SORTED_FIXES: PhrasePair[] = (phraseFixes as PhrasePair[])
  .filter(([from, to]) => Boolean(from) && from !== to)
  .sort(([a], [b]) => b.length - a.length);

export function applyZhHantPhraseFixes(text: string): string {
  if (!text) {
    return text;
  }
  let out = text;
  for (const [from, to] of SORTED_FIXES) {
    if (out.includes(from)) {
      out = out.split(from).join(to);
    }
  }
  return out;
}
