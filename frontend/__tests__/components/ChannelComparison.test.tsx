import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import { ChannelComparison } from '@/components/ChannelComparison';
import type { ChannelProfitResponse } from '@/lib/api/types';

// API sends percent fields as decimals (0.055 = 5.5%) — ChannelComparison
// multiplies by 100 for display via formatDecimalPct.
const smartstore: ChannelProfitResponse = {
  channel: 'SMARTSTORE',
  unit_cost_krw: 8200,
  expected_price_krw: 38000,
  platform_fee_pct: 0.055,
  ad_cost_pct: 0.08,
  unit_profit_krw: 24400,
  margin_pct: 0.64,
  roi_pct: 1.28,
  breakeven_units: 17,
};

const coupang: ChannelProfitResponse = {
  channel: 'COUPANG',
  unit_cost_krw: 8200,
  expected_price_krw: 42000,
  platform_fee_pct: 0.108,
  ad_cost_pct: 0.12,
  unit_profit_krw: 19100,
  margin_pct: 0.50,
  roi_pct: 0.98,
  breakeven_units: 21,
};

describe('<ChannelComparison />', () => {
  it('renders both channels with smartstore-first ordering', () => {
    render(
      <ChannelComparison
        channels={[coupang, smartstore]}
        recommendedChannel="SMARTSTORE"
      />,
    );
    const headers = screen.getAllByRole('columnheader');
    // first column is "항목", second/third are channels
    expect(headers[1]).toHaveTextContent(/스마트스토어/);
    expect(headers[2]).toHaveTextContent(/쿠팡/);
  });

  it('marks the recommended channel with a trophy and data attribute', () => {
    render(
      <ChannelComparison
        channels={[smartstore, coupang]}
        recommendedChannel="SMARTSTORE"
      />,
    );
    const ssHeader = screen.getByTestId('channel-header-SMARTSTORE');
    const cpHeader = screen.getByTestId('channel-header-COUPANG');
    expect(ssHeader.dataset.recommended).toBe('true');
    expect(cpHeader.dataset.recommended).toBe('false');
    expect(ssHeader).toHaveTextContent('🏆');
    expect(cpHeader).not.toHaveTextContent('🏆');
  });

  it('formats KRW + percentage cells per channel', () => {
    render(
      <ChannelComparison
        channels={[smartstore, coupang]}
        recommendedChannel="SMARTSTORE"
      />,
    );
    expect(
      screen.getByTestId('channel-cell-SMARTSTORE-개당 순이익'),
    ).toHaveTextContent(/24,400/);
    expect(
      screen.getByTestId('channel-cell-COUPANG-마진율'),
    ).toHaveTextContent(/50/);
  });

  it('renders an empty placeholder when no channel data is provided', () => {
    render(<ChannelComparison channels={[]} />);
    expect(screen.getByTestId('channel-empty')).toBeInTheDocument();
  });
});
