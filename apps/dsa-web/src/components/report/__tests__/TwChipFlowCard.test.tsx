import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { TwChipFlowCard } from '../TwChipFlowCard';
import type { TwChipFlow } from '../../../types/analysis';

const flow: TwChipFlow = {
  institutional: {
    date: '2026-06-09',
    foreignNetLots: -379,
    trustNetLots: -79,
    dealerNetLots: 293,
    totalNetLots: -165,
    source: 'finmind',
  },
  margin: {
    date: '2026-06-09',
    marginBalanceLots: 8896,
    marginChangeLots: -79,
    shortBalanceLots: 84,
    shortChangeLots: -3,
    marginUsagePct: 7.44,
    source: 'finmind',
  },
};

describe('TwChipFlowCard', () => {
  it('renders institutional net and margin balances with signed formatting', () => {
    // language is 'zh'|'en' at this layer; Traditional UI comes from runtime OpenCC.
    render(<TwChipFlowCard chipFlow={flow} language="zh" />);
    expect(screen.getByText('个股筹码流动（三大法人 / 融资融券）')).toBeInTheDocument();
    expect(screen.getByText('-165 张')).toBeInTheDocument();   // total net (signed)
    expect(screen.getByText('+293')).toBeInTheDocument();       // dealer net positive
    expect(screen.getByText('7.44%')).toBeInTheDocument();      // margin usage
  });

  it('renders English labels and tolerates a missing block', () => {
    render(<TwChipFlowCard chipFlow={{ margin: flow.margin }} language="en" />);
    expect(screen.getByText('Chip Flow (Institutions / Margin)')).toBeInTheDocument();
    expect(screen.getByText('Margin balance')).toBeInTheDocument();
    // institutional block absent -> no "3 institutions net" label
    expect(screen.queryByText('3 institutions net')).not.toBeInTheDocument();
  });

  it('renders nothing when no chip flow data is present', () => {
    const { container } = render(<TwChipFlowCard chipFlow={null} language="zh" />);
    expect(container).toBeEmptyDOMElement();
    const { container: c2 } = render(<TwChipFlowCard chipFlow={{ institutional: null, margin: null }} language="zh" />);
    expect(c2).toBeEmptyDOMElement();
  });
});
