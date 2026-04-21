import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';

import ProductDetailPage from '@/app/products/[id]/page';
import {
  installFetchMock,
  mockJsonResponse,
  renderWithClient,
} from '../test-utils';

vi.mock('next/navigation', async () => {
  const actual = await vi.importActual<typeof import('next/navigation')>(
    'next/navigation',
  );
  return {
    ...actual,
    useRouter: () => ({
      push: vi.fn(),
      back: vi.fn(),
      replace: vi.fn(),
      forward: vi.fn(),
      refresh: vi.fn(),
      prefetch: vi.fn(),
    }),
    useSearchParams: () => new URLSearchParams(),
    useParams: () => ({ id: '12' }),
    usePathname: () => '/products/12',
  };
});

const detailPayload = {
  id: 12,
  keyword_id: 99,
  url: 'https://detail.1688.com/offer/abc.html',
  name: '고양이 자동급수기 2L',
  cny_price: 45,
  moq: 50,
  notes: null,
  created_by_user: null,
  created_at: '2026-04-18T01:00:00Z',
  latest_score: {
    product_id: 12,
    snapshot_date: '2026-04-18',
    total_score: 83,
    opportunity_score: 85,
    profit_score: 72,
    risk_score: 68,
    stability_score: 80,
    recommendation: 'GO',
    channel_profits: [
      {
        channel: 'SMARTSTORE',
        unit_cost_krw: 8200,
        expected_price_krw: 38000,
        platform_fee_pct: 5.5,
        ad_cost_pct: 8,
        unit_profit_krw: 24400,
        margin_pct: 64,
        roi_pct: 128,
        breakeven_units: 17,
      },
      {
        channel: 'COUPANG',
        unit_cost_krw: 8200,
        expected_price_krw: 42000,
        platform_fee_pct: 10.8,
        ad_cost_pct: 12,
        unit_profit_krw: 19100,
        margin_pct: 50,
        roi_pct: 98,
        breakeven_units: 21,
      },
    ],
    recommended_channel: 'SMARTSTORE',
  },
  score_history: [],
};

describe('ProductDetailPage', () => {
  beforeEach(() => {
    installFetchMock([
      {
        match: (url) => url.includes('/products/12'),
        response: () => mockJsonResponse(detailPayload),
      },
    ]);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders the radar chart, scores, and channel comparison', async () => {
    renderWithClient(<ProductDetailPage />);

    await waitFor(() => {
      expect(screen.getByTestId('radar-section')).toBeInTheDocument();
    });
    expect(screen.getByTestId('radar-score-chart')).toBeInTheDocument();

    // Score badge with rounded value + recommendation
    const scorePill = screen.getByTestId('score-pill');
    expect(scorePill).toHaveTextContent('83점');
    const rec = screen.getByTestId('recommendation-pill');
    expect(rec.dataset.recommendation).toBe('GO');

    // Channel comparison values
    expect(
      screen.getByTestId('channel-cell-SMARTSTORE-개당 순이익'),
    ).toHaveTextContent(/24,400/);
    expect(
      screen.getByTestId('channel-cell-COUPANG-개당 순이익'),
    ).toHaveTextContent(/19,100/);

    // Recommended channel banner
    expect(screen.getByTestId('recommended-channel')).toHaveTextContent(
      /스마트스토어/,
    );
  });
});
