import { ArrowLeft, ExternalLink, GitCompareArrows } from "lucide-react";
import { navigate } from "../../routing";
import beforeAnalysis from "../../../../../docs/ui/palantir-overhaul/final/1440x1000/analysis.png";
import beforeOntology from "../../../../../docs/ui/palantir-overhaul/final/1440x1000/ontology.png";
import afterPath from "../../../../../docs/ui/palantir-integration/final/analysis-path.png";
import afterCanvas from "../../../../../docs/ui/palantir-integration/final/analysis-canvas.png";
import afterGraph from "../../../../../docs/ui/palantir-integration/final/analysis-graph.png";
import afterForecast from "../../../../../docs/ui/palantir-integration/final/analysis-forecast.png";
import afterSelection from "../../../../../docs/ui/palantir-integration/final/ontology-selection.png";
import afterTraversal from "../../../../../docs/ui/palantir-integration/final/ontology-traversal.png";

const comparisons = [
  { id: "path", title: "Analysis · Typed Path", detail: "DataPill metadata and compatible card contracts", before: beforeAnalysis, after: afterPath },
  { id: "canvas", title: "Analysis · Free-form Canvas", detail: "Multiple canvases, movable cards, hidden computational nodes", before: beforeAnalysis, after: afterCanvas },
  { id: "graph", title: "Analysis · Dependency Graph", detail: "Existing nodes and edges projected with computation collapse", before: beforeAnalysis, after: afterGraph },
  { id: "forecast", title: "Analysis · Time Series Forecast", detail: "Training range, forecast editor, confidence band, event markers", before: beforeAnalysis, after: afterForecast },
  { id: "selection", title: "Ontology · ObjectSet Selection", detail: "Replace, union, intersection, and difference semantics", before: beforeOntology, after: afterSelection },
  { id: "traversal", title: "Ontology · Linked Traversal", detail: "Selected roots merged through the existing traversal API", before: beforeOntology, after: afterTraversal },
];

export function ReferenceGallery() {
  return (
    <main className="reference-gallery-page">
      <header className="reference-gallery-header">
        <div><span className="section-label">PALANTIR UI/UX INTEGRATION</span><h1><GitCompareArrows size={18} /> Before / After Reference</h1><p>The left column uses the tagged pre-integration 1440×1000 baseline. The right column uses browser captures generated after the three implementation phases.</p></div>
        <button type="button" onClick={() => navigate("/app")}><ArrowLeft size={12} /> Back to application</button>
      </header>
      <section className="reference-gallery-grid">
        {comparisons.map((item) => (
          <article className="reference-comparison-card" key={item.id}>
            <header><div><span className="section-label">{item.id.toUpperCase()}</span><h2>{item.title}</h2></div><span>{item.detail}</span></header>
            <div className="reference-comparison-images">
              <figure><figcaption>BEFORE · tag pre-palantir-uiux-integration-20260803-1552</figcaption><a href={item.before} target="_blank" rel="noreferrer"><img src={item.before} alt={`${item.title} before integration`} /></a></figure>
              <figure><figcaption>AFTER · current implementation <ExternalLink size={9} /></figcaption><a href={item.after} target="_blank" rel="noreferrer"><img src={item.after} alt={`${item.title} after integration`} /></a></figure>
            </div>
          </article>
        ))}
      </section>
    </main>
  );
}
