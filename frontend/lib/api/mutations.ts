import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiRequest } from './client';
import {
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
