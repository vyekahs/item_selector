'use client';

import type { CategoryNode } from '@/lib/api/types';

export interface KeywordFilterBarProps {
  categories: CategoryNode[];
  categoryId: number | null;
  onCategoryChange: (id: number | null) => void;
  limit: number;
  onLimitChange: (n: number) => void;
  minScore: number;
  onMinScoreChange: (n: number) => void;
  includeExcluded: boolean;
  onIncludeExcludedChange: (v: boolean) => void;
}

function flattenCategories(
  nodes: CategoryNode[],
  depth = 0,
): Array<{ id: number; label: string }> {
  const out: Array<{ id: number; label: string }> = [];
  for (const node of nodes) {
    const prefix = depth ? `${'  '.repeat(depth)}└ ` : '';
    out.push({ id: node.id, label: `${prefix}${node.name}` });
    if (node.children && node.children.length) {
      out.push(...flattenCategories(node.children, depth + 1));
    }
  }
  return out;
}

export function KeywordFilterBar(props: KeywordFilterBarProps) {
  const options = flattenCategories(props.categories);

  return (
    <section
      aria-label="키워드 필터"
      className="card flex flex-wrap items-end gap-3"
    >
      <div className="min-w-[180px] flex-1">
        <label className="label" htmlFor="filter-category">
          카테고리
        </label>
        <select
          id="filter-category"
          className="input"
          value={props.categoryId ?? ''}
          onChange={(e) =>
            props.onCategoryChange(e.target.value ? Number(e.target.value) : null)
          }
        >
          <option value="">전체</option>
          {options.map((opt) => (
            <option key={opt.id} value={opt.id}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      <div className="w-28">
        <label className="label" htmlFor="filter-limit">
          개수
        </label>
        <select
          id="filter-limit"
          className="input"
          value={props.limit}
          onChange={(e) => props.onLimitChange(Number(e.target.value))}
        >
          <option value={10}>10</option>
          <option value={20}>20</option>
          <option value={50}>50</option>
        </select>
      </div>

      <div className="w-32">
        <label className="label" htmlFor="filter-minscore">
          최소 점수
        </label>
        <input
          id="filter-minscore"
          type="number"
          min={0}
          max={100}
          className="input"
          value={props.minScore}
          onChange={(e) =>
            props.onMinScoreChange(Number.parseFloat(e.target.value) || 0)
          }
        />
      </div>

      <label className="mb-1 flex items-center gap-2 text-sm text-slate-700">
        <input
          type="checkbox"
          className="h-4 w-4"
          checked={props.includeExcluded}
          onChange={(e) => props.onIncludeExcludedChange(e.target.checked)}
        />
        제외된 키워드 포함
      </label>
    </section>
  );
}
