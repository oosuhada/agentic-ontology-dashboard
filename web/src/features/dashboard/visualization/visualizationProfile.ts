import type {
  RenderSpec,
  VisualizationCandidate,
  VisualizationFieldMapping,
  VisualizationFieldProfile,
  VisualizationKind,
  VisualizationRecommendation,
  VisualizationSettings,
} from "../types";
import { VISUALIZATION_REGISTRY } from "./visualizationRegistry";

type Row = Record<string, unknown>;

function dateLike(value: unknown) {
  if (value instanceof Date) return true;
  if (typeof value !== "string" || value.length < 6) return false;
  return /[-/:T]/.test(value) && Number.isFinite(Date.parse(value));
}

function identifierLike(id: string, values: unknown[]) {
  return /(^id$|_id$|uuid|key|code)/i.test(id)
    || (values.length > 4 && new Set(values.map(String)).size / values.length > 0.95 && values.every((value) => typeof value === "string"));
}

export function profileRows(rows: Row[]): VisualizationFieldProfile[] {
  const sample = rows.slice(0, 500);
  const fields = Array.from(new Set(sample.flatMap((row) => Object.keys(row))));
  return fields.map((id) => {
    const raw = sample.map((row) => row[id]);
    const present = raw.filter((value) => value !== null && value !== undefined && value !== "");
    const numeric = present.filter((value) => typeof value === "number" || (typeof value === "string" && value.trim() !== "" && Number.isFinite(Number(value))));
    const dates = present.filter(dateLike);
    const booleans = present.filter((value) => typeof value === "boolean");
    let physicalType: VisualizationFieldProfile["physical_type"] = "unknown";
    if (present.length && numeric.length === present.length) physicalType = "number";
    else if (present.length && dates.length === present.length) physicalType = "date";
    else if (present.length && booleans.length === present.length) physicalType = "boolean";
    else if (present.length && present.every((value) => typeof value === "string")) physicalType = "string";
    else if (present.length) physicalType = "mixed";
    const distinct = new Set(present.map((value) => String(value))).size;
    const ratio = present.length ? distinct / present.length : 0;
    let semantic: VisualizationFieldProfile["semantic_type"] = "text";
    if (/lat(itude)?|lon(gitude)?/i.test(id)) semantic = "geo";
    else if (identifierLike(id, present)) semantic = "identifier";
    else if (physicalType === "date" || /(date|time|timestamp|month|week|year|day)$/i.test(id)) semantic = "temporal";
    else if (physicalType === "number") semantic = "quantitative";
    else if (physicalType === "boolean") semantic = "boolean";
    else if (distinct <= Math.max(12, Math.ceil(present.length * 0.2))) semantic = "categorical";
    const comparable = semantic === "quantitative"
      ? present.map(Number).filter(Number.isFinite)
      : semantic === "temporal" ? present.map(String).sort() : [];
    return {
      id,
      semantic_type: semantic,
      physical_type: physicalType,
      null_ratio: sample.length ? (sample.length - present.length) / sample.length : 0,
      distinct_count: distinct,
      cardinality_ratio: ratio,
      min: comparable.length ? comparable[0] : undefined,
      max: comparable.length ? comparable[comparable.length - 1] : undefined,
      sample_values: present.slice(0, 5) as Array<string | number | boolean>,
    };
  });
}

function candidate(kind: VisualizationKind, score: number, fieldMapping: VisualizationFieldMapping, reasonCodes: string[], rationale: string): VisualizationCandidate {
  return { kind, score: Math.min(1, Math.max(0, score)), field_mapping: fieldMapping, reason_codes: reasonCodes, rationale };
}

function hashProfile(profile: VisualizationFieldProfile[]) {
  const source = JSON.stringify(profile.map(({ id, semantic_type, distinct_count, null_ratio }) => [id, semantic_type, distinct_count, Math.round(null_ratio * 100)]));
  let hash = 0;
  for (let index = 0; index < source.length; index += 1) hash = (Math.imul(31, hash) + source.charCodeAt(index)) | 0;
  return `profile-${Math.abs(hash)}`;
}

