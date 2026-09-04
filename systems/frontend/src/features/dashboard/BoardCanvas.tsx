import { DashboardGridCanvas, type DashboardGridCanvasProps } from "./DashboardGridCanvas";

/**
 * Compatibility wrapper retained for existing imports and tests.
 * New dashboard work should import DashboardGridCanvas directly.
 */
export function BoardCanvas(props: DashboardGridCanvasProps) {
  return <DashboardGridCanvas {...props} />;
}
