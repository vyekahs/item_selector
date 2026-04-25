import { z } from 'zod';

/**
 * Runtime schemas (Zod) + static TypeScript types for the backend contract.
 * Mirrors the Pydantic models under `backend/app/schemas/`.
 */

// --- Categories ---------------------------------------------------------

const categoryNodeBase = z.object({
  id: z.number().int(),
  name: z.string(),
  parent_id: z.number().int().nullable().optional(),
  is_certification_required: z.boolean().optional().default(false),
});

export type CategoryNode = z.infer<typeof categoryNodeBase> & {
  children: CategoryNode[];
};

export const CategoryNodeSchema: z.ZodType<CategoryNode, z.ZodTypeDef, any> =
  categoryNodeBase.extend({
    children: z.lazy(() => CategoryNodeSchema.array()).default([]),
  });

export const CategoryResponseSchema = z.object({
  roots: z.array(CategoryNodeSchema).default([]),
});
export type CategoryResponse = z.infer<typeof CategoryResponseSchema>;

// --- Opportunities ------------------------------------------------------

export const CompetitionLevelSchema = z.enum(['낮음', '중간', '높음']);
export type CompetitionLevel = z.infer<typeof CompetitionLevelSchema>;

export const CompetitionBreakdownSchema = z.object({
  competition_index: z.number().nullable().optional().default(null),
  demand_factor: z.number().nullable().optional().default(null),
  shopping_penalty: z.number().nullable().optional().default(null),
});
export type CompetitionBreakdown = z.infer<typeof CompetitionBreakdownSchema>;

export const OpportunityMetricsSummarySchema = z.object({
  monthly_search_volume: z.number().int().nullable().optional().default(null),
  search_growth_3m: z.number().nullable().optional().default(null),
  customs_growth_3m_pct: z.number().nullable().optional().default(null),
  import_growth: z.number().nullable().optional().default(null),
  competition_raw_score: z.number().nullable().optional().default(null),
  competition_breakdown: CompetitionBreakdownSchema.nullable().optional().default(null),
  competition_level: CompetitionLevelSchema.nullable().optional().default(null),
  naver_shopping_count: z.number().int().nullable().optional().default(null),
  smartstore_avg_price_krw: z.number().int().nullable().optional().default(null),
  coupang_avg_price_krw: z.number().int().nullable().optional().default(null),
});
export type OpportunityMetricsSummary = z.infer<
  typeof OpportunityMetricsSummarySchema
>;

export const OpportunityResponseSchema = z.object({
  rank: z.number().int().min(1),
  keyword_id: z.number().int(),
  term: z.string(),
  category_id: z.number().int().nullable().optional().default(null),
  category_name: z.string().nullable().optional().default(null),
  score_details: z.record(z.any()).nullable().optional().default(null),
  snapshot_date: z.string(), // ISO YYYY-MM-DD
  total_score: z.number().min(0).max(100),
  demand_score: z.number().min(0),
  growth_score: z.number().min(0),
  competition_score: z.number().min(0),
  customs_score: z.number().min(0),
  trend_score: z.number().min(0),
  stability_score: z.number().min(0),
  is_excluded: z.boolean().default(false),
  exclusion_reasons: z.string().nullable().optional().default(null),
  metrics: OpportunityMetricsSummarySchema,
  search_1688_url: z.string(),
  product_count: z.number().int().min(0).default(0),
});
export type OpportunityResponse = z.infer<typeof OpportunityResponseSchema>;

export const OpportunityListSchema = z.array(OpportunityResponseSchema);

// --- Products -----------------------------------------------------------

export const ChannelSchema = z.enum(['SMARTSTORE', 'COUPANG']);
export type Channel = z.infer<typeof ChannelSchema>;

export const RecommendationSchema = z.enum(['GO', 'CONDITIONAL', 'PASS']);
export type Recommendation = z.infer<typeof RecommendationSchema>;

export const ChannelProfitResponseSchema = z.object({
  channel: ChannelSchema,
  unit_cost_krw: z.number().min(0),
  expected_price_krw: z.number().min(0),
  platform_fee_pct: z.number().min(0),
  ad_cost_pct: z.number().min(0),
  unit_profit_krw: z.number(),
  margin_pct: z.number(),
  roi_pct: z.number(),
  breakeven_units: z.number().int().min(0),
});
export type ChannelProfitResponse = z.infer<typeof ChannelProfitResponseSchema>;

export const CostBreakdownResponseSchema = z.object({
  moq: z.number().int(),
  goods_cost_krw: z.number().int(),
  china_domestic_shipping_krw: z.number().int(),
  intl_shipping_krw: z.number().int(),
  cif_krw: z.number().int(),
  cif_usd_approx: z.number(),
  customs_duty_krw: z.number().int(),
  vat_krw: z.number().int(),
  filing_fee_krw: z.number().int(),
  mokrok_duty_free: z.boolean(),
  total_cost_krw: z.number().int(),
  unit_cost_krw: z.number().int(),
  effective_duty_pct: z.number(),
  effective_vat_pct: z.number(),
  suggested_base_duty_pct: z.number().nullable().optional().default(null),
  suggested_kcfta_duty_pct: z.number().nullable().optional().default(null),
  duty_source: z.string().nullable().optional().default(null),
  exchange_rate_cny_krw: z.number(),
  expected_sell_price_krw: z.number().int().nullable().optional().default(null),
  naver_avg_price_krw: z.number().int().nullable().optional().default(null),
  sell_price_source: z.string().nullable().optional().default(null),
  shipping_method_applied: z.string().nullable().optional().default(null),
  total_weight_kg: z.number().nullable().optional().default(null),
  intl_shipping_source: z.string().nullable().optional().default(null),
});
export type CostBreakdownResponse = z.infer<typeof CostBreakdownResponseSchema>;

