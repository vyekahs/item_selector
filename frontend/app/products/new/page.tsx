'use client';

import { useRouter, useSearchParams } from 'next/navigation';
import { FormEvent, Suspense, useMemo, useState } from 'react';

import { useCreateProduct } from '@/lib/api/mutations';
import {
  ProductCreateRequest,
  ProductCreateRequestSchema,
} from '@/lib/api/types';

interface FormState {
  url: string;
  cny_price: string;
  moq: string;
  name: string;
  notes: string;
}

const INITIAL: FormState = {
  url: '',
  cny_price: '',
  moq: '',
  name: '',
  notes: '',
};

export default function NewProductPage() {
  return (
    <Suspense fallback={<div className="text-sm text-slate-500">로딩 중…</div>}>
      <NewProductForm />
    </Suspense>
  );
}

function NewProductForm() {
  const params = useSearchParams();
  const router = useRouter();
  const mutation = useCreateProduct();

  const prefilledKeywordId = useMemo(() => {
    const raw = params.get('keyword_id');
    if (!raw) return null;
    const parsed = Number(raw);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
  }, [params]);
  const prefilledTerm = params.get('term') ?? '';

  const [state, setState] = useState<FormState>(INITIAL);
  const [errors, setErrors] = useState<Record<string, string>>({});

  const update = <K extends keyof FormState>(key: K, value: string) => {
    setState((prev) => ({ ...prev, [key]: value }));
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setErrors({});

    const payload: ProductCreateRequest = {
      keyword_id: prefilledKeywordId,
      url: state.url.trim(),
      cny_price: Number.parseFloat(state.cny_price),
      moq: Number.parseInt(state.moq, 10),
      name: state.name.trim() || null,
      notes: state.notes.trim() || null,
    };

    const result = ProductCreateRequestSchema.safeParse(payload);
    if (!result.success) {
      const fieldErrors: Record<string, string> = {};
      for (const issue of result.error.issues) {
        const key = issue.path[0];
        if (typeof key === 'string' && !fieldErrors[key]) {
          fieldErrors[key] = issue.message;
        }
      }
      setErrors(fieldErrors);
      return;
    }

    try {
      const score = await mutation.mutateAsync(result.data);
      router.push(`/products/${score.product_id}`);
    } catch (err) {
      setErrors({
        form:
          err instanceof Error ? err.message : '상품 등록에 실패했습니다.',
      });
    }
  };

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-5">
      <header>
        <h1 className="text-xl font-bold text-slate-900">상품 입력</h1>
        <p className="mt-1 text-sm text-slate-500">
          1688 URL, 단가(CNY), MOQ를 입력하면 2채널 수익을 자동 분석합니다.
        </p>
      </header>

      {prefilledKeywordId ? (
        <p
          data-testid="linked-keyword"
          className="rounded-md border border-brand-100 bg-brand-50 px-3 py-2 text-sm text-brand-700"
        >
          연결된 키워드: <strong>{prefilledTerm || `#${prefilledKeywordId}`}</strong>
        </p>
      ) : null}

      <form
        className="card flex flex-col gap-4"
        onSubmit={handleSubmit}
        noValidate
      >
        <div>
          <label className="label" htmlFor="product-url">
            1688 URL <span className="text-rose-500">*</span>
          </label>
          <input
            id="product-url"
            name="url"
            type="url"
            className="input"
            placeholder="https://detail.1688.com/offer/..."
            value={state.url}
            onChange={(e) => update('url', e.target.value)}
            aria-invalid={Boolean(errors.url) || undefined}
            aria-describedby={errors.url ? 'err-url' : undefined}
            required
          />
          {errors.url ? (
            <p id="err-url" className="mt-1 text-xs text-rose-600">
              {errors.url}
            </p>
          ) : null}
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <label className="label" htmlFor="product-cny-price">
              단가 (CNY) <span className="text-rose-500">*</span>
            </label>
            <input
              id="product-cny-price"
              name="cny_price"
              type="number"
              step="0.01"
              min="0.01"
              className="input"
              placeholder="45"
              value={state.cny_price}
              onChange={(e) => update('cny_price', e.target.value)}
              aria-invalid={Boolean(errors.cny_price) || undefined}
              aria-describedby={errors.cny_price ? 'err-cny' : undefined}
              required
            />
            {errors.cny_price ? (
              <p id="err-cny" className="mt-1 text-xs text-rose-600">
                {errors.cny_price}
              </p>
            ) : null}
          </div>

          <div>
            <label className="label" htmlFor="product-moq">
              MOQ (최소주문수량) <span className="text-rose-500">*</span>
            </label>
            <input
              id="product-moq"
              name="moq"
              type="number"
              min="1"
              step="1"
              className="input"
              placeholder="50"
              value={state.moq}
              onChange={(e) => update('moq', e.target.value)}
              aria-invalid={Boolean(errors.moq) || undefined}
              aria-describedby={errors.moq ? 'err-moq' : undefined}
              required
            />
            {errors.moq ? (
              <p id="err-moq" className="mt-1 text-xs text-rose-600">
                {errors.moq}
              </p>
            ) : null}
          </div>
        </div>

        <div>
          <label className="label" htmlFor="product-name">
            상품명 (선택)
          </label>
          <input
            id="product-name"
            name="name"
            type="text"
            maxLength={500}
            className="input"
            placeholder="예: 고양이 자동급수기 2L"
            value={state.name}
            onChange={(e) => update('name', e.target.value)}
          />
        </div>

        <div>
          <label className="label" htmlFor="product-notes">
            메모 (선택)
          </label>
          <textarea
            id="product-notes"
            name="notes"
            rows={3}
            className="input resize-none"
            placeholder="공급자, 리드타임 등"
            value={state.notes}
            onChange={(e) => update('notes', e.target.value)}
          />
        </div>

        {errors.form ? (
          <p role="alert" className="text-sm text-rose-600">
            {errors.form}
          </p>
        ) : null}

        <div className="flex items-center justify-end gap-2">
          <button
            type="button"
            className="btn-secondary"
            onClick={() => router.back()}
            disabled={mutation.isPending}
          >
            취소
          </button>
          <button
            type="submit"
            className="btn-primary"
            disabled={mutation.isPending}
          >
            {mutation.isPending ? '분석 중…' : '분석하기'}
          </button>
        </div>
      </form>
    </div>
  );
}
