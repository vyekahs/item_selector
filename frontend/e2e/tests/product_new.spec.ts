import { expect, test } from '@playwright/test';

import { installApiMock, makeProductScore } from '../fixtures/api-mock';

test.describe('Product input form (spec §6.2)', () => {
  test('rejects submission with an empty URL (client-side validation)', async ({
    page,
  }) => {
    let captured = 0;
    await installApiMock(page, {
      onCreateProduct: (payload) => {
        captured += 1;
        void payload;
        return makeProductScore({ product_id: 9001 });
      },
    });

    await page.goto('/products/new?keyword_id=42&term=%EA%B3%A0%EC%96%91%EC%9D%B4');
    await expect(page.getByTestId('linked-keyword')).toBeVisible();

    await page.getByLabel(/단가 \(CNY\)/).fill('45');
    await page.getByLabel(/MOQ/).fill('50');
    await page.getByRole('button', { name: /분석하기/ }).click();

    // zod flagged the missing URL → aria-invalid + no POST sent.
    await expect(page.getByLabel(/1688 URL/)).toHaveAttribute(
      'aria-invalid',
      'true',
    );
    expect(captured).toBe(0);
  });

  test('submits valid input and navigates to the product detail page', async ({
    page,
  }) => {
    await installApiMock(page, {
      onCreateProduct: () => makeProductScore({ product_id: 777 }),
    });

    await page.goto('/products/new');
    await page
      .getByLabel(/1688 URL/)
      .fill('https://detail.1688.com/offer/abc.html');
    await page.getByLabel(/단가 \(CNY\)/).fill('45');
    await page.getByLabel(/MOQ/).fill('50');
    await page.getByLabel(/상품명/).fill('고양이 자동급수기 2L');

    await page.getByRole('button', { name: /분석하기/ }).click();

    await expect(page).toHaveURL(/\/products\/777$/);
  });
});
