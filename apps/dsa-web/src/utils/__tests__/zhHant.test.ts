import { describe, it, expect, afterEach } from 'vitest';
import { toHant, convertTree, stopHantDom } from '../zhHant';

afterEach(() => stopHantDom());

describe('toHant (string conversion)', () => {
  it('converts Simplified to Taiwan Traditional', () => {
    expect(toHant('创建账户')).toBe('建立賬戶');
    expect(toHant('信息')).toBe('資訊');
    expect(toHant('默认')).toBe('預設');
    expect(toHant('网络质量')).toContain('網路');
  });

  it('maps stock 代码 to 代碼 (not 程式碼)', () => {
    expect(toHant('股票代码')).toBe('股票代碼');
  });

  it('leaves non-CJK and already-Traditional text unchanged (idempotent)', () => {
    expect(toHant('AAPL 2330')).toBe('AAPL 2330');
    const once = toHant('创建账户');
    expect(toHant(once)).toBe(once);
  });
});

describe('convertTree (DOM)', () => {
  it('converts text nodes and display attributes', () => {
    document.body.innerHTML =
      '<div><button>创建账户</button><input placeholder="选择协议" /></div>';
    convertTree(document.body);
    expect(document.querySelector('button')!.textContent).toBe('建立賬戶');
    expect(document.querySelector('input')!.getAttribute('placeholder')).toBe('選擇協議');
  });

  it('does NOT convert input values, code, or textarea content', () => {
    document.body.innerHTML =
      '<code>创建账户</code><textarea>选择协议</textarea>';
    convertTree(document.body);
    expect(document.querySelector('code')!.textContent).toBe('创建账户');
    expect(document.querySelector('textarea')!.textContent).toBe('选择协议');
  });

  it('respects data-no-hant opt-out', () => {
    document.body.innerHTML = '<span data-no-hant>创建账户</span>';
    convertTree(document.body);
    expect(document.querySelector('span')!.textContent).toBe('创建账户');
  });
});
