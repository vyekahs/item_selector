import type { ZodTypeAny, ZodTypeDef } from 'zod';
import type { ZodType } from 'zod';

/**
 * Minimal typed fetch wrapper for the FastAPI backend.
 *
 * Reads the base URL from `NEXT_PUBLIC_API_BASE_URL` (matching the
 * value wired in `docker-compose.yml`). In dev/local we fall back to
 * the nginx-routed `/api` path so requests can be proxied by the
 * front-door proxy during `docker compose up`.
 */
export const API_BASE_URL: string =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, '') || '/api';

export class ApiError extends Error {
  status: number;
  detail?: unknown;

  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

type QueryValue = string | number | boolean | undefined | null;
type QueryRecord = Record<string, QueryValue>;

function buildQuery(params?: QueryRecord): string {
  if (!params) return '';
  const pairs: string[] = [];
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue;
    pairs.push(`${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`);
  }
  return pairs.length ? `?${pairs.join('&')}` : '';
}

export interface RequestOptions<T> {
  method?: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE';
  query?: QueryRecord;
  body?: unknown;
  schema?: ZodType<T, ZodTypeDef, any>;
  signal?: AbortSignal;
  headers?: Record<string, string>;
}

export async function apiRequest<T>(
  path: string,
  opts: RequestOptions<T> = {},
): Promise<T> {
  const {
    method = 'GET',
    query,
    body,
    schema,
    signal,
    headers = {},
  } = opts;

  const url = `${API_BASE_URL}${path}${buildQuery(query)}`;
  const init: RequestInit = {
    method,
    signal,
    headers: {
      Accept: 'application/json',
      ...headers,
    },
  };

  if (body !== undefined) {
    init.headers = {
      ...init.headers,
      'Content-Type': 'application/json',
    };
    init.body = JSON.stringify(body);
  }

  const response = await fetch(url, init);

  let payload: unknown = null;
  const contentType = response.headers.get('content-type') ?? '';
  if (contentType.includes('application/json')) {
    payload = await response.json().catch(() => null);
  } else {
    const text = await response.text().catch(() => '');
    payload = text || null;
  }

  if (!response.ok) {
    const detail =
      (payload && typeof payload === 'object' && 'detail' in payload
        ? (payload as { detail: unknown }).detail
        : payload) ?? response.statusText;
    const message =
      typeof detail === 'string' ? detail : `HTTP ${response.status}`;
    throw new ApiError(response.status, message, detail);
  }

  if (schema) {
    const parsed = schema.safeParse(payload);
    if (!parsed.success) {
      throw new ApiError(
        500,
        `Response validation failed: ${parsed.error.message}`,
        parsed.error.flatten(),
      );
    }
    return parsed.data;
  }

  return payload as T;
}
