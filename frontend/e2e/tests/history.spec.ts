import { expect, test } from '@playwright/test';

import { installApiMock, makeProductScore } from '../fixtures/api-mock';

test.describe('Product history page', () => {
  test('renders the table and allows next/prev pagination', async ({
    page,
  }) => {
    const pageSize = 20;

    function buildListing(offset: number) {
      const total = 25;
      const startId = offset + 1;
      const endId = Math.min(offset + pageSize, total);
      const items = [];
      for (let id = startId; id <= endId; id++) {
        items.push({
          id,
          keyword_id: null,
          url: `https://detail.1688.com/offer/${id}.html`,
          name: `샘플 ${id}`,
          cny_price: 45,
          moq: 50,
          notes: null,
          created_by_user: null,
          created_at: '2026-04-18T01:00:00Z',
          latest_score: makeProductScore({
            product_id: id,
            total_score: 80 - (id % 10),
            recommendation: id % 2 === 0 ? 'GO' : 'CONDITIONAL',
          }),
        });
      }
      return { items, total, limit: pageSize, offset };
    }

    // Route /products?limit=&offset= to a dynamic listing. The mock
    // helper already sets up /products (POST + GET), but the default
    // listing is static — override with a per-offset version here.
    await installApiMock(page);
    await page.route(/\/products(\?.*)?$/, (route) => {
      if (route.request().method() !== 'GET') {
        return route.fallback();
      }
      const url = new URL(route.request().url());
      const offset = Number.parseInt(url.searchParams.get('offset') ?? '0', 10);
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(buildListing(Number.isFinite(offset) ? offset : 0)),
      });
    });

    await page.goto('/history');

    await expect(page.getByRole('heading', { name: /입력 이력/ })).toBeVisible();
    // Page 1: rows 1..20
    await expect(page.getByTestId('history-row')).toHaveCount(pageSize);
    await expect(page.getByText('총 25건')).toBeVisible();
    await expect(page.getByText(/페이지 1 \/ 2/)).toBeVisible();

    // Click next → offset advances to 20, showing the last 5 rows.
    await page.getByRole('button', { name: '다음' }).click();
    await expect(page.getByText(/페이지 2 \/ 2/)).toBeVisible();
    await expect(page.getByTestId('history-row')).toHaveCount(5);

    // Next button is disabled on the last page.
    await expect(page.getByRole('button', { name: '다음' })).toBeDisabled();

    // Prev button goes back.
    await page.getByRole('button', { name: '이전' }).click();
    await expect(page.getByText(/페이지 1 \/ 2/)).toBeVisible();
  });

  test('shows empty-state message when no products exist', async ({
    page,
  }) => {
    await installApiMock(page, {
      productList: { items: [], total: 0, limit: 20, offset: 0 },
    });
    await page.goto('/history');
    await expect(
      page.getByText(/아직 입력한 상품이 없습니다/),
    ).toBeVisible();
  });
});
