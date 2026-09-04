export const CHART_SERIES = [
  "#0C1C74",
  "#E64D2B",
  "#00A396",
  "#D1970C",
  "#7861DB",
  "#29A634",
  "#DA2D6F",
  "#5F6B7B",
] as const;

export const CHART_NEUTRAL = {
  canvas: "#F7F8F9",
  border: "#DCDCDD",
  muted: "#5F6B7B",
  ink: "#3A4950",
  white: "#FFFFFF",
} as const;

export const CHART_SEMANTIC = {
  info: "#0C1C74",
  success: "#29A634",
  warning: "#D1970C",
  danger: "#DB0714",
  accent: "#E64D2B",
} as const;

function stableHash(value: string) {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return Math.abs(hash >>> 0);
}

export function categoryColor(category: string) {
  return CHART_SERIES[stableHash(category) % CHART_SERIES.length];
}

export function withAlpha(hex: string, alpha: number) {
  const normalized = hex.replace("#", "");
  const value = Number.parseInt(normalized, 16);
  const red = (value >> 16) & 255;
  const green = (value >> 8) & 255;
  const blue = value & 255;
  return `rgba(${red}, ${green}, ${blue}, ${alpha})`;
}
