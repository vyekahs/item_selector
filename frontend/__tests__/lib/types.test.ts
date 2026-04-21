import { describe, expect, it } from 'vitest';

import {
  CategoryResponseSchema,
  OpportunityListSchema,
  OpportunityResponseSchema,
  PaginatedProductsResponseSchema,
  ProductCreateRequestSchema,
  ProductDetailResponseSchema,
  ProductScoreResponseSchema,
} from '@/lib/api/types';

const validOpportunity = {
  rank: 1,
  keyword_id: 42,
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
};

describe('OpportunityResponseSchema', () => {
  it('accepts a fully-populated payload', () => {
    expect(() => OpportunityResponseSchema.parse(validOpportunity)).not.toThrow();
  });

  it('accepts a minimal payload with metric defaults', () => {
    const minimal = {
      rank: 1,
      keyword_id: 1,
      term: 'a',
      snapshot_date: '2026-04-18',
      total_score: 50,
      demand_score: 0,
      growth_score: 0,
      competition_score: 0,
      customs_score: 0,
      trend_score: 0,
      stability_score: 0,
      metrics: {},
      search_1688_url: 'https://example.com',
    };
    const parsed = OpportunityResponseSchema.parse(minimal);
    expect(parsed.metrics.monthly_search_volume).toBeNull();
    expect(parsed.is_excluded).toBe(false);
  });

  it('rejects payloads with out-of-range total_score', () => {
    const bad = { ...validOpportunity, total_score: 150 };
    expect(() => OpportunityResponseSchema.parse(bad)).toThrow();
  });

  it('rejects payloads with unknown competition levels', () => {
    const bad = {
      ...validOpportunity,
      metrics: { ...validOpportunity.metrics, competition_level: 'EXTREME' },
    };
    expect(() => OpportunityResponseSchema.parse(bad)).toThrow();
  });
});

describe('OpportunityListSchema', () => {
  it('round-trips a list of opportunities', () => {
    const list = OpportunityListSchema.parse([validOpportunity, validOpportunity]);
    expect(list).toHaveLength(2);
  });
});

describe('CategoryResponseSchema', () => {
  it('parses a recursive category tree', () => {
    const result = CategoryResponseSchema.parse({
      roots: [
        {
          id: 1,
          name: '반려동물',
          children: [
            { id: 11, name: '강아지', parent_id: 1, children: [] },
            { id: 12, name: '고양이', parent_id: 1 },
          ],
        },
      ],
    });
    expect(result.roots[0].children).toHaveLength(2);
    expect(result.roots[0].children[1].children).toEqual([]);
  });
});

describe('Product schemas', () => {
  const validScore = {
    product_id: 1,
    snapshot_date: '2026-04-18',
    total_score: 83,
    opportunity_score: 85,
    profit_score: 72,
    risk_score: 68,
    stability_score: 80,
    recommendation: 'GO' as const,
    channel_profits: [
      {
        channel: 'SMARTSTORE' as const,
        unit_cost_krw: 8200,
        expected_price_krw: 38000,
        platform_fee_pct: 5.5,
        ad_cost_pct: 8,
        unit_profit_krw: 24400,
        margin_pct: 64,
        roi_pct: 128,
        breakeven_units: 17,
      },
    ],
    recommended_channel: 'SMARTSTORE' as const,
  };

  it('parses ProductScoreResponse with channel breakdown', () => {
    expect(() => ProductScoreResponseSchema.parse(validScore)).not.toThrow();
  });

  it('rejects unknown recommendation values', () => {
    const bad = { ...validScore, recommendation: 'MAYBE' };
    expect(() => ProductScoreResponseSchema.parse(bad)).toThrow();
  });

  it('parses ProductDetailResponse with score history', () => {
    const detail = ProductDetailResponseSchema.parse({
      id: 1,
      url: 'https://detail.1688.com/offer/1.html',
      cny_price: 45,
      moq: 50,
      created_at: '2026-04-18T00:00:00Z',
      latest_score: validScore,
      score_history: [validScore],
    });
    expect(detail.score_history).toHaveLength(1);
  });

  it('parses paginated product list', () => {
    const page = PaginatedProductsResponseSchema.parse({
      items: [],
      total: 0,
      limit: 20,
      offset: 0,
    });
    expect(page.items).toEqual([]);
  });
});

describe('ProductCreateRequestSchema', () => {
  it('rejects non-positive cny_price', () => {
    expect(() =>
      ProductCreateRequestSchema.parse({
        url: 'https://detail.1688.com/offer/1.html',
        cny_price: 0,
        moq: 1,
      }),
    ).toThrow();
  });

  it('rejects MOQ below 1', () => {
    expect(() =>
      ProductCreateRequestSchema.parse({
        url: 'https://detail.1688.com/offer/1.html',
        cny_price: 1,
        moq: 0,
      }),
    ).toThrow();
  });

  it('accepts a minimal valid payload', () => {
    const parsed = ProductCreateRequestSchema.parse({
      url: 'https://detail.1688.com/offer/1.html',
      cny_price: 1.23,
      moq: 50,
    });
    expect(parsed.moq).toBe(50);
  });
});
