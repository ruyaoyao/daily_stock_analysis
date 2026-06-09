import apiClient from './index';
import { toCamelCase } from './utils';

export type TwMarginSortBy = 'margin_increase' | 'margin_decrease' | 'short_increase';

export interface TwMarginRow {
  stockCode: string;
  name: string;
  marginBalance: number | null;
  marginPrev: number | null;
  marginChange: number | null;
  shortBalance: number | null;
  shortPrev: number | null;
  shortChange: number | null;
  offset: number | null;
  marginUsagePct: number | null;
  shortMarginRatio: number | null;
}

export interface TwMarginRankingResponse {
  success: boolean;
  market?: string;
  unit?: string;
  sortBy: TwMarginSortBy;
  count: number;
  ranking: TwMarginRow[];
  error?: string;
}

export const twMarginApi = {
  /** TWSE 上市融資融券排行（盤後，無需金鑰）。 */
  getRanking: async (
    topN = 50,
    sortBy: TwMarginSortBy = 'margin_increase',
  ): Promise<TwMarginRankingResponse> => {
    const response = await apiClient.get<Record<string, unknown>>(
      '/api/v1/tw-margin/ranking',
      { params: { top_n: topN, sort_by: sortBy } },
    );
    return toCamelCase<TwMarginRankingResponse>(response.data);
  },
};
