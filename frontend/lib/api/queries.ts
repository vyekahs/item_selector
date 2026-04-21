import { useQuery, keepPreviousData } from '@tanstack/react-query';
import { apiRequest } from './client';
import {
  CategoryResponse,
  CategoryResponseSchema,
  OpportunityListSchema,
  OpportunityResponse,
  PaginatedProductsResponse,
  PaginatedProductsResponseSchema,
  ProductDetailResponse,
  ProductDetailResponseSchema,
} from './types';

export interface UseOpportunitiesParams {
  category_id?: number | null;
  limit?: number;
  min_score?: number;
  include_excluded?: boolean;
}

export function useOpportunities(params: UseOpportunitiesParams = {}) {
  const {
    category_id = null,
    limit = 20,
    min_score = 0,
    include_excluded = false,
  } = params;
  return useQuery({
    queryKey: ['opportunities', { category_id, limit, min_score, include_excluded }],
    placeholderData: keepPreviousData,
    queryFn: () =>
      apiRequest<OpportunityResponse[]>('/opportunities', {
        query: {
          category_id: category_id ?? undefined,
          limit,
          min_score,
          include_excluded,
        },
        schema: OpportunityListSchema,
      }),
  });
}

export function useCategories() {
  return useQuery({
    queryKey: ['categories'],
    staleTime: 1000 * 60 * 30,
    queryFn: () =>
      apiRequest<CategoryResponse>('/categories', {
        schema: CategoryResponseSchema,
      }),
  });
}

export function useProduct(productId: number | null | undefined) {
  return useQuery({
    queryKey: ['product', productId],
    enabled: typeof productId === 'number' && productId > 0,
    queryFn: () =>
      apiRequest<ProductDetailResponse>(`/products/${productId}`, {
        schema: ProductDetailResponseSchema,
      }),
  });
}

export interface UseProductListParams {
  limit?: number;
  offset?: number;
  keyword_id?: number | null;
}

export function useProductList(params: UseProductListParams = {}) {
  const { limit = 20, offset = 0, keyword_id = null } = params;
  return useQuery({
    queryKey: ['products', { limit, offset, keyword_id }],
    placeholderData: keepPreviousData,
    queryFn: () =>
      apiRequest<PaginatedProductsResponse>('/products', {
        query: {
          limit,
          offset,
          ...(keyword_id != null ? { keyword_id } : {}),
        },
        schema: PaginatedProductsResponseSchema,
      }),
  });
}
