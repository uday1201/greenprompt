import React, { useEffect, useState } from 'react';
import axios from 'axios';

export default function Overview() {
    const [data, setData] = useState([]);
    const [stats, setStats] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        axios.get('http://localhost:5000/api/usage/all')
            .then(response => {
                const all = response.data;
                setData(all);
                setStats(generateStats(all));
                setLoading(false);
            })
            .catch(error => {
                console.error('Error fetching usage data:', error);
                setLoading(false);
            });
    }, []);

    const generateStats = (entries) => {
        const totalPrompts = entries.length;
        const totalEnergy = entries.reduce((sum, entry) => sum + entry.energy_wh, 0);
        const avgCpuPower = entries.reduce((sum, entry) => sum + entry.cpu_power_w, 0) / totalPrompts;
        const totalDuration = entries.reduce((sum, entry) => sum + entry.duration_sec, 0);
        const avgTokens = entries.reduce((sum, entry) => sum + entry.total_tokens, 0) / totalPrompts;

        return {
            totalPrompts,
            totalEnergy: totalEnergy.toFixed(4),
            avgCpuPower: avgCpuPower.toFixed(2),
            totalDuration: totalDuration.toFixed(2),
            avgTokens: avgTokens.toFixed(1),
        };
    };

    if (loading) return <p className="text-gray-400">Loading...</p>;
    if (!stats) return <p className="text-red-500">No data available</p>;

    return (
        <div className="space-y-6 text-white">
            <h2 className="text-2xl font-bold text-green-400">Usage Overview</h2>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4 text-sm">
                <OverviewCard label="Total Prompts" value={stats.totalPrompts} />
                <OverviewCard label="Total Energy (Wh)" value={stats.totalEnergy} />
                <OverviewCard label="Avg CPU Power (W)" value={stats.avgCpuPower} />
                <OverviewCard label="Total Duration (s)" value={stats.totalDuration} />
                <OverviewCard label="Avg Tokens per Prompt" value={stats.avgTokens} />
            </div>
        </div>
    );
}

function OverviewCard({ label, value }) {
    return (
        <div className="bg-[#2d2c33] p-4 rounded-xl shadow-md border border-gray-700">
            <p className="text-gray-400">{label}</p>
            <p className="text-lg font-semibold text-white">{value}</p>
        </div>
    );
}
