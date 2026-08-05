import { useEffect, useMemo, useRef, useState } from "react";
import { EChartCanvas, type DashboardChartOption } from "../dashboard/EChartCanvas";

type ComparisonKind = "bar" | "donut" | "line";

export interface ComparisonDatum {
  category: string;
  value: number;
}

export interface ComparisonPayload {
  kind: ComparisonKind;
  title: string;
  unit?: string;
  rows: ComparisonDatum[];
}

const DEFAULT_PAYLOAD: ComparisonPayload = {
  kind: "bar",
  title: "Node count by type",
  unit: "count",
  rows: [
    { category: "Part", value: 2736 },
    { category: "ProcessRun", value: 2758 },
    { category: "QualityMeasurement", value: 7570 },
  ],
};

export function parseComparisonPayload(search: string): ComparisonPayload {
  try {
    const raw = new URLSearchParams(search).get("payload");
    if (!raw) return DEFAULT_PAYLOAD;
    const parsed = JSON.parse(raw) as Partial<ComparisonPayload>;
    const kind = parsed.kind;
    const rows = Array.isArray(parsed.rows)
      ? parsed.rows
          .map((row) => ({
            category: String((row as ComparisonDatum).category ?? ""),
            value: Number((row as ComparisonDatum).value),
          }))
          .filter((row) => row.category && Number.isFinite(row.value))
      : [];
    if (!rows.length || !kind || !["bar", "donut", "line"].includes(kind)) return DEFAULT_PAYLOAD;
    return {
      kind,
      title: String(parsed.title || DEFAULT_PAYLOAD.title),
      unit: parsed.unit ? String(parsed.unit) : undefined,
      rows,
    };
  } catch {
    return DEFAULT_PAYLOAD;
  }
}

function chartOption(payload: ComparisonPayload): DashboardChartOption {
  const categories = payload.rows.map((row) => row.category);
  const values = payload.rows.map((row) => row.value);
  const shared = {
    animationDuration: 280,
    textStyle: { fontFamily: "Inter, Pretendard, sans-serif", color: "#3A4950" },
    tooltip: { trigger: payload.kind === "donut" ? "item" : "axis", confine: true },
  };
  if (payload.kind === "donut") {
    return {
      ...shared,
      legend: { bottom: 2, left: "center", type: "scroll", textStyle: { fontSize: 10 } },
      series: [{
        type: "pie",
        radius: ["50%", "72%"],
        center: ["50%", "43%"],
        label: { show: false },
        emphasis: { label: { show: true, formatter: "{b}\n{c}", fontSize: 12, fontWeight: 700 } },
        data: payload.rows.map((row) => ({ name: row.category, value: row.value })),
      }],
    };
  }
  if (payload.kind === "line") {
    return {
      ...shared,
      grid: { top: 18, right: 16, bottom: 34, left: 48, containLabel: true },
      xAxis: { type: "category", data: categories, boundaryGap: false, axisTick: { show: false } },
      yAxis: { type: "value", splitLine: { lineStyle: { color: "#ECEDEF" } } },
      series: [{ type: "line", data: values, smooth: true, symbolSize: 7, areaStyle: { opacity: 0.08 } }],
    };
  }
  return {
    ...shared,
    grid: { top: 14, right: 28, bottom: 26, left: 98, containLabel: true },
    xAxis: { type: "value", splitLine: { lineStyle: { color: "#ECEDEF" } } },
    yAxis: { type: "category", data: categories, axisTick: { show: false } },
    series: [{ type: "bar", data: values, barMaxWidth: 22, label: { show: true, position: "right" }, itemStyle: { borderRadius: [0, 4, 4, 0] } }],
  };
}

export function EChartsComparisonEmbed() {
  const payload = useMemo(() => parseComparisonPayload(window.location.search), []);
  const option = useMemo(() => chartOption(payload), [payload]);
  const hostRef = useRef<HTMLDivElement | null>(null);
  const startedAt = useRef(performance.now());
  const [readyMs, setReadyMs] = useState<number | null>(null);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const resolveReady = () => {
      const chart = host.querySelector<HTMLElement>("[data-chart-state='ready']");
      if (!chart || readyMs !== null) return;
      const elapsed = Math.round((performance.now() - startedAt.current) * 10) / 10;
      setReadyMs(elapsed);
      window.parent.postMessage({
        type: "oosu:echarts-ready",
        readyMs: elapsed,
        payloadBytes: new TextEncoder().encode(JSON.stringify(payload)).byteLength,
      }, "*");
    };
    resolveReady();
    const observer = new MutationObserver(resolveReady);
    observer.observe(host, { attributes: true, childList: true, subtree: true });
    return () => observer.disconnect();
  }, [payload, readyMs]);

  return (
    <main
      ref={hostRef}
      className="echarts-comparison-embed"
      data-comparison-renderer="echarts"
      data-renderer-ready={readyMs === null ? "false" : "true"}
    >
      <header>
        <div><small>REACT + APACHE ECHARTS</small><strong>{payload.title}</strong></div>
        <span>{readyMs === null ? "Rendering…" : `Ready ${readyMs.toFixed(1)} ms`}</span>
      </header>
      <section className="echarts-comparison-canvas">
        <EChartCanvas option={option} ariaLabel={`${payload.title} rendered with Apache ECharts`} />
      </section>
      <footer>
        <span>{payload.rows.length} data points</span>
        <span>{new TextEncoder().encode(JSON.stringify(payload)).byteLength.toLocaleString()} B payload</span>
      </footer>
    </main>
  );
}

