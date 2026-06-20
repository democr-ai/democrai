import React from 'react';

export const Chart: React.FC<any> = ({ chartType = 'bar', data = [], labels = [], title }) => {
  if (!data?.length) {
    return (
      <div className="ds-chart-empty">No data available</div>
    );
  }

  const numericData = data.map((value: unknown) => Number(value)).filter((value: number) => Number.isFinite(value));
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

  const yTicks = [0, 0.25, 0.5, 0.75, 1];
  const yForValue = (value: number) => baselineY - ((value / maxVal) * chartHeight);

  const renderChart = () => {
    if (chartType === 'bar') {
      const slotWidth = chartWidth / numericData.length;
      const barWidth = Math.max(8, Math.min(34, slotWidth * 0.54));
      return numericData.map((val: number, i: number) => {
        const h = (val / maxVal) * chartHeight;
        const x = padding.left + (i * slotWidth) + ((slotWidth - barWidth) / 2);
        return (
          <rect
            key={i}
            x={x}
            y={baselineY - h}
            width={barWidth}
            height={h}
            className="ds-chart-bar"
            rx="1"
          />
        );
      });
    }

    if (chartType === 'line' || chartType === 'area') {
      const points = numericData.map((val: number, i: number) => {
        const x = padding.left + (i * stepX);
        const y = yForValue(val);
        return `${x},${y}`;
      }).join(' ');

      return (
        <>
          {chartType === 'area' ? (
            <polygon
              points={`${padding.left},${baselineY} ${points} ${width - padding.right},${baselineY}`}
              className="ds-chart-area"
              stroke="none"
            />
          ) : null}
          <polyline points={points} fill="none" className="ds-chart-line" strokeLinejoin="round" strokeLinecap="round" />
          {numericData.map((val: number, i: number) => {
            const x = padding.left + (i * stepX);
            const y = yForValue(val);
            return <circle key={i} cx={x} cy={y} r="3.5" className="ds-chart-point" />;
          })}
        </>
      );
    }

    return null;
  };

  return (
    <div className="ds-chart">
      {title ? (
        <div className="ds-chart-title">{title}</div>
      ) : null}
      <div className="ds-chart-frame">
        <svg viewBox={`0 0 ${width} ${height}`} className="ds-chart-svg" role="img" aria-label={title || `${chartType} chart`}>
          {yTicks.map((p) => {
            const y = baselineY - (p * chartHeight);
            const tickValue = Math.round(maxVal * p);
            return (
              <React.Fragment key={p}>
                <line
                  x1={padding.left}
                  y1={y}
                  x2={width - padding.right}
                  y2={y}
                  className="ds-chart-grid-line"
                />
                <text
                  x={padding.left - 8}
                  y={y + 4}
                  textAnchor="end"
                  className="ds-chart-axis-label"
                >
                  {tickValue}
                </text>
              </React.Fragment>
            );
          })}

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
                className="ds-chart-axis-label ds-chart-x-label"
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
