import { expect, test } from '@playwright/test';

import {
  installApiMock,
  makeOpportunity,
  sampleCategories,
} from '../fixtures/api-mock';

test.describe('Opportunity dashboard (spec §6.1)', () => {
  test('renders the top 20 keywords and their 1688 deep link', async ({
    page,
  }) => {
    await installApiMock(page, {
      opportunities: [
        makeOpportunity({
          rank: 1,
          keyword_id: 100,
          term: '고양이 자동급수기',
          total_score: 87,
        }),
        makeOpportunity({
          rank: 2,
          keyword_id: 101,
          term: '강아지 슬링백',
          total_score: 81,
          category_id: 1,
        }),
      ],
    });

    await page.goto('/');

    await expect(
      page.getByRole('heading', { name: /이번주 중국 소싱 기회/ }),
    ).toBeVisible();

    const rows = page.getByTestId('opportunity-row');
    await expect(rows).toHaveCount(2);
    await expect(rows.first()).toContainText('고양이 자동급수기');
    await expect(rows.nth(1)).toContainText('강아지 슬링백');

    // 1688 deep link + internal product-input link per row.
    const firstLink = rows.first().getByTestId('search-1688-link');
    await expect(firstLink).toHaveAttribute(
      'href',
      /^https:\/\/s\.1688\.com\//,
    );
    await expect(firstLink).toHaveAttribute('target', '_blank');

    const inputLink = rows.first().getByTestId('input-product-link');
    await expect(inputLink).toHaveAttribute(
      'href',
      /\/products\/new\?keyword_id=100/,
    );
  });

  test('filters the list by category when the dropdown changes', async ({
    page,
  }) => {
    await installApiMock(page, {
      categories: sampleCategories,
      opportunities: [
        makeOpportunity({
          rank: 1,
          keyword_id: 100,
          term: '반려동물 키워드',
          category_id: 1,
          category_name: '반려동물',
        }),
        makeOpportunity({
          rank: 2,
          keyword_id: 200,
          term: '주방용품 키워드',
          category_id: 2,
          category_name: '주방용품',
          total_score: 77,
        }),
      ],
    });

    await page.goto('/');
    await expect(page.getByTestId('opportunity-row')).toHaveCount(2);

    await page.getByLabel('카테고리').selectOption('2');

    await expect(page.getByTestId('opportunity-row')).toHaveCount(1);
    await expect(page.getByTestId('opportunity-row').first()).toContainText(
      '주방용품 키워드',
    );
  });
});
