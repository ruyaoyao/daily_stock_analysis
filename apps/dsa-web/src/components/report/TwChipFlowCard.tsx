import type React from 'react';
import type { ReportLanguage, TwChipFlow } from '../../types/analysis';
import { Card } from '../common';
import { normalizeReportLanguage } from '../../utils/reportLanguage';

interface TwChipFlowCardProps {
  chipFlow?: TwChipFlow | null;
  language?: ReportLanguage;
}

// ReportLanguage is only 'zh' | 'en' at this layer; zh-Hant (Traditional) UI is
// produced at runtime by the OpenCC DOM converter on the Simplified text.
type Lang = 'zh' | 'en';

const TEXT: Record<Lang, {
  title: string;
  inst: string;
  foreign: string;
  trust: string;
  dealer: string;
  total: string;
  marginBal: string;
  shortBal: string;
  usage: string;
  lots: string;
  note: string;
  asOf: string;
}> = {
  zh: {
    title: '个股筹码流动（三大法人 / 融资融券）',
    inst: '三大法人买卖超',
    foreign: '外资', trust: '投信', dealer: '自营商', total: '合计',
    marginBal: '融资余额', shortBal: '融券余额', usage: '融资使用率',
    lots: '张', note: '正=净买入 / 增加，负=净卖出 / 减少（台股涨红跌绿口径）', asOf: '资料日',
  },
  en: {
    title: 'Chip Flow (Institutions / Margin)',
    inst: '3 institutions net',
    foreign: 'Foreign', trust: 'Inv. trust', dealer: 'Dealer', total: 'Total',
    marginBal: 'Margin balance', shortBal: 'Short balance', usage: 'Margin usage',
    lots: 'lots', note: '+ = net buy / increase, − = net sell / decrease', asOf: 'As of',
  },
};

function changeClass(v?: number | null): string {
  if (v == null || v === 0) return 'text-muted-text';
  return v > 0 ? 'text-danger' : 'text-success';
}

function fmtSigned(v?: number | null, unit = ''): string {
  if (v == null) return '—';
  const s = v > 0 ? `+${v.toLocaleString('en-US')}` : v.toLocaleString('en-US');
  return unit ? `${s} ${unit}` : s;
}

function fmtPlain(v?: number | null, unit = ''): string {
  if (v == null) return '—';
  const s = v.toLocaleString('en-US');
  return unit ? `${s} ${unit}` : s;
}

export const TwChipFlowCard: React.FC<TwChipFlowCardProps> = ({ chipFlow, language = 'zh' }) => {
  const inst = chipFlow?.institutional;
  const margin = chipFlow?.margin;
  if (!inst && !margin) return null;

  const lang = normalizeReportLanguage(language) as Lang;
  const t = TEXT[lang] || TEXT.zh;

  return (
    <Card title={t.title} padding="md">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {inst && (
          <div className="space-y-1.5">
            <div className="flex items-baseline justify-between">
              <span className="text-sm font-medium text-secondary-text">{t.inst}</span>
              <span className={`text-base font-bold font-mono ${changeClass(inst.totalNetLots)}`}>
                {fmtSigned(inst.totalNetLots, t.lots)}
              </span>
            </div>
            <div className="grid grid-cols-3 gap-2 text-xs">
              {([['foreign', inst.foreignNetLots], ['trust', inst.trustNetLots], ['dealer', inst.dealerNetLots]] as const).map(
                ([key, val]) => (
                  <div key={key} className="rounded-lg bg-elevated/60 px-2 py-1.5">
                    <div className="text-muted-text">{t[key]}</div>
                    <div className={`font-mono ${changeClass(val)}`}>{fmtSigned(val)}</div>
                  </div>
                ),
              )}
            </div>
            {inst.date && <div className="text-[11px] text-muted-text">{t.asOf} {inst.date}</div>}
          </div>
        )}

        {margin && (
          <div className="space-y-1.5">
            <div className="flex items-baseline justify-between">
              <span className="text-sm font-medium text-secondary-text">{t.marginBal}</span>
              <span className="text-base font-bold font-mono text-foreground">
                {fmtPlain(margin.marginBalanceLots, t.lots)}
                {margin.marginChangeLots != null && (
                  <span className={`ml-1 text-xs ${changeClass(margin.marginChangeLots)}`}>
                    ({fmtSigned(margin.marginChangeLots)})
                  </span>
                )}
              </span>
            </div>
            <div className="flex items-baseline justify-between text-sm">
              <span className="text-muted-text">{t.shortBal}</span>
              <span className="font-mono text-foreground">
                {fmtPlain(margin.shortBalanceLots, t.lots)}
                {margin.shortChangeLots != null && (
                  <span className={`ml-1 text-xs ${changeClass(margin.shortChangeLots)}`}>
                    ({fmtSigned(margin.shortChangeLots)})
                  </span>
                )}
              </span>
            </div>
            {margin.marginUsagePct != null && (
              <div className="flex items-baseline justify-between text-sm">
                <span className="text-muted-text">{t.usage}</span>
                <span className="font-mono text-foreground">{margin.marginUsagePct}%</span>
              </div>
            )}
            {margin.date && <div className="text-[11px] text-muted-text">{t.asOf} {margin.date}</div>}
          </div>
        )}
      </div>
      <p className="mt-3 text-[11px] text-muted-text">{t.note}</p>
    </Card>
  );
};
