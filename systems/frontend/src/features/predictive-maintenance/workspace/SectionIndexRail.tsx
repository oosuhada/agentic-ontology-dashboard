import { useEffect, useMemo, useRef, useState, type RefObject } from "react";

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

const SECTION_ANCHOR_OFFSET = 18;

function sectionTargets(root: HTMLElement, sections: ReliabilitySectionIndexItem[]) {
  return sections
    .map((item) => root.querySelector<HTMLElement>(`[data-section-index-id="${item.id}"]`))
    .filter((item): item is HTMLElement => Boolean(item));
}

function closestSectionId(root: HTMLElement, targets: HTMLElement[]) {
  if (!targets.length) return null;
  if (root.scrollTop + root.clientHeight >= root.scrollHeight - 2) {
    return targets.at(-1)?.getAttribute("data-section-index-id") ?? null;
  }
  const rootTop = root.getBoundingClientRect().top;
  const anchor = rootTop + SECTION_ANCHOR_OFFSET + 2;
  let current = targets[0];
  for (const target of targets) {
    if (target.getBoundingClientRect().top <= anchor) current = target;
    else break;
  }
  return current.getAttribute("data-section-index-id");
}

export function SectionIndexRail({ containerRef, sections, english }: SectionIndexRailProps) {
  const sectionKey = useMemo(() => sections.map((item) => item.id).join("|"), [sections]);
  const [activeId, setActiveId] = useState(sections[0]?.id ?? null);
  const [previewId, setPreviewId] = useState<string | null>(null);
  const clickLockRef = useRef<string | null>(null);
  const releaseTimerRef = useRef<number | null>(null);

  useEffect(() => {
    clickLockRef.current = null;
    if (releaseTimerRef.current !== null) {
      window.clearTimeout(releaseTimerRef.current);
      releaseTimerRef.current = null;
    }
    setActiveId(sections[0]?.id ?? null);
    setPreviewId(null);
    const root = containerRef.current;
    if (!root || !sections.length) return undefined;
    const targets = sectionTargets(root, sections);
    if (!targets.length) return undefined;

    let frame = 0;
    const syncActive = () => {
      frame = 0;
      const lockedId = clickLockRef.current;
      if (lockedId) {
        const lockedTarget = targets.find(
          (target) => target.getAttribute("data-section-index-id") === lockedId,
        );
        if (lockedTarget) {
          const rootRect = root.getBoundingClientRect();
          const targetTop = lockedTarget.getBoundingClientRect().top;
          const reachedAnchor = Math.abs(targetTop - (rootRect.top + SECTION_ANCHOR_OFFSET)) <= 4;
          const reachedBottom =
            root.scrollTop + root.clientHeight >= root.scrollHeight - 2
            && targetTop < rootRect.bottom;
          if (!reachedAnchor && !reachedBottom) return;
        }
        clickLockRef.current = null;
      }
      const next = closestSectionId(root, targets);
      if (next) setActiveId(next);
    };
    const scheduleSync = () => {
      if (frame) return;
      frame = window.requestAnimationFrame(syncActive);
    };

    syncActive();
    root.addEventListener("scroll", scheduleSync, { passive: true });
    window.addEventListener("resize", scheduleSync);
    return () => {
      root.removeEventListener("scroll", scheduleSync);
      window.removeEventListener("resize", scheduleSync);
      if (frame) window.cancelAnimationFrame(frame);
      if (releaseTimerRef.current !== null) {
        window.clearTimeout(releaseTimerRef.current);
        releaseTimerRef.current = null;
      }
      clickLockRef.current = null;
    };
  }, [containerRef, sectionKey]);

  if (sections.length < 2) return null;

  function goTo(id: string) {
    const root = containerRef.current;
    const target = root?.querySelector<HTMLElement>(`[data-section-index-id="${id}"]`);
    if (!root || !target) return;
    clickLockRef.current = id;
    setActiveId(id);
    target.scrollIntoView({ behavior: "smooth", block: "start" });
    if (releaseTimerRef.current !== null) window.clearTimeout(releaseTimerRef.current);
    releaseTimerRef.current = window.setTimeout(() => {
      clickLockRef.current = null;
      const next = closestSectionId(root, sectionTargets(root, sections));
      if (next) setActiveId(next);
      releaseTimerRef.current = null;
    }, 900);
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
                data-section-id={item.id}
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
