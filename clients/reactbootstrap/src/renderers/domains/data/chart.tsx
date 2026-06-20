import React from 'react';

export const Chart: React.FC<any> = ({ chartType = 'bar', data = [], labels = [], title }) => {
  if (!data?.length) {
    return (
      <div className="text-muted small">Nessun dato disponibile</div>
    );
  }

  const numericData = data.map((value: unknown) => Number(value)).filter((value: number) => Number.isFinite(value));
  if (!numericData.length) {
    return (
      <div className="text-muted small">Nessun dato disponibile</div>
    );
  }

  const maxVal = Math.max(...numericData, 1);
  const height = 270;
  const width = 480;
  const padding = { top: 18, right: 18, bottom: 68, left: 44 };
  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;

  const stepX = chartWidth / (numericData.length > 1 ? numericData.length - 1 : 1);
  const baselineY = height - padding.bottom;
  const labelY = height - 22;
  const visibleLabelIndexes = (() => {
    const count = Math.min(labels.length, numericData.length);
    return Array.from({ length: count }, (_, i) => i);
  })();

  const renderChart = () => {
    if (chartType === 'bar') {
      const slotWidth = chartWidth / numericData.length;
      const barWidth = Math.max(8, Math.min(34, slotWidth * 0.54));
      return numericData.map((val: number, i: number) => {
        const h = (val / maxVal) * chartHeight;
        const x = padding.left + (i * slotWidth) + ((slotWidth - barWidth) / 2);
        return <rect key={i} x={x} y={baselineY - h} width={barWidth} height={h} fill="var(--bs-primary)" rx="2" />;
      });
    }

    if (chartType === 'line' || chartType === 'area') {
      const points = numericData.map((val: number, i: number) => {
        const x = padding.left + (i * stepX);
        const y = baselineY - ((val / maxVal) * chartHeight);
        return `${x},${y}`;
      }).join(' ');

      return (
        <>
          {chartType === 'area' ? (
            <polyline
              points={`${padding.left},${baselineY} ${points} ${width - padding.right},${baselineY}`}
              fill="var(--bs-primary)"
              fillOpacity="0.2"
              stroke="none"
            />
          ) : null}
          <polyline points={points} fill="none" stroke="var(--bs-primary)" strokeWidth="3" strokeLinejoin="round" />
          {numericData.map((val: number, i: number) => {
            const x = padding.left + (i * stepX);
            const y = baselineY - ((val / maxVal) * chartHeight);
            return <circle key={i} cx={x} cy={y} r="4" fill="var(--bs-primary)" />;
          })}
        </>
      );
    }

    return null;
  };

  return (
    <div className="w-100">
      {title ? (
        <div className="mb-2 small fw-semibold">{title}</div>
      ) : null}
      <div>
        <svg viewBox={`0 0 ${width} ${height}`} className="w-100 h-auto">
          {[0, 0.25, 0.5, 0.75, 1].map((p) => (
            <line
              key={p}
              x1={padding.left}
              y1={baselineY - (p * chartHeight)}
              x2={width - padding.right}
              y2={baselineY - (p * chartHeight)}
              stroke="var(--bs-border-color)"
              strokeWidth="1"
              strokeDasharray="4"
            />
          ))}

          {renderChart()}

          {visibleLabelIndexes.map((i: number) => {
            const label = labels[i];
            const x = padding.left + (i * (chartWidth / (numericData.length > 1 ? numericData.length - 1 : 1)));
            let textX = x;
            if (chartType === 'bar') {
              const slotWidth = chartWidth / numericData.length;
              textX = padding.left + (i * slotWidth) + (slotWidth / 2);
            }
            return (
              <text 
                key={i} 
                x={textX} 
                y={labelY} 
                textAnchor="end" 
                dominantBaseline="middle"
                transform={`rotate(-45 ${textX} ${labelY})`}
                fill="var(--bs-secondary-color)" 
                style={{ fontSize: '12px' }}
              >
                {label}
              </text>
            );
          })}
        </svg>
      </div>
    </div>
  );
};
