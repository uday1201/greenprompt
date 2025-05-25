import React, { useEffect, useState } from 'react';
import EnergyChart from './EnergyChart';

export default function EnergyChartContainer({ model, startDate, endDate }) {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    async function fetchData() {
      setLoading(true);
      let url = `/api/usage/model/${model}`;
      if (startDate && endDate) {
        url = `/api/usage/timeframe?start=${encodeURIComponent(startDate)}&end=${encodeURIComponent(endDate)}`;
      }
      try {
        const res = await fetch(url);
        const json = await res.json();
        // Map API data to chart data structure (timestamp -> time string)
        const mapped = json.map(item => ({
          time: new Date(item.timestamp).toLocaleTimeString(),
          energy: item.energy_wh,
          cpu: item.cpu_power_w,
          gpu: item.gpu_power_w,
        }));
        setData(mapped);
      } catch (error) {
        console.error('Failed to fetch energy data', error);
      }
      setLoading(false);
    }
    fetchData();
  }, [model, startDate, endDate]);

  if (loading) return <p>Loading energy data...</p>;
  if (!data.length) return <p>No data available</p>;

  return <EnergyChart data={data} />;
}
