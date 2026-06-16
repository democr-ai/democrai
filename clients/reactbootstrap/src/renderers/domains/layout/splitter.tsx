import React, { useEffect, useMemo, useRef, useState } from 'react';

const normalizeSizes = (raw: number[]): number[] => {
  const total = raw.reduce((acc, n) => acc + n, 0);
  if (total <= 0) return raw;
  return raw.map((n) => (n / total) * 100);
};

const asNumberArray = (value: any): number[] => {
  if (!Array.isArray(value)) return [];
  return value.map((entry) => Number(entry));
};

export const Splitter: React.FC<any> = ({
  ExplicitList,
  stretch,
  sizes: declaredSizes,
  max_sizes: declaredMaxSizes,
}) => {
  const list = useMemo(() => (Array.isArray(ExplicitList) ? ExplicitList : []), [ExplicitList]);
  const initialSizes = useMemo(() => asNumberArray(declaredSizes).filter((n) => Number.isFinite(n) && n > 0), [declaredSizes]);
  const maxSizes = useMemo(() => asNumberArray(declaredMaxSizes), [declaredMaxSizes]);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [sizes, setSizes] = useState<number[]>([]);

  useEffect(() => {
    if (list.length === 0) {
      setSizes([]);
      return;
    }
    if (initialSizes.length === list.length) {
      setSizes(normalizeSizes(initialSizes));
      return;
    }
    setSizes(new Array(list.length).fill(100 / list.length));
  }, [initialSizes, list.length]);

  const startResize = (index: number, startClientX: number) => {
    const container = containerRef.current;
    if (!container) return;

    const totalWidth = container.clientWidth;
    if (totalWidth <= 0) return;

    const minPct = Math.max(8, (140 / totalWidth) * 100);
    const leftMaxPx = maxSizes[index];
    const rightMaxPx = maxSizes[index + 1];
    const leftMaxPct = Number.isFinite(leftMaxPx) && leftMaxPx > 0 ? (leftMaxPx / totalWidth) * 100 : Infinity;
    const rightMaxPct = Number.isFinite(rightMaxPx) && rightMaxPx > 0 ? (rightMaxPx / totalWidth) * 100 : Infinity;
    const startSizes = [...sizes];

    const onMove = (event: MouseEvent) => {
      const deltaPx = event.clientX - startClientX;
      const deltaPct = (deltaPx / totalWidth) * 100;

      const left = startSizes[index] + deltaPct;
      const right = startSizes[index + 1] - deltaPct;

      if (left < minPct || right < minPct) return;
      if (left > leftMaxPct || right > rightMaxPct) return;

      const next = [...startSizes];
      next[index] = left;
      next[index + 1] = right;
      setSizes(normalizeSizes(next));
    };

    const onUp = () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };

    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  };

  return (
    <div 
      ref={containerRef} 
      className={`d-flex min-vh-0 w-100 flex-row overflow-hidden ${stretch ? 'flex-grow-1' : ''}`}
    >
      {list.map((child: any, idx: number) => {
        const size = sizes[idx] ?? (100 / Math.max(1, list.length));
        const maxPx = maxSizes[idx];
        const maxWidth = Number.isFinite(maxPx) && maxPx > 0 ? `${maxPx}px` : undefined;
        return (
          <React.Fragment key={idx}>
            <div 
              className="min-vh-0 min-vw-0 overflow-auto"
              style={{ flex: `0 0 ${size}%`, ...(maxWidth ? { maxWidth } : {}) }}
            >
              {child}
            </div>
            {idx < list.length - 1 ? (
              <div
                onMouseDown={(e) => startResize(idx, e.clientX)}
                className="position-relative bg-light cursor-col-resize"
                style={{ width: '4px', flexShrink: 0 }}
                role="separator"
                aria-orientation="vertical"
                aria-label="Resize panels"
              >
                <div className="position-absolute h-100 border-start" style={{ left: '50%', transform: 'translateX(-50%)' }} />
              </div>
            ) : null}
          </React.Fragment>
        );
      })}
    </div>
  );
};
