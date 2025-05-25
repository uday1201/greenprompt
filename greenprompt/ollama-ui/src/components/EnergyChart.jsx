import * as React from 'react';
import { LineChart } from '@mui/x-charts/LineChart';

export default function EnergyChart({ data }) {
  if (!data || data.length === 0) {
    return <div className="text-gray-400 p-4">No data available</div>;
  }

  return (
    <div className="bg-[#2e2c33] p-4 rounded-xl mt-6">
      <h3 className="text-white text-lg mb-2">Energy & Power Usage Over Time</h3>
      <LineChart
        height={300}
        series={[
          { data: data.map(d => d.energy), label: 'Energy (Wh)' },
          { data: data.map(d => d.cpu), label: 'CPU Power (W)' },
          { data: data.map(d => d.gpu), label: 'GPU Power (W)' },
        ]}
        xAxis={[{ scaleType: 'point', data: data.map(d => d.time) }]}
        sx={{
          '.MuiChartsAxis-tickLabel': { fill: '#ccc' },
          '.MuiChartsAxis-line': { stroke: '#666' },
        }}
      />
    </div>
  );
}

