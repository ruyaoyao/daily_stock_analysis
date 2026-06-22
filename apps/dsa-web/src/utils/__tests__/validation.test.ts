import { describe, it, test, expect } from 'vitest';
import {
  isObviouslyInvalidStockQuery,
  looksLikeStockCode,
  validateStockCode,
} from '../validation';

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

describe('stock code validation', () => {
  test.each([
    ['7203.T', '7203.T'],
    ['6758.t', '6758.T'],
    ['005930.KS', '005930.KS'],
    ['035720.kq', '035720.KQ'],
  ])('accepts JP/KR Yahoo suffix code %s', (input, normalized) => {
    expect(looksLikeStockCode(input)).toBe(true);
    expect(validateStockCode(input)).toEqual({
      valid: true,
      normalized,
    });
    expect(isObviouslyInvalidStockQuery(input)).toBe(false);
  });

  test.each(['7203', '005930.K', '035720.KRX'])(
    'does not treat ambiguous JP/KR-like query %s as a valid suffix code',
    (input) => {
      const result = validateStockCode(input);
      expect(result.valid).toBe(false);
    }
  );
});
