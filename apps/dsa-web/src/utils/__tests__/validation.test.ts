import { describe, it, expect } from 'vitest';
import { validateStockCode, looksLikeStockCode, isObviouslyInvalidStockQuery } from '../validation';

describe('validateStockCode - Taiwan codes', () => {
  it.each(['tw0050', 'TW2330', 'tw006208', '0050.TW', '2330.TWO'])(
    'accepts Taiwan code %s',
    (code) => {
      expect(validateStockCode(code).valid).toBe(true);
      expect(looksLikeStockCode(code)).toBe(true);
      // Taiwan codes (letters + digits) must not be flagged as obviously invalid.
      expect(isObviouslyInvalidStockQuery(code)).toBe(false);
    },
  );

  it('still accepts existing A-share / HK / US formats', () => {
    expect(validateStockCode('600519').valid).toBe(true);
    expect(validateStockCode('00700').valid).toBe(true);
    expect(validateStockCode('AAPL').valid).toBe(true);
  });

  it('rejects a bare 4-digit code without the tw prefix', () => {
    expect(validateStockCode('2330').valid).toBe(false);
  });
});
