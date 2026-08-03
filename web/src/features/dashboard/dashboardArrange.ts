import { useCallback, useEffect, useReducer, useRef, type PointerEventHandler } from "react";
import type { DashboardMode } from "./types";

export type DashboardArrangePhase = "view" | "press-armed" | "arranging" | "dragging" | "resizing" | "saving";

export type DashboardArrangeAction =
  | { type: "ARM" }
  | { type: "CANCEL" }
  | { type: "ENTER" }
  | { type: "DRAG_START" }
  | { type: "DRAG_STOP" }
  | { type: "RESIZE_START" }
  | { type: "RESIZE_STOP" }
  | { type: "SAVE_START" }
  | { type: "SAVE_END" }
  | { type: "EXIT" };

export function dashboardArrangeReducer(state: DashboardArrangePhase, action: DashboardArrangeAction): DashboardArrangePhase {
  switch (action.type) {
    case "ARM": return state === "view" ? "press-armed" : state;
    case "CANCEL": return state === "press-armed" ? "view" : state;
    case "ENTER": return "arranging";
    case "DRAG_START": return state === "arranging" ? "dragging" : state;
    case "DRAG_STOP": return state === "dragging" ? "arranging" : state;
    case "RESIZE_START": return state === "arranging" ? "resizing" : state;
    case "RESIZE_STOP": return state === "resizing" ? "arranging" : state;
    case "SAVE_START": return state === "arranging" ? "saving" : state;
    case "SAVE_END": return state === "saving" ? "arranging" : state;
    case "EXIT": return "view";
  }
}

export function isArrangeInteractiveTarget(target: EventTarget | null) {
  return target instanceof Element && Boolean(target.closest(
    "button,input,select,textarea,a,[role='button'],[role='link'],[contenteditable='true'],.react-resizable-handle,.dashboard-board-drag-handle",
  ));
}

interface LongPressState {
  pointerId: number;
  x: number;
  y: number;
}

export function useDashboardArrangeMode({
  mode,
  onEnter,
  thresholdMs = 500,
  movementThreshold = 8,
}: {
  mode: DashboardMode;
  onEnter: () => void;
  thresholdMs?: number;
  movementThreshold?: number;
}) {
  const [phase, dispatch] = useReducer(dashboardArrangeReducer, mode === "edit" ? "arranging" : "view");
  const timerRef = useRef<number | null>(null);
  const pressRef = useRef<LongPressState | null>(null);

  const cancelPress = useCallback(() => {
    if (timerRef.current !== null) window.clearTimeout(timerRef.current);
    timerRef.current = null;
    pressRef.current = null;
    dispatch({ type: "CANCEL" });
  }, []);

  useEffect(() => {
    if (mode === "edit") dispatch({ type: "ENTER" });
    else dispatch({ type: "EXIT" });
  }, [mode]);

  useEffect(() => {
    window.addEventListener("scroll", cancelPress, true);
    return () => {
      window.removeEventListener("scroll", cancelPress, true);
      cancelPress();
    };
  }, [cancelPress]);

  const onPointerDownCapture: PointerEventHandler<HTMLElement> = useCallback((event) => {
    if (mode === "edit" || isArrangeInteractiveTarget(event.target)) return;
    if (event.pointerType === "mouse" && event.button !== 0) return;
    cancelPress();
    pressRef.current = { pointerId: event.pointerId, x: event.clientX, y: event.clientY };
    dispatch({ type: "ARM" });
    timerRef.current = window.setTimeout(() => {
      timerRef.current = null;
      pressRef.current = null;
      dispatch({ type: "ENTER" });
      onEnter();
    }, thresholdMs);
  }, [cancelPress, mode, onEnter, thresholdMs]);

  const onPointerMoveCapture: PointerEventHandler<HTMLElement> = useCallback((event) => {
    const press = pressRef.current;
    if (!press || press.pointerId !== event.pointerId) return;
    if (Math.hypot(event.clientX - press.x, event.clientY - press.y) >= movementThreshold) cancelPress();
  }, [cancelPress, movementThreshold]);

  const onPointerEndCapture: PointerEventHandler<HTMLElement> = useCallback(() => cancelPress(), [cancelPress]);

  return {
    phase,
    dispatch,
    longPressHandlers: {
      onPointerDownCapture,
      onPointerMoveCapture,
      onPointerUpCapture: onPointerEndCapture,
      onPointerCancelCapture: onPointerEndCapture,
      onContextMenuCapture: cancelPress,
    },
  };
}
