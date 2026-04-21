import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import NewProductPage from '@/app/products/new/page';
import {
  installFetchMock,
  mockJsonResponse,
  renderWithClient,
} from '../test-utils';

const pushMock = vi.fn();

vi.mock('next/navigation', () => ({
  useRouter: () => ({
    push: pushMock,
    back: vi.fn(),
    replace: vi.fn(),
    forward: vi.fn(),
    refresh: vi.fn(),
    prefetch: vi.fn(),
  }),
  useSearchParams: () => new URLSearchParams('keyword_id=42&term=고양이'),
  useParams: () => ({}),
  usePathname: () => '/products/new',
}));

describe('NewProductPage', () => {
  beforeEach(() => {
    pushMock.mockReset();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('shows a validation error when required URL is missing', async () => {
    const fetchMock = installFetchMock([
      {
        match: () => true,
        response: () => mockJsonResponse({ detail: 'should not be called' }),
      },
    ]);
    const user = userEvent.setup();
    renderWithClient(<NewProductPage />);

    await user.type(screen.getByLabelText(/단가 \(CNY\)/), '45');
    await user.type(screen.getByLabelText(/MOQ/), '50');
    await user.click(screen.getByRole('button', { name: /분석하기/ }));

    await waitFor(() => {
      expect(screen.getByLabelText(/1688 URL/)).toHaveAttribute(
        'aria-invalid',
        'true',
      );
    });
    expect(fetchMock).not.toHaveBeenCalled();
    expect(pushMock).not.toHaveBeenCalled();
  });

  it('submits and routes to /products/[id] on success', async () => {
    installFetchMock([
      {
        match: (url, init) =>
          url.includes('/products') && init?.method === 'POST',
        response: () =>
          mockJsonResponse({
            product_id: 777,
            snapshot_date: '2026-04-18',
            total_score: 82,
            opportunity_score: 80,
            profit_score: 75,
            risk_score: 65,
            stability_score: 78,
            recommendation: 'GO',
            channel_profits: [],
            recommended_channel: 'SMARTSTORE',
          }),
      },
    ]);

    const user = userEvent.setup();
    renderWithClient(<NewProductPage />);

    expect(screen.getByTestId('linked-keyword')).toHaveTextContent(/고양이/);

    await user.type(
      screen.getByLabelText(/1688 URL/),
      'https://detail.1688.com/offer/abc.html',
    );
    await user.type(screen.getByLabelText(/단가 \(CNY\)/), '45');
    await user.type(screen.getByLabelText(/MOQ/), '50');

    await user.click(screen.getByRole('button', { name: /분석하기/ }));

    await waitFor(() => {
      expect(pushMock).toHaveBeenCalledWith('/products/777');
    });
  });
});
