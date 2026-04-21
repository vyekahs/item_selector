import { expect, test } from '@playwright/test';

import {
  installApiMock,
  makeProductDetail,
  makeProductScore,
} from '../fixtures/api-mock';

test.describe('Product detail page (spec §6.2 하단)', () => {
  test('renders the radar section, 2-channel comparison, and recommended channel', async ({
    page,
  }) => {
    await installApiMock(page, {
      productDetail: makeProductDetail({
        id: 12,
        name: '고양이 자동급수기 2L',
        latest_score: makeProductScore({
          product_id: 12,
          total_score: 83,
          recommendation: 'GO',
          recommended_channel: 'SMARTSTORE',
        }),
        score_history: [makeProductScore({ product_id: 12 })],
      }),
    });

    await page.goto('/products/12');

    await expect(page.getByTestId('radar-section')).toBeVisible();

    // Score badge shows rounded total.
    await expect(page.getByTestId('score-pill')).toContainText('83');

    // 2-channel table values visible + recommended channel banner.
    await expect(
      page.getByTestId('channel-cell-SMARTSTORE-개당 순이익'),
    ).toContainText('24,400');
    await expect(
      page.getByTestId('channel-cell-COUPANG-개당 순이익'),
    ).toContainText('19,100');

    const banner = page.getByTestId('recommended-channel');
    await expect(banner).toBeVisible();
    await expect(banner).toContainText('스마트스토어');
  });

  test('surfaces a 404-shaped failure without crashing the page shell', async ({
    page,
  }) => {
    // Match only the absolute API URL so we do NOT intercept the
    // browser's navigation to /products/<id> (which would render the
    // 404 JSON body as the page itself).
    await page.route(/^http:\/\/localhost:8000\/products\/\d+(\?.*)?$/, (route) =>
      route.fulfill({
        status: 404,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'product not found' }),
      }),
    );
    await page.route(/^http:\/\/localhost:8000\/categories(\?.*)?$/, (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ roots: [] }),
      }),
    );

    await page.goto('/products/999999');

    await expect(page.getByRole('alert')).toBeVisible();
  });
});