export function recommendVisualization(rows: Row[], fallback?: RenderSpec | null): VisualizationRecommendation {
  const profile = profileRows(rows);
  const temporal = profile.find((field) => field.semantic_type === "temporal");
  const quantitative = profile.filter((field) => field.semantic_type === "quantitative");
  const categorical = profile.filter((field) => field.semantic_type === "categorical" || field.semantic_type === "boolean");
  const candidates: VisualizationCandidate[] = [];
  const firstNumeric = quantitative[0];
  const secondNumeric = quantitative[1];
  const firstCategory = categorical[0] ?? profile.find((field) => field.semantic_type === "identifier");
  const secondCategory = categorical[1];

  if (rows.length <= 2 && firstNumeric) candidates.push(candidate("metric", 0.96, { value: firstNumeric.id }, ["small_summary_record", "numeric_measure"], `Small result set with numeric measure ${firstNumeric.id}.`));
  if (temporal && firstNumeric) {
    candidates.push(candidate("line", 0.94, { x: temporal.id, y: firstNumeric.id, series: firstCategory?.id }, ["temporal_sequence", "continuous_numeric_measure"], `${temporal.id} is ordered time data and ${firstNumeric.id} is quantitative.`));
    candidates.push(candidate("area", 0.86, { x: temporal.id, y: firstNumeric.id, series: firstCategory?.id }, ["temporal_sequence", "magnitude_emphasis"], `Area emphasizes the magnitude of ${firstNumeric.id} over time.`));
  }
  if (firstCategory && firstNumeric) {
    candidates.push(candidate("bar", firstCategory.distinct_count > 20 ? 0.82 : 0.9, { x: firstCategory.id, y: firstNumeric.id }, ["categorical_comparison", "numeric_measure"], `${firstCategory.id} categories can be compared by ${firstNumeric.id}.`));
    if (firstCategory.distinct_count > 1 && firstCategory.distinct_count <= 8) candidates.push(candidate("pie", 0.75, { x: firstCategory.id, value: firstNumeric.id }, ["low_category_cardinality", "part_to_whole"], `${firstCategory.distinct_count} categories are suitable for a donut composition.`));
  }
  if (firstCategory && secondCategory && firstNumeric) {
    candidates.push(candidate("stacked_bar", 0.84, { x: firstCategory.id, y: firstNumeric.id, series: secondCategory.id }, ["two_categorical_dimensions", "composition_comparison"], `${secondCategory.id} can be stacked within ${firstCategory.id}.`));
    candidates.push(candidate("heatmap", 0.8, { row: firstCategory.id, column: secondCategory.id, value: firstNumeric.id }, ["categorical_matrix", "numeric_intensity"], `${firstCategory.id} × ${secondCategory.id} forms a matrix for ${firstNumeric.id}.`));
  }
  if (firstNumeric) candidates.push(candidate("histogram", 0.78, { value: firstNumeric.id }, ["numeric_distribution"], `${firstNumeric.id} can be inspected as a distribution.`));
  if (firstNumeric && secondNumeric) candidates.push(candidate("scatter", 0.87, { x: firstNumeric.id, y: secondNumeric.id, series: firstCategory?.id }, ["two_numeric_measures", "relationship"], `${firstNumeric.id} and ${secondNumeric.id} can be compared for correlation.`));
  candidates.push(candidate("table", profile.length > 6 ? 0.88 : 0.62, {}, ["detail_fallback", "all_fields_available"], "Table preserves every available field without aggregation."));

  const fallbackKind = fallback?.kind;
  if (fallbackKind && VISUALIZATION_REGISTRY.some((item) => item.kind === fallbackKind) && !candidates.some((item) => item.kind === fallbackKind)) {
    candidates.push(candidate(fallbackKind as VisualizationKind, 0.65, {
      x: fallback?.x_field,
      y: fallback?.y_field,
      value: fallback?.value_field,
      series: fallback?.group_field,
    }, ["api_render_spec"], "API render specification provides a compatible fallback."));
  }

  const unique = Array.from(new Map(candidates.sort((left, right) => right.score - left.score).map((item) => [item.kind, item])).values());
  const recommended = unique[0] ?? candidate("table", 1, {}, ["safe_fallback"], "No compatible quantitative mapping was detected.");
  const supported = new Set(unique.map((item) => item.kind));
  const unavailable = VISUALIZATION_REGISTRY
    .filter((item) => !supported.has(item.kind))
    .map((item) => ({ kind: item.kind, reason: unavailableReason(item.kind, quantitative.length, categorical.length, Boolean(temporal)) }));
  return { profile, profile_hash: hashProfile(profile), recommended, alternatives: unique.slice(1, 6), unavailable };
}

