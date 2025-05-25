import React, { useEffect, useState } from 'react';
import { DataGrid } from '@mui/x-data-grid';

const columns = [
  { field: 'timestamp', headerName: 'Time', width: 150 },
  { field: 'model', headerName: 'Model', width: 120 },
  { field: 'energy', headerName: 'Energy (Wh)', width: 130 },
  { field: 'cpu', headerName: 'CPU (%)', width: 100 },
  { field: 'prompt', headerName: 'Prompt', flex: 1 },
];

export default function PromptTable({ model, startDate, endDate }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    async function fetchRows() {
      setLoading(true);
      let url = `/api/usage/model/${model}`;
      if (startDate && endDate) {
        url = `/api/usage/timeframe?start=${encodeURIComponent(startDate)}&end=${encodeURIComponent(endDate)}`;
      }
      try {
        const res = await fetch(url);
        const data = await res.json();
        const mapped = data.map(item => ({
          id: item.id,
          timestamp: new Date(item.timestamp).toLocaleString(),
          model: item.model,
          energy: item.energy_wh,
          cpu: item.cpu_power_w,
          prompt: item.prompt,
        }));
        setRows(mapped);
      } catch (error) {
        console.error('Failed to fetch prompt table data', error);
      }
      setLoading(false);
    }
    fetchRows();
  }, [model, startDate, endDate]);

  if (loading) return <p>Loading prompt history...</p>;
  if (!rows.length) return <p>No data available</p>;

  return (
    <div className="h-[400px] w-full bg-[#2e2c33] rounded-xl mt-6 p-4">
      <DataGrid
        rows={rows}
        columns={columns}
        pageSize={5}
        sx={{
          color: 'green',
          borderColor: '#2e2d2d',
          '& .MuiDataGrid-cell': { color: 'green' },
          '& .MuiDataGrid-columnHeaders': { backgroundColor: '#3e3e46' },
        }}
      />
    </div>
  );
}
