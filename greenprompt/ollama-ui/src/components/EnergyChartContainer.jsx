import React, { useEffect, useState } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import axios from 'axios';

const EnergyChartContainer = ({ model }) => {
    const [data, setData] = useState([]);

    useEffect(() => {
        const fetchEnergyData = async () => {
            try {
                const response = await axios.get('/api/usage/all');
                console.log(response.data)
                const filtered = response.data
                    .filter(item => !model || item.model === model)
                    .map(item => ({
                        timestamp: new Date(item.timestamp).toLocaleString(),
                        energy: item.energy_wh,
                    }));
                setData(filtered);
            } catch (error) {
                console.error("Error fetching energy data", error);
            }
        };
        fetchEnergyData();
    }, [model]);

    return (
        <div className="bg-[#2e2c34] p-4 rounded-lg shadow-md">
            <h2 className="text-xl font-semibold text-green-400 mb-4">Energy Consumption Chart</h2>
            <ResponsiveContainer width="100%" height={300}>
                <LineChart data={data}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#555" />
                    <XAxis dataKey="timestamp" tick={{ fill: 'white' }} />
                    <YAxis tick={{ fill: 'white' }} />
                    <Tooltip contentStyle={{ backgroundColor: '#1f1e24', border: 'none' }} labelStyle={{ color: 'white' }} />
                    <Legend />
                    <Line type="monotone" dataKey="energy" stroke="#82ca9d" strokeWidth={2} />
                </LineChart>
            </ResponsiveContainer>
        </div>
    );
};

export default EnergyChartContainer;
