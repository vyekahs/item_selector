import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiRequest } from './client';
import {
  DetailPageIngestAccepted,
  DetailPageIngestAcceptedSchema,
  FeedbackCreateRequest,
  FeedbackResponse,
  FeedbackResponseSchema,
  ProductCreateRequest,
  ProductScoreResponse,
  ProductScoreResponseSchema,
} from './types';

export function useCreateProduct() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ProductCreateRequest) =>
      apiRequest<ProductScoreResponse>('/products', {
        method: 'POST',
        body,
        schema: ProductScoreResponseSchema,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['products'] });
    },
  });
}

export interface ProductCostUpdate {
  moq?: number;
  china_domestic_shipping_krw?: number;
  intl_shipping_krw?: number;
  customs_duty_pct?: number;
  expected_sell_price_krw?: number;
  ad_cost_pct?: number;
  unit_weight_kg?: number;
  shipping_method?: 'lcl' | 'sea_self' | null;
}

export function useUpdateProductCosts(productId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ProductCostUpdate) =>
      apiRequest<ProductScoreResponse>(`/products/${productId}`, {
        method: 'PATCH',
        body,
        schema: ProductScoreResponseSchema,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['product', productId] });
      qc.invalidateQueries({ queryKey: ['products'] });
    },
  });
}

export function useCreateFeedback() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: FeedbackCreateRequest) =>
      apiRequest<FeedbackResponse>('/feedback', {
        method: 'POST',
        body,
        schema: FeedbackResponseSchema,
      }),
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: ['product', variables.product_id] });
    },
  });
}

export interface SeedCreateResponse {
  id: number;
  term: string;
  category_id: number | null;
  category_name: string | null;
  status: string;
  is_seed: boolean;
}

export function useCreateSeed() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (term: string) =>
      apiRequest<SeedCreateResponse>('/keywords/seed', {
        method: 'POST',
        body: { term },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['categories'] });
    },
  });
}

export function useExpandAndRecalculate() {
  return useMutation({
    mutationFn: () =>
      apiRequest<{ status: string; message: string }>('/admin/expand', {
        method: 'POST',
      }),
  });
}

export function useDiscoverSeeds() {
  return useMutation({
    mutationFn: () =>
      apiRequest<{ status: string; message: string }>('/admin/discover-seeds', {
        method: 'POST',
      }),
  });
}

export function useApproveCandidates() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (ids: number[]) =>
      apiRequest<{ promoted: number; requested: number }>(
        '/admin/seed-candidates/approve',
        { method: 'POST', body: { ids } },
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['seed-candidates'] });
    },
  });
}

// --- Detail pages -------------------------------------------------------

/**
 * POST /detail-pages/ingest. The body shape mirrors backend ``IngestRequest``
 * but is kept loose here (`Record<string, unknown>`) so callers can build
 * payloads incrementally without a duplicate Zod definition — the backend
 * is the source of truth for validation and will reject malformed bodies.
 */
export function useIngestDetailPage() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      apiRequest<DetailPageIngestAccepted>('/detail-pages/ingest', {
        method: 'POST',
        body,
        schema: DetailPageIngestAcceptedSchema,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['detail-pages'] });
    },
  });
}

export interface RegenerateDetailPageVars {
  detailPageId: number;
  template_name?: string;
}

export function useRegenerateDetailPage() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ detailPageId, template_name }: RegenerateDetailPageVars) => {
      const body =
        typeof template_name === 'string' && template_name.length > 0
          ? { template_name }
          : {};
      return apiRequest<DetailPageIngestAccepted>(
        `/detail-pages/${detailPageId}/regenerate`,
        {
          method: 'POST',
          body,
          schema: DetailPageIngestAcceptedSchema,
        },
      );
    },
    onSuccess: (_data, { detailPageId }) => {
      qc.invalidateQueries({ queryKey: ['detail-pages'] });
      qc.invalidateQueries({ queryKey: ['detail-page', detailPageId] });
    },
  });
}