function unavailableReason(kind: VisualizationKind, numericCount: number, categoryCount: number, hasTemporal: boolean) {
  if (kind === "scatter") return "Two quantitative fields are required.";
  if (kind === "heatmap" || kind === "stacked_bar") return "Two categorical dimensions and one quantitative field are required.";
  if (kind === "line" || kind === "area") return hasTemporal ? "A quantitative value field is required." : "A temporal field and quantitative value are required.";
  if (kind === "pie" || kind === "bar") return categoryCount ? "A quantitative value field is required." : "A categorical field and quantitative value are required.";
  if (kind === "histogram" || kind === "metric") return numericCount ? "Current mapping is unavailable." : "A quantitative field is required.";
  return "The current field profile is not compatible.";
}

export function visualizationSettings(value: unknown): VisualizationSettings {
  if (!value || typeof value !== "object") return { version: 1, mode: "auto" };
  const source = value as Partial<VisualizationSettings>;
  return {
    version: 1,
    mode: source.mode === "manual" ? "manual" : "auto",
    kind: source.kind,
    field_mapping: source.field_mapping,
    aggregation: source.aggregation,
    orientation: source.orientation,
    stack: source.stack,
    legend: source.legend,
    labels: source.labels,
    curve: source.curve,
    color_strategy: source.color_strategy,
    pie_style: source.pie_style,
    recommendation_revision: source.recommendation_revision,
  };
}

export function resolveVisualizationSpec(base: RenderSpec, recommendation: VisualizationRecommendation, settings: VisualizationSettings): RenderSpec {
  const selected = settings.mode === "manual" && settings.kind
    ? [recommendation.recommended, ...recommendation.alternatives].find((item) => item.kind === settings.kind)
    : recommendation.recommended;
  const mapping = settings.mode === "manual" ? { ...selected?.field_mapping, ...settings.field_mapping } : selected?.field_mapping;
  return {
    ...base,
    kind: settings.mode === "manual" && settings.kind ? settings.kind : recommendation.recommended.kind,
    x_field: mapping?.x ?? mapping?.column ?? base.x_field,
    y_field: mapping?.y ?? base.y_field,
    value_field: mapping?.value ?? base.value_field,
    group_field: mapping?.series ?? mapping?.row ?? base.group_field,
    aggregation: settings.aggregation ?? base.aggregation ?? "avg",
    orientation: settings.orientation ?? base.orientation ?? "vertical",
    stack: settings.stack ?? (settings.kind === "stacked_bar" ? "normal" : base.stack ?? "off"),
    legend: settings.legend ?? base.legend ?? "auto",
    labels: settings.labels ?? base.labels ?? "auto",
    curve: settings.curve ?? base.curve ?? "smooth",
    color_strategy: settings.color_strategy ?? base.color_strategy ?? "categorical",
    pie_style: settings.pie_style ?? base.pie_style ?? "donut",
  };
}
