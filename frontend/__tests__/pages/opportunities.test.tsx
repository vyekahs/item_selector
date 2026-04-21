import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';

import HomePage from '@/app/page';
import {
  installFetchMock,
  mockJsonResponse,
  renderWithClient,
} from '../test-utils';

function makeOpportunity(overrides: Record<string, unknown> = {}) {
  return {
    rank: 1,
    keyword_id: 100,
    term: '고양이 자동급수기',
    category_id: 7,
    category_name: '반려동물',
    snapshot_date: '2026-04-18',
    total_score: 87,
    demand_score: 28,
    growth_score: 14,
    competition_score: 18,
    customs_score: 12,
    trend_score: 9,
    stability_score: 6,
    is_excluded: false,
    exclusion_reasons: null,
    metrics: {
      monthly_search_volume: 28000,
      search_growth_3m: 0.19,
      import_growth: 0.34,
      competition_level: '낮음',
      smartstore_avg_price_krw: 38000,
      coupang_avg_price_krw: 42000,
    },
    search_1688_url: 'https://s.1688.com/selloffer/offer_search.htm?keywords=cat',
    ...overrides,
  };
}

describe('HomePage (opportunities dashboard)', () => {
  beforeEach(() => {
    const list = [
      makeOpportunity({ rank: 1, keyword_id: 100, term: '고양이 자동급수기' }),
      makeOpportunity({
        rank: 2,
        keyword_id: 101,
        term: '강아지 슬링백',
        total_score: 81,
      }),
    ];
    installFetchMock([
      {
        match: (url) => url.includes('/categories'),
        response: () =>
          mockJsonResponse({
            roots: [
              { id: 1, name: '반려동물', children: [] },
              { id: 2, name: '주방용품', children: [] },
            ],
          }),
      },
      {
        match: (url) => url.includes('/opportunities'),
        response: () => mockJsonResponse(list),
      },
    ]);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders the page title and the TOP keyword cards from the API', async () => {
    renderWithClient(<HomePage />);

    expect(
      screen.getByRole('heading', { name: /이번주 중국 소싱 기회/ }),
    ).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getAllByTestId('opportunity-row')).toHaveLength(2);
    });
    expect(screen.getByText('고양이 자동급수기')).toBeInTheDocument();
    expect(screen.getByText('강아지 슬링백')).toBeInTheDocument();
  });

  it('exposes a deep link to 1688 and to the product-input form', async () => {
    renderWithClient(<HomePage />);
    const rows = await screen.findAllByTestId('opportunity-row');

    const firstRow = within(rows[0]);
    const ext = firstRow.getByTestId('search-1688-link');
    expect(ext).toHaveAttribute(
      'href',
      'https://s.1688.com/selloffer/offer_search.htm?keywords=cat',
    );
    expect(ext).toHaveAttribute('target', '_blank');

    const internal = firstRow.getByTestId('input-product-link');
    expect(internal).toHaveAttribute(
      'href',
      expect.stringContaining('/products/new?keyword_id=100'),
    );
  });
});
