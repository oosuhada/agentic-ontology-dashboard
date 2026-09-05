export interface AdaptiveReliabilityCardSignals {
  declaredSpan: 6 | 12;
  empty: boolean;
  actionHero: boolean;
  textLength: number;
  controlCount: number;
  hasWideVisualization: boolean;
}

export const RELIABILITY_MASONRY_ROW_HEIGHT = 8;

/**
 * Reliability layout has two layers:
 * - semantic ordering is owned by role/runtime composition (and can be fed by
 *   an LLM planner),
 * - pixel geometry stays deterministic so a refresh never makes the UI jump
 *   unpredictably for the same content.
 *
 * The geometry layer may shrink genuinely compact cards, widen dense cards,
 * and lets empty states occupy one half-row so later cards can pack beside
 * them instead of inheriting a tall sibling's row height.
 */
export function preferredAdaptiveReliabilitySpan(
  signals: AdaptiveReliabilityCardSignals,
): 4 | 6 | 8 | 12 {
  if (signals.actionHero) return 12;
  if (signals.empty) return 6;
  if (signals.declaredSpan === 12) return 12;
  if (signals.hasWideVisualization) return 6;
  if (signals.controlCount >= 6 || signals.textLength >= 1600) return 8;
  if (signals.controlCount <= 1 && signals.textLength > 0 && signals.textLength <= 260) return 4;
  return 6;
}

export function adaptiveReliabilityRowSpan(
  contentHeight: number,
  rowGap: number,
  rowHeight = RELIABILITY_MASONRY_ROW_HEIGHT,
) {
  if (!Number.isFinite(contentHeight) || contentHeight <= 0) return 1;
  return Math.max(1, Math.ceil((contentHeight + rowGap) / (rowHeight + rowGap)));
}
