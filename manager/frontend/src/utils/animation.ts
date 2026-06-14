import type { CSSProperties } from 'react'

const STAGGER_STEP_MS = 40
const STAGGER_MAX_MS = 320

/** Inline style for staggered entrance animations (use with animate-fade-in / animate-fade-in-up). */
export function staggerDelay(index: number, step: number = STAGGER_STEP_MS, max: number = STAGGER_MAX_MS): CSSProperties {
  return { animationDelay: `${Math.min(index * step, max)}ms` }
}
