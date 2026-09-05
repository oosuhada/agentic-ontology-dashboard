import { useEffect, useMemo, useState, type RefObject } from "react";

export interface ReliabilitySectionIndexItem {
  id: string;
  label: string;
  summary: string;
}

interface SectionIndexRailProps {
  containerRef: RefObject<HTMLElement | null>;
  sections: ReliabilitySectionIndexItem[];
  english: boolean;
}

export function SectionIndexRail({ containerRef, sections, english }: SectionIndexRailProps) {
  const sectionKey = useMemo(() => sections.map((item) => item.id).join("|"), [sections]);
  const [activeId, setActiveId] = useState(sections[0]?.id ?? null);
  const [previewId, setPreviewId] = useState<string | null>(null);

  useEffect(() => {
    setActiveId(sections[0]?.id ?? null);
    setPreviewId(null);
    const root = containerRef.current;
    if (!root || !sections.length) return undefined;
    const targets = sections
      .map((item) => root.querySelector<HTMLElement>(`[data-section-index-id="${item.id}"]`))
      .filter((item): item is HTMLElement => Boolean(item));
    if (!targets.length) return undefined;

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((left, right) => (
            Math.abs(left.boundingClientRect.top - root.getBoundingClientRect().top)
            - Math.abs(right.boundingClientRect.top - root.getBoundingClientRect().top)
          ));
        const next = visible[0]?.target.getAttribute("data-section-index-id");
        if (next) setActiveId(next);
      },
      {
        root,
        rootMargin: "-8% 0px -72% 0px",
        threshold: [0, 0.05, 0.2, 0.5],
      },
    );
    for (const target of targets) observer.observe(target);
    return () => observer.disconnect();
  }, [containerRef, sectionKey]);

  if (sections.length < 2) return null;

  function goTo(id: string) {
    const target = containerRef.current?.querySelector<HTMLElement>(`[data-section-index-id="${id}"]`);
    if (!target) return;
    setActiveId(id);
    target.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  return (
    <nav className="rw-section-index" aria-label={english ? "Page section index" : "화면 섹션 인덱스"}>
      <div className="rw-section-index__track">
        {sections.map((item) => {
          const active = item.id === activeId;
          const preview = item.id === previewId;
          return (
            <div className="rw-section-index__item" key={item.id}>
              <button
                type="button"
                className={active ? "is-active" : ""}
                aria-label={item.label}
                aria-current={active ? "location" : undefined}
                onPointerEnter={() => setPreviewId(item.id)}
                onPointerLeave={() => setPreviewId(null)}
                onFocus={() => setPreviewId(item.id)}
                onBlur={() => setPreviewId(null)}
                onClick={() => goTo(item.id)}
              >
                <span />
              </button>
              {preview ? (
                <aside className="rw-section-index__preview" role="status">
                  <strong>{item.label}</strong>
                  <p>{item.summary}</p>
                  <small>{active ? (english ? "Current section" : "현재 섹션") : (english ? "Click to move" : "클릭하여 이동")}</small>
                </aside>
              ) : null}
            </div>
          );
        })}
      </div>
    </nav>
  );
}

export default SectionIndexRail;
