import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import { ScoreBadge, scoreTier } from '@/components/ScoreBadge';

describe('scoreTier', () => {
  it('maps numeric ranges to qualitative tiers', () => {
    expect(scoreTier(95)).toBe('excellent');
    expect(scoreTier(85)).toBe('excellent');
    expect(scoreTier(80)).toBe('good');
    expect(scoreTier(70)).toBe('good');
    expect(scoreTier(60)).toBe('ok');
    expect(scoreTier(45)).toBe('warn');
    expect(scoreTier(20)).toBe('bad');
    expect(scoreTier(0)).toBe('bad');
  });
});

describe('<ScoreBadge />', () => {
  it('renders a rounded score with the matching tier attribute', () => {
    render(<ScoreBadge score={87.4} />);
    const pill = screen.getByTestId('score-pill');
    expect(pill).toHaveTextContent('87점');
    expect(pill.dataset.tier).toBe('excellent');
  });

  it('shows GO recommendation badge with positive label', () => {
    render(<ScoreBadge score={83} recommendation="GO" />);
    const rec = screen.getByTestId('recommendation-pill');
    expect(rec.dataset.recommendation).toBe('GO');
    expect(rec).toHaveTextContent(/GO/);
  });

  it('marks PASS recommendations clearly', () => {
    render(<ScoreBadge score={32} recommendation="PASS" />);
    const rec = screen.getByTestId('recommendation-pill');
    expect(rec.dataset.recommendation).toBe('PASS');
    const score = screen.getByTestId('score-pill');
    expect(score.dataset.tier).toBe('bad');
  });

  it('omits the recommendation pill when not provided', () => {
    render(<ScoreBadge score={50} />);
    expect(screen.queryByTestId('recommendation-pill')).toBeNull();
  });
});
