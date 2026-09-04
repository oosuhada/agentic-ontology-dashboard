import { useEffect } from "react";

const THEME_KEY = "ontology-dashboard:reliability-theme";
const LOCALE_KEY = "ontology-dashboard:reliability-locale";

export function isReliabilityPreviewLocation(): boolean {
  const queryEnabled = new URLSearchParams(window.location.search).get("workspace_shell") === "reliability";
  if (queryEnabled) return true;
  const basePath = import.meta.env.BASE_URL.replace(/\/+$/, "");
  const pathname = window.location.pathname;
  if (basePath === "") {
    return pathname === "/" || pathname === "/app" || /^\/app\/projects\/[^/]+\/operations/.test(pathname);
  }
  if (basePath !== "/reliability-preview") return false;
  return pathname.startsWith(`${basePath}/app/projects/`)
    && (pathname.includes("/operations") || pathname.includes("/operations"));
}

export function ReliabilityRoutePlaceholder() {
  const theme = window.localStorage.getItem(THEME_KEY) === "dark" ? "dark" : "light";
  const locale = window.localStorage.getItem(LOCALE_KEY) === "en-US" ? "en-US" : "ko-KR";

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.lang = locale;
  }, [locale, theme]);

  return (
    <main className={`reliability-route-placeholder is-${theme}`} aria-busy="true" aria-label="Reliability workspace 준비 중">
      <header className="reliability-route-placeholder__topbar">
        <strong>Hanbit Tech</strong>
        <span />
      </header>
      <div className="reliability-route-placeholder__body">
        <aside aria-hidden="true">
          <i className="wide" /><i /><i /><i /><b />
        </aside>
        <section aria-hidden="true">
          <i className="eyebrow" />
          <i className="title" />
          <i className="copy" />
          <article>
            <i className="kicker" /><i className="hero" /><i className="copy" />
            <div><b /><b /><b /><b /></div>
          </article>
          <div className="reliability-route-placeholder__cards"><article /><article /></div>
        </section>
      </div>
      <footer aria-hidden="true"><i /><i /><i /><i /></footer>
    </main>
  );
}
