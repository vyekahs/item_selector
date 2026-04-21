'use client';

import { FormEvent, useState } from 'react';

import { useCreateFeedback } from '@/lib/api/mutations';
import { FeedbackCreateRequestSchema } from '@/lib/api/types';

export interface FeedbackFormProps {
  productId: number;
}

interface State {
  purchased: boolean;
  monthly_sales: string;
  actual_revenue: string;
  notes: string;
}

const INITIAL: State = {
  purchased: false,
  monthly_sales: '',
  actual_revenue: '',
  notes: '',
};

export function FeedbackForm({ productId }: FeedbackFormProps) {
  const mutation = useCreateFeedback();
  const [state, setState] = useState<State>(INITIAL);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<boolean>(false);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    setDone(false);

    const payload = {
      product_id: productId,
      purchased: state.purchased,
      monthly_sales: state.monthly_sales
        ? Number.parseInt(state.monthly_sales, 10)
        : null,
      actual_revenue: state.actual_revenue
        ? Number.parseFloat(state.actual_revenue)
        : null,
      notes: state.notes.trim() || null,
    };

    const result = FeedbackCreateRequestSchema.safeParse(payload);
    if (!result.success) {
      setError(result.error.issues[0]?.message ?? '입력 값을 확인하세요.');
      return;
    }

    try {
      await mutation.mutateAsync(result.data);
      setDone(true);
      setState(INITIAL);
    } catch (err) {
      setError(err instanceof Error ? err.message : '피드백 저장 실패');
    }
  };

  return (
    <form className="card flex flex-col gap-3" onSubmit={handleSubmit}>
      <h3 className="text-base font-semibold text-slate-900">
        60일 피드백 입력
      </h3>

      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={state.purchased}
          onChange={(e) =>
            setState((s) => ({ ...s, purchased: e.target.checked }))
          }
        />
        실제로 소싱했음
      </label>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div>
          <label className="label" htmlFor="fb-monthly">
            월 판매량 (개)
          </label>
          <input
            id="fb-monthly"
            type="number"
            min="0"
            className="input"
            value={state.monthly_sales}
            onChange={(e) =>
              setState((s) => ({ ...s, monthly_sales: e.target.value }))
            }
          />
        </div>
        <div>
          <label className="label" htmlFor="fb-revenue">
            실제 매출 (KRW)
          </label>
          <input
            id="fb-revenue"
            type="number"
            min="0"
            step="0.01"
            className="input"
            value={state.actual_revenue}
            onChange={(e) =>
              setState((s) => ({ ...s, actual_revenue: e.target.value }))
            }
          />
        </div>
      </div>

      <div>
        <label className="label" htmlFor="fb-notes">
          메모
        </label>
        <textarea
          id="fb-notes"
          rows={3}
          className="input resize-none"
          value={state.notes}
          onChange={(e) => setState((s) => ({ ...s, notes: e.target.value }))}
        />
      </div>

      {error ? (
        <p role="alert" className="text-sm text-rose-600">
          {error}
        </p>
      ) : null}
      {done ? (
        <p role="status" className="text-sm text-emerald-600">
          ✅ 피드백이 저장되었습니다.
        </p>
      ) : null}

      <div className="flex justify-end">
        <button
          type="submit"
          className="btn-primary"
          disabled={mutation.isPending}
        >
          {mutation.isPending ? '저장 중…' : '피드백 저장'}
        </button>
      </div>
    </form>
  );
}
