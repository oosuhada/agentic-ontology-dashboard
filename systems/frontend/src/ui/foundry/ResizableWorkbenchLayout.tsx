import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";

interface ResizableWorkbenchLayoutProps {
  storageKey: string;
  left?: ReactNode;
  main: ReactNode;
  right?: ReactNode;
  leftOpen?: boolean;
  rightOpen?: boolean;
  className?: string;
}

interface StoredWidths {
  left: number;
  right: number;
}

function loadWidths(storageKey: string): StoredWidths {
  try {
    const value = JSON.parse(window.localStorage.getItem(storageKey) ?? "null") as Partial<StoredWidths> | null;
    return {
      left: Math.max(196, Math.min(380, Number(value?.left) || 254)),
      right: Math.max(248, Math.min(480, Number(value?.right) || 318)),
    };
  } catch {
    return { left: 254, right: 318 };
  }
}

export function ResizableWorkbenchLayout({ storageKey, left, main, right, leftOpen = true, rightOpen = true, className = "" }: ResizableWorkbenchLayoutProps) {
  const [widths, setWidths] = useState(() => loadWidths(storageKey));
  const drag = useRef<{ side: "left" | "right"; startX: number; startWidth: number } | null>(null);

  useEffect(() => {
    window.localStorage.setItem(storageKey, JSON.stringify(widths));
  }, [storageKey, widths]);

  function setWidth(side: "left" | "right", width: number) {
    const limits = side === "left" ? [196, 380] : [248, 480];
    setWidths((current) => ({ ...current, [side]: Math.max(limits[0], Math.min(limits[1], width)) }));
  }

  function begin(side: "left" | "right", event: React.PointerEvent<HTMLDivElement>) {
    drag.current = { side, startX: event.clientX, startWidth: widths[side] };
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function move(event: React.PointerEvent<HTMLDivElement>) {
    if (!drag.current) return;
    const delta = event.clientX - drag.current.startX;
    setWidth(drag.current.side, drag.current.startWidth + (drag.current.side === "left" ? delta : -delta));
  }

  function end(event: React.PointerEvent<HTMLDivElement>) {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
    drag.current = null;
  }

  function keyboardResize(side: "left" | "right", event: KeyboardEvent<HTMLDivElement>) {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    const direction = event.key === "ArrowRight" ? 1 : -1;
    setWidth(side, widths[side] + direction * (side === "left" ? 16 : -16));
  }

  const columns = [
    leftOpen && left ? `${widths.left}px 5px` : "",
    "minmax(0, 1fr)",
    rightOpen && right ? `5px ${widths.right}px` : "",
  ].filter(Boolean).join(" ");

  const handle = (side: "left" | "right") => (
    <div
      className={`fd-resize-handle side-${side}`}
      role="separator"
      tabIndex={0}
      aria-label={`Resize ${side} workbench pane`}
      aria-orientation="vertical"
      aria-valuemin={side === "left" ? 196 : 248}
      aria-valuemax={side === "left" ? 380 : 480}
      aria-valuenow={widths[side]}
      onPointerDown={(event) => begin(side, event)}
      onPointerMove={move}
      onPointerUp={end}
      onDoubleClick={() => setWidth(side, side === "left" ? 254 : 318)}
      onKeyDown={(event) => keyboardResize(side, event)}
    />
  );

  return (
    <div className={`fd-resizable-workbench ${className}`.trim()} style={{ gridTemplateColumns: columns }}>
      {leftOpen && left ? <><aside className="fd-resizable-workbench__left">{left}</aside>{handle("left")}</> : null}
      <main className="fd-resizable-workbench__main">{main}</main>
      {rightOpen && right ? <>{handle("right")}<aside className="fd-resizable-workbench__right">{right}</aside></> : null}
    </div>
  );
}
