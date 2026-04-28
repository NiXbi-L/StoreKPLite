import { useCallback, useRef } from 'react';

const MOVE_SUPPRESS_CLICK_PX = 8;

/**
 * Горизонтальный overflow-x на десктопе: мышью тащим как на тач-скролле.
 * Для pointerType "touch" / "pen" не вмешиваемся — остаётся нативный скролл.
 */
export function useMouseDragHorizontalScroll({ disabled = false } = {}) {
  const draggingRef = useRef(false);
  const startXRef = useRef(0);
  const startScrollRef = useRef(0);
  const pointerIdRef = useRef(null);
  const movedEnoughToSuppressClickRef = useRef(false);

  const onPointerDown = useCallback(
    (e) => {
      if (disabled || e.pointerType !== 'mouse' || e.button !== 0) return;
      const el = e.currentTarget;
      if (!el || el.scrollWidth <= el.clientWidth + 1) return;
      movedEnoughToSuppressClickRef.current = false;
      draggingRef.current = true;
      pointerIdRef.current = e.pointerId;
      startXRef.current = e.clientX;
      startScrollRef.current = el.scrollLeft;
      try {
        el.setPointerCapture(e.pointerId);
      } catch (_) {
        /* ignore */
      }
      e.preventDefault();
    },
    [disabled]
  );

  const onPointerMove = useCallback((e) => {
    if (!draggingRef.current || e.pointerId !== pointerIdRef.current) return;
    const el = e.currentTarget;
    const dx = e.clientX - startXRef.current;
    if (Math.abs(dx) > MOVE_SUPPRESS_CLICK_PX) {
      movedEnoughToSuppressClickRef.current = true;
    }
    el.scrollLeft = startScrollRef.current - dx;
  }, []);

  const endDrag = useCallback((e) => {
    if (e.pointerId !== pointerIdRef.current) return;
    draggingRef.current = false;
    pointerIdRef.current = null;
    try {
      e.currentTarget.releasePointerCapture(e.pointerId);
    } catch (_) {
      /* ignore */
    }
  }, []);

  const onPointerUp = useCallback(
    (e) => {
      endDrag(e);
    },
    [endDrag]
  );

  const onPointerCancel = useCallback(
    (e) => {
      endDrag(e);
    },
    [endDrag]
  );

  const consumeSuppressedClick = useCallback(() => {
    if (movedEnoughToSuppressClickRef.current) {
      movedEnoughToSuppressClickRef.current = false;
      return true;
    }
    return false;
  }, []);

  return {
    dragScrollProps: {
      onPointerDown,
      onPointerMove,
      onPointerUp,
      onPointerCancel,
    },
    consumeSuppressedClick,
  };
}
