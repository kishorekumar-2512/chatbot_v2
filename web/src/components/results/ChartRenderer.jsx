import { useMemo } from 'react';
import Plot from 'react-plotly.js';

/**
 * ChartRenderer — Plotly chart with dark theme.
 * Accepts chart_json (string or object) containing { data, layout }.
 */
export default function ChartRenderer({ chartJson, chartKind }) {
  const parsed = useMemo(() => {
    if (!chartJson) return null;
    try {
      const obj = typeof chartJson === 'string' ? JSON.parse(chartJson) : chartJson;
      return obj;
    } catch {
      return null;
    }
  }, [chartJson]);

  if (!parsed || !parsed.data) return null;

  /* Dark theme overrides */
  const layout = {
    ...parsed.layout,
    paper_bgcolor: 'transparent',
    plot_bgcolor: 'transparent',
    font: { color: '#94A3B8', family: 'Inter, sans-serif', size: 12 },
    margin: { l: 50, r: 20, t: 40, b: 50, pad: 4 },
    xaxis: {
      ...parsed.layout?.xaxis,
      gridcolor: 'rgba(255,255,255,0.06)',
      linecolor: 'rgba(255,255,255,0.1)',
      zerolinecolor: 'rgba(255,255,255,0.06)',
    },
    yaxis: {
      ...parsed.layout?.yaxis,
      gridcolor: 'rgba(255,255,255,0.06)',
      linecolor: 'rgba(255,255,255,0.1)',
      zerolinecolor: 'rgba(255,255,255,0.06)',
    },
    legend: {
      ...parsed.layout?.legend,
      font: { color: '#94A3B8' },
    },
    autosize: true,
  };

  const config = {
    displayModeBar: true,
    displaylogo: false,
    responsive: true,
    modeBarButtonsToRemove: ['lasso2d', 'select2d'],
  };

  return (
    <div className="chart-container">
      <Plot
        data={parsed.data}
        layout={layout}
        config={config}
        useResizeHandler
        style={{ width: '100%', height: '350px' }}
      />
    </div>
  );
}
