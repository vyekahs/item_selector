import '@testing-library/jest-dom/vitest';
import { vi } from 'vitest';

// Recharts' ResponsiveContainer uses ResizeObserver and inspects the
// parent's width via getBoundingClientRect() — both return 0 in jsdom,
// which suppresses chart rendering. Stub the observer + a sane width
// so child Radar/PolarGrid components mount.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
if (typeof globalThis.ResizeObserver === 'undefined') {
  (globalThis as { ResizeObserver?: unknown }).ResizeObserver =
    ResizeObserverStub;
}

// Force a non-zero size for layout measurement in jsdom.
if (typeof window !== 'undefined') {
  Object.defineProperty(HTMLElement.prototype, 'offsetWidth', {
    configurable: true,
    get: () => 480,
  });
  Object.defineProperty(HTMLElement.prototype, 'offsetHeight', {
    configurable: true,
    get: () => 240,
  });
}

// Recharts is heavy and depends on `ResizeObserver` + DOM measurements
// that are unreliable in jsdom. We do not need to render the chart's
// SVG to assert business behaviour, so stub it out.
vi.mock('recharts', () => {
  const Stub = ({ children }: { children?: unknown }) => children ?? null;
  return {
    Radar: Stub,
    RadarChart: Stub,
    PolarGrid: Stub,
    PolarAngleAxis: Stub,
    PolarRadiusAxis: Stub,
    ResponsiveContainer: Stub,
    Tooltip: Stub,
  };
});

// Next.js navigation hooks are not available outside the App Router
// runtime; provide minimal stubs that test cases can override.
vi.mock('next/navigation', () => {
  const router = {
    push: vi.fn(),
    replace: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
    refresh: vi.fn(),
    prefetch: vi.fn(),
  };
  return {
    useRouter: () => router,
    useSearchParams: () => new URLSearchParams(),
    useParams: () => ({}),
    usePathname: () => '/',
  };
});
