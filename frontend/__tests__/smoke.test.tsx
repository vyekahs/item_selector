import { afterEach, describe, expect, it, vi } from 'vitest';
import { screen } from '@testing-library/react';

import HomePage from '@/app/page';
import {
  installFetchMock,
  mockJsonResponse,
  renderWithClient,
} from './test-utils';

describe('HomePage (smoke)', () => {
  afterEach(() => vi.restoreAllMocks());

  it('renders the project headline', () => {
    installFetchMock([
      {
        match: (url) => url.includes('/categories'),
        response: () => mockJsonResponse({ roots: [] }),
      },
      {
        match: (url) => url.includes('/opportunities'),
        response: () => mockJsonResponse([]),
      },
    ]);

    renderWithClient(<HomePage />);
    expect(
      screen.getByRole('heading', { name: /이번주 중국 소싱 기회/ }),
    ).toBeInTheDocument();
  });
});
