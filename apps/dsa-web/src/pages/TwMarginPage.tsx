import { useCallback, useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { ApiErrorAlert, Button, Card, EmptyState, Select } from '../components/common';
import { getParsedApiError, type ParsedApiError } from '../api/error';
import { twMarginApi, type TwMarginRow, type TwMarginSortBy } from '../api/twMargin';
import { useUiLanguage } from '../contexts/UiLanguageContext';
import { TW_MARGIN_TEXT } from '../locales/featureText';

const TOP_N_OPTIONS = ['20', '30', '50', '100'];

function fmtInt(value: number | null): string {
  return value == null ? '-' : value.toLocaleString('en-US');
}

function fmtPct(value: number | null): string {
  return value == null ? '-' : `${value}`;
}

// TW convention: 漲/增 = red, 跌/減 = green.
function changeClass(value: number | null): string {
  if (value == null || value === 0) return 'text-muted-text';
  return value > 0 ? 'text-danger' : 'text-success';
}

function fmtChange(value: number | null): string {
  if (value == null) return '-';
  return value > 0 ? `+${value.toLocaleString('en-US')}` : value.toLocaleString('en-US');
}

export default function TwMarginPage() {
  const { language } = useUiLanguage();
  const text = TW_MARGIN_TEXT[language];

  const [sortBy, setSortBy] = useState<TwMarginSortBy>('margin_increase');
  const [topN, setTopN] = useState('30');
  const [rows, setRows] = useState<TwMarginRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ParsedApiError | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [tradeDate, setTradeDate] = useState<string | null>(null);

  useEffect(() => {
    document.title = text.documentTitle;
  }, [text.documentTitle]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setNotice(null);
    try {
      const resp = await twMarginApi.getRanking(Number(topN), sortBy);
      setRows(resp.ranking || []);
      setTradeDate(resp.tradeDate ?? null);
      if (!resp.success) {
        setNotice(resp.error || text.emptyDescription);
      }
    } catch (err) {
      setError(getParsedApiError(err));
      setRows([]);
      setTradeDate(null);
    } finally {
      setLoading(false);
    }
  }, [topN, sortBy, text.emptyDescription]);

  useEffect(() => {
    void load();
  }, [load]);

  const sortOptions = [
    { value: 'margin_increase', label: text.sortMarginInc },
    { value: 'margin_decrease', label: text.sortMarginDec },
    { value: 'short_increase', label: text.sortShortInc },
  ];

  return (
    <div className="space-y-4">
      <Card title={text.title} subtitle={text.subtitle} padding="md">
        <div className="flex flex-wrap items-end gap-3">
          <Select
            label={text.sortLabel}
            value={sortBy}
            onChange={(v) => setSortBy(v as TwMarginSortBy)}
            options={sortOptions}
          />
          <Select
            label={text.topNLabel}
            value={topN}
            onChange={setTopN}
            options={TOP_N_OPTIONS.map((n) => ({ value: n, label: n }))}
          />
          <Button variant="secondary" onClick={() => void load()} disabled={loading}>
            <RefreshCw className={loading ? 'h-4 w-4 animate-spin' : 'h-4 w-4'} />
            {loading ? text.refreshing : text.refresh}
          </Button>
        </div>
        <p className="mt-2 text-xs text-muted-text">
          {text.unitNote}
          {tradeDate ? <span className="ml-2">· {text.updateDate}: {tradeDate}</span> : null}
        </p>
      </Card>

      {error && <ApiErrorAlert error={error} />}

      <Card padding="none">
        {loading && rows.length === 0 ? (
          <div className="p-8 text-center text-sm text-muted-text">{text.loading}</div>
        ) : rows.length === 0 ? (
          <EmptyState title={text.emptyTitle} description={notice || text.emptyDescription} />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-xs text-muted-text">
                  <th className="px-3 py-2 text-right">{text.colRank}</th>
                  <th className="px-3 py-2 text-left">{text.colCode}</th>
                  <th className="px-3 py-2 text-left">{text.colName}</th>
                  <th className="px-3 py-2 text-right">{text.colMarginChange}</th>
                  <th className="px-3 py-2 text-right">{text.colMarginBalance}</th>
                  <th className="px-3 py-2 text-right">{text.colShortChange}</th>
                  <th className="px-3 py-2 text-right">{text.colShortRatio}</th>
                  <th className="px-3 py-2 text-right">{text.colUsage}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={r.stockCode} className="border-b border-border/50 hover:bg-elevated/60">
                    <td className="px-3 py-2 text-right text-muted-text">{i + 1}</td>
                    <td className="px-3 py-2 font-mono">{r.stockCode}</td>
                    <td className="px-3 py-2">{r.name}</td>
                    <td className={`px-3 py-2 text-right font-medium ${changeClass(r.marginChange)}`}>
                      {fmtChange(r.marginChange)}
                    </td>
                    <td className="px-3 py-2 text-right">{fmtInt(r.marginBalance)}</td>
                    <td className={`px-3 py-2 text-right ${changeClass(r.shortChange)}`}>
                      {fmtChange(r.shortChange)}
                    </td>
                    <td className="px-3 py-2 text-right">{fmtPct(r.shortMarginRatio)}</td>
                    <td className="px-3 py-2 text-right">{fmtPct(r.marginUsagePct)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
