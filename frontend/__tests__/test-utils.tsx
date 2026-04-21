import { ReactElement, ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, RenderOptions } from '@testing-library/react';
import { vi } from 'vitest';

export function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
        staleTime: 0,
      },
      mutations: { retry: false },
    },
  });
}

export function renderWithClient(
  ui: ReactElement,
  options?: Omit<RenderOptions, 'wrapper'> & { client?: QueryClient },
) {
  const client = options?.client ?? createTestQueryClient();
  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  }
  return {
    client,
    ...render(ui, { wrapper: Wrapper, ...options }),
  };
}

interface MockResponseInit {
  status?: number;
  contentType?: string;
}

export function mockJsonResponse(
  body: unknown,
  init: MockResponseInit = {},
): Response {
  const status = init.status ?? 200;
  const contentType = init.contentType ?? 'application/json';
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': contentType },
  });
}

export function installFetchMock(
  routes: Array<{
    match: (url: string, init?: RequestInit) => boolean;
    response: () => Response | Promise<Response>;
  }>,
): ReturnType<typeof vi.fn> {
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url =
      typeof input === 'string'
        ? input
        : input instanceof URL
          ? input.toString()
          : input.url;
    for (const route of routes) {
      if (route.match(url, init)) {
        return route.response();
      }
    }
    throw new Error(`Unhandled fetch URL: ${url}`);
  });
  globalThis.fetch = fn as unknown as typeof fetch;
  return fn;
}
