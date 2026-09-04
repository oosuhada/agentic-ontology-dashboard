export function observeElementSize(
  element: Element,
  onSize: (width: number, height: number) => void,
): () => void {
  if (typeof ResizeObserver === "undefined") return () => undefined;
  let frame = 0;
  let previousWidth = -1;
  let previousHeight = -1;
  const observer = new ResizeObserver(([entry]) => {
    const { width, height } = entry.contentRect;
    if (Math.abs(width - previousWidth) < 0.5 && Math.abs(height - previousHeight) < 0.5) return;
    previousWidth = width;
    previousHeight = height;
    window.cancelAnimationFrame(frame);
    frame = window.requestAnimationFrame(() => onSize(width, height));
  });
  observer.observe(element);
  return () => {
    window.cancelAnimationFrame(frame);
    observer.disconnect();
  };
}

const BATCHED_RESIZE_OBSERVER = Symbol.for("ontology-dashboard.batched-resize-observer");

export function installBatchedResizeObserver(): void {
  if (typeof window === "undefined" || typeof window.ResizeObserver === "undefined") return;
  const target = window as typeof window & { [BATCHED_RESIZE_OBSERVER]?: boolean };
  if (target[BATCHED_RESIZE_OBSERVER]) return;
  const NativeResizeObserver = window.ResizeObserver;

  class AnimationFrameResizeObserver implements ResizeObserver {
    private readonly observer: ResizeObserver;
    private frame = 0;
    private pendingEntries: ResizeObserverEntry[] = [];

    constructor(callback: ResizeObserverCallback) {
      this.observer = new NativeResizeObserver((entries) => {
        this.pendingEntries = entries;
        window.cancelAnimationFrame(this.frame);
        this.frame = window.requestAnimationFrame(() => {
          const nextEntries = this.pendingEntries;
          this.pendingEntries = [];
          callback(nextEntries, this);
        });
      });
    }

    observe(targetElement: Element, options?: ResizeObserverOptions): void {
      this.observer.observe(targetElement, options);
    }

    unobserve(targetElement: Element): void {
      this.observer.unobserve(targetElement);
    }

    disconnect(): void {
      window.cancelAnimationFrame(this.frame);
      this.pendingEntries = [];
      this.observer.disconnect();
    }
  }

  window.ResizeObserver = AnimationFrameResizeObserver;
  target[BATCHED_RESIZE_OBSERVER] = true;
}

export function installResizeObserverErrorGuard(): () => void {
  const handler = (event: ErrorEvent) => {
    if (event.message === "ResizeObserver loop completed with undelivered notifications." || event.message === "ResizeObserver loop limit exceeded") {
      event.preventDefault();
      event.stopImmediatePropagation();
    }
  };
  window.addEventListener("error", handler, true);
  return () => window.removeEventListener("error", handler, true);
}
