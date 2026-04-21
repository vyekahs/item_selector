import type { Page, Route } from '@playwright/test';

/**
 * Lightweight API mock helpers for Playwright E2E tests.
 *
 * All tests point `NEXT_PUBLIC_API_BASE_URL` at ``http://localhost:8000``
 * (see ``playwright.config.ts``). These helpers register `page.route()`
 * handlers so no real backend is needed at test time.
 */

export interface OpportunityFixture {
  rank: number;
  keyword_id: number;
  term: string;
  category_id: number | null;
  category_name: string | null;
  snapshot_date: string;
  total_score: number;
  demand_score: number;
  growth_score: number;
  competition_score: number;
  customs_score: number;
  trend_score: number;
  stability_score: number;
  is_excluded: boolean;
  exclusion_reasons: string | null;
  metrics: {
    monthly_search_volume: number | null;
    search_growth_3m: number | null;
    import_growth: number | null;
    competition_level: '낮음' | '중간' | '높음' | null;
    smartstore_avg_price_krw: number | null;
    coupang_avg_price_krw: number | null;
  };
  search_1688_url: string;
}

export function makeOpportunity(
  overrides: Partial<OpportunityFixture> = {},
): OpportunityFixture {
  return {
    rank: 1,
    keyword_id: 100,
    term: '고양이 자동급수기',
    category_id: 1,
    category_name: '반려동물',
    snapshot_date: '2026-04-18',
    total_score: 87,
    demand_score: 22,
    growth_score: 16,
    competition_score: 18,
    customs_score: 15,
    trend_score: 9,
    stability_score: 7,
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
    search_1688_url:
      'https://s.1688.com/selloffer/offer_search.htm?keywords=%EA%B3%A0%EC%96%91%EC%9D%B4',
    ...overrides,
  };
}

export const sampleCategories = {
  roots: [
    { id: 1, name: '반려동물', children: [] },
    { id: 2, name: '주방용품', children: [] },
  ],
};

export function makeProductScore(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    product_id: 777,
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
    ...overrides,
  };
}

export function makeProductDetail(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    id: 777,
    keyword_id: 100,
    url: 'https://detail.1688.com/offer/abc.html',
    name: '고양이 자동급수기 2L',
    cny_price: 45,
    moq: 50,
    notes: null,
    created_by_user: null,
    created_at: '2026-04-18T01:00:00Z',
    latest_score: makeProductScore({ product_id: 777 }),
    score_history: [makeProductScore({ product_id: 777 })],
    ...overrides,
  };
}

interface InstallOpts {
  opportunities?: OpportunityFixture[];
  categories?: typeof sampleCategories;
  productDetail?: ReturnType<typeof makeProductDetail>;
  productList?: {
    items: unknown[];
    total: number;
    limit: number;
    offset: number;
  };
  onCreateProduct?: (payload: unknown) => ReturnType<typeof makeProductScore>;
}

/**
 * Install a default API mock that covers every route touched by the
 * four E2E scenarios. Individual tests can call
 * ``page.route()`` afterwards to override specific endpoints.
 */
export async function installApiMock(page: Page, opts: InstallOpts = {}) {
  const opportunities = opts.opportunities ?? [
    makeOpportunity({ rank: 1, keyword_id: 100, term: '고양이 자동급수기' }),
    makeOpportunity({
      rank: 2,
      keyword_id: 101,
      term: '강아지 슬링백',
      total_score: 81,
    }),
  ];

  // All routes are anchored to the absolute API base URL so we never
  // accidentally intercept the browser's page navigation requests
  // (e.g. `page.goto('/products/12')` would otherwise be hijacked by
  // the `/products/<id>` route below and render the JSON body as the
  // page itself).
  await page.route(/^http:\/\/localhost:8000\/categories(\?.*)?$/, (route: Route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(opts.categories ?? sampleCategories),
    }),
  );

  await page.route(/^http:\/\/localhost:8000\/opportunities(\?.*)?$/, (route: Route) => {
    const url = new URL(route.request().url());
    const cat = url.searchParams.get('category_id');
    const filtered = cat
      ? opportunities.filter(
          (o) => o.category_id !== null && String(o.category_id) === cat,
        )
      : opportunities;
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(filtered),
    });
  });

  // GET list + POST create share the /products prefix; differentiate by method.
  await page.route(/^http:\/\/localhost:8000\/products(\?.*)?$/, (route: Route) => {
    const method = route.request().method();
    if (method === 'POST') {
      const raw = route.request().postData();
      let payload: unknown = null;
      try {
        payload = raw ? JSON.parse(raw) : null;
      } catch {
        payload = null;
      }
      const score = opts.onCreateProduct
        ? opts.onCreateProduct(payload)
        : makeProductScore();
      return route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify(score),
      });
    }

    // Default GET /products?limit=&offset=
    const listing = opts.productList ?? {
      items: [
        {
          id: 1,
          keyword_id: 100,
          url: 'https://detail.1688.com/offer/1.html',
          name: '샘플 A',
          cny_price: 45,
          moq: 50,
          notes: null,
          created_by_user: null,
          created_at: '2026-04-18T01:00:00Z',
          latest_score: makeProductScore({ product_id: 1 }),
        },
        {
          id: 2,
          keyword_id: 101,
          url: 'https://detail.1688.com/offer/2.html',
          name: '샘플 B',
          cny_price: 30,
          moq: 100,
          notes: null,
          created_by_user: null,
          created_at: '2026-04-17T01:00:00Z',
          latest_score: makeProductScore({
            product_id: 2,
            total_score: 66,
            recommendation: 'CONDITIONAL',
          }),
        },
      ],
      total: 2,
      limit: 20,
      offset: 0,
    };
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(listing),
    });
  });

  // GET /products/<id>
  await page.route(/^http:\/\/localhost:8000\/products\/\d+(\?.*)?$/, (route: Route) => {
    const detail = opts.productDetail ?? makeProductDetail();
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(detail),
    });
  });
}