export const ProductScoreResponseSchema = z.object({
  product_id: z.number().int(),
  snapshot_date: z.string(),
  total_score: z.number().min(0).max(100),
  opportunity_score: z.number().min(0),
  profit_score: z.number().min(0),
  risk_score: z.number().min(0),
  stability_score: z.number().min(0),
  recommendation: RecommendationSchema,
  channel_profits: z.array(ChannelProfitResponseSchema).default([]),
  recommended_channel: ChannelSchema.nullable().optional().default(null),
  cost_breakdown: CostBreakdownResponseSchema.nullable().optional().default(null),
});
export type ProductScoreResponse = z.infer<typeof ProductScoreResponseSchema>;

export const ProductResponseSchema = z.object({
  id: z.number().int(),
  keyword_id: z.number().int().nullable().optional().default(null),
  url: z.string(),
  name: z.string().nullable().optional().default(null),
  cny_price: z.number(),
  moq: z.number().int(),
  notes: z.string().nullable().optional().default(null),
  created_by_user: z.string().nullable().optional().default(null),
  created_at: z.string(), // ISO datetime
  latest_score: ProductScoreResponseSchema.nullable().optional().default(null),
});
export type ProductResponse = z.infer<typeof ProductResponseSchema>;

export const ProductDetailResponseSchema = ProductResponseSchema.extend({
  score_history: z.array(ProductScoreResponseSchema).default([]),
});
export type ProductDetailResponse = z.infer<typeof ProductDetailResponseSchema>;

export const PaginatedProductsResponseSchema = z.object({
  items: z.array(ProductResponseSchema),
  total: z.number().int().min(0),
  limit: z.number().int().min(1).max(200),
  offset: z.number().int().min(0),
});
export type PaginatedProductsResponse = z.infer<
  typeof PaginatedProductsResponseSchema
>;

// --- Requests -----------------------------------------------------------

export const ProductCreateRequestSchema = z.object({
  keyword_id: z.number().int().min(1).nullable().optional(),
  url: z.string().url(),
  cny_price: z.number().gt(0),
  moq: z.number().int().min(1),
  name: z.string().max(500).nullable().optional(),
  notes: z.string().nullable().optional(),
  created_by_user: z.string().max(255).nullable().optional(),
});
export type ProductCreateRequest = z.infer<typeof ProductCreateRequestSchema>;

export const FeedbackCreateRequestSchema = z.object({
  product_id: z.number().int().min(1),
  purchased: z.boolean().default(false),
  monthly_sales: z.number().int().min(0).nullable().optional(),
  actual_revenue: z.number().min(0).nullable().optional(),
  notes: z.string().nullable().optional(),
});
export type FeedbackCreateRequest = z.infer<typeof FeedbackCreateRequestSchema>;

export const FeedbackResponseSchema = z.object({
  id: z.number().int(),
  product_id: z.number().int(),
  purchased: z.boolean(),
  monthly_sales: z.number().int().nullable().optional().default(null),
  actual_revenue: z.number().nullable().optional().default(null),
  notes: z.string().nullable().optional().default(null),
  recorded_at: z.string(),
});
export type FeedbackResponse = z.infer<typeof FeedbackResponseSchema>;

// --- Detail pages -------------------------------------------------------

export const DetailPageStatusSchema = z.enum([
  'pending',
  'processing',
  'done',
  'failed',
]);
export type DetailPageStatus = z.infer<typeof DetailPageStatusSchema>;

export const DetailPageSummarySchema = z.object({
  id: z.number().int(),
  status: DetailPageStatusSchema,
  title_ko: z.string().nullable().optional().default(null),
  image_path: z.string().nullable().optional().default(null),
  source_url: z.string(),
  source_platform: z.string(),
  created_at: z.string(),
});
export type DetailPageSummary = z.infer<typeof DetailPageSummarySchema>;

export const DetailPageDetailSchema = DetailPageSummarySchema.extend({
  props: z.record(z.any()).nullable().optional().default(null),
  failure_reason: z.string().nullable().optional().default(null),
});
export type DetailPageDetail = z.infer<typeof DetailPageDetailSchema>;

export const PaginatedDetailPagesResponseSchema = z.object({
  items: z.array(DetailPageSummarySchema),
  total: z.number().int().min(0),
  limit: z.number().int().min(1).max(200),
  offset: z.number().int().min(0),
});
export type PaginatedDetailPagesResponse = z.infer<
  typeof PaginatedDetailPagesResponseSchema
>;

export const DetailPageIngestAcceptedSchema = z.object({
  id: z.number().int(),
  status: z.string(),
  message: z.string(),
});
export type DetailPageIngestAccepted = z.infer<
  typeof DetailPageIngestAcceptedSchema
>;
