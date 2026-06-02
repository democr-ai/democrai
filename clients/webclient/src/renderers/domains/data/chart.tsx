import React from 'react';

export const Chart: React.FC<any> = ({ chartType = 'bar', data = [], labels = [], title }) => {
  if (!data?.length) {
    return (
      <div className="w-full text-sm text-muted-foreground">Nessun dato disponibile</div>
    );
  }

  const maxVal = Math.max(...data) || 1;
  const height = 200;
  const width = 400;
  const padding = 20;
  const chartWidth = width - (padding * 2);
  const chartHeight = height - (padding * 2);

  const stepX = chartWidth / (data.length > 1 ? data.length - 1 : 1);
  const visibleLabelIndexes = (() => {
    const count = Math.min(labels.length, data.length);
    if (count <= 6) {
      return Array.from({ length: count }, (_, i) => i);
    }
    const indexes = new Set<number>();
    const step = Math.ceil((count - 1) / 5);
    for (let i = 0; i < count; i += step) {
      indexes.add(i);
    }
    indexes.add(count - 1);
    return Array.from(indexes).sort((a, b) => a - b);
  })();

  const renderChart = () => {
    if (chartType === 'bar') {
      const barWidth = (chartWidth / data.length) * 0.7;
      return data.map((val: number, i: number) => {
        const h = (val / maxVal) * chartHeight;
        const x = padding + (i * (chartWidth / data.length)) + (chartWidth / data.length - barWidth) / 2;
        return <rect key={i} x={x} y={height - padding - h} width={barWidth} height={h} className="fill-primary" rx="2" />;
      });
    }

    if (chartType === 'line' || chartType === 'area') {
      const points = data.map((val: number, i: number) => {
        const x = padding + (i * stepX);
        const y = height - padding - ((val / maxVal) * chartHeight);
        return `${x},${y}`;
      }).join(' ');

      return (
        <>
          {chartType === 'area' ? (
            <polyline
              points={`${padding},${height - padding} ${points} ${width - padding},${height - padding}`}
              className="fill-primary/20"
              stroke="none"
            />
          ) : null}
          <polyline points={points} fill="none" className="stroke-primary" strokeWidth="3" strokeLinejoin="round" />
          {data.map((val: number, i: number) => {
            const x = padding + (i * stepX);
            const y = height - padding - ((val / maxVal) * chartHeight);
            return <circle key={i} cx={x} cy={y} r="4" className="fill-primary" />;
          })}
        </>
      );
    }

    return null;
  };

  return (
    <div className="w-full min-w-0">
      {title ? (
        <div className="pb-2 text-sm font-semibold text-foreground">{title}</div>
      ) : null}
      <div>
        <svg viewBox={`0 0 ${width} ${height}`} className="h-full w-full">
          {[0, 0.25, 0.5, 0.75, 1].map((p) => (
            <line
              key={p}
              x1={padding}
              y1={height - padding - (p * chartHeight)}
              x2={width - padding}
              y2={height - padding - (p * chartHeight)}
              className="stroke-border"
              strokeWidth="1"
              strokeDasharray="4"
            />
          ))}

          {renderChart()}

          {visibleLabelIndexes.map((i: number) => {
            const label = labels[i];
            const x = padding + (i * (chartWidth / (data.length > 1 ? data.length - 1 : 1)));
            if (chartType === 'bar') {
              const centerBar = padding + (i * (chartWidth / data.length)) + ((chartWidth / data.length) / 2);
              return <text key={i} x={centerBar} y={height - 5} textAnchor="middle" className="fill-muted-foreground" style={{ fontSize: 6 }}>{label}</text>;
            }
            return <text key={i} x={x} y={height - 5} textAnchor="middle" className="fill-muted-foreground" style={{ fontSize: 6 }}>{label}</text>;
          })}
        </svg>
      </div>
    </div>
  );
};
