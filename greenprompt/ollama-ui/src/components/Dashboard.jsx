import React, { useState } from 'react';
import { FormControl, InputLabel, MenuItem, Select } from '@mui/material';
import EnergyChartContainer from './EnergyChart';
import PromptTable from './PromptTable';
import Overview from './Overview';
import HomeIcon from '@mui/icons-material/Home';
import { useNavigate } from 'react-router';

export default function Dashboard() {
    const [value, setValue] = useState('llama2');
    const [activeSection, setActiveSection] = useState("overview");
    const [startDate, setStartDate] = useState('');
    const [endDate, setEndDate] = useState('');

    const handleSectionClick = (section) => {
        setActiveSection(section);
    }

    const handleChange = (e) => {
        setValue(e.target.value);
    }

    const section = [
        { id: "overview", label: "Overview" },
        { id: "energychart", label: "Energy Chart" },
        { id: "prompthistory", label: "Prompt History" },
    ];

    const sectionContent = {
        overview: <Overview />,
        energychart: <EnergyChartContainer model={value} startDate={startDate} endDate={endDate} />,
        prompthistory: <PromptTable model={value} startDate={startDate} endDate={endDate} />,
    };

    const navigate = useNavigate();

    const goToHome = () => {
        navigate("/chat");
    }
    return (
        <div className="min-h-screen flex flex-col bg-[#3d3b44] text-white">
            {/* Header */}
            <div className="p-4 flex flex-row justify-between w-full bg-[#1f1e24] shadow-md">
                <h1 className="text-2xl font-semibold text-green-500">Dashboard</h1>
                <div className='flex flex-row items-center gap-x-2'>
                    <button className='border p-2 rounded-md border-gray-600 hover:scale-105 transition-transform duration-200' onClick={goToHome}>
                        <div className='flex flex-row items-center gap-x-2'>
                            <p className='font-medium hover:text-gray-300'>Home</p>
                            <HomeIcon className='text-green-600 w-6 h-6' />
                        </div>
                    </button>
                </div>
            </div>
            <div className="border h-screen">
                <div className="grid grid-cols-12 gap-4 p-4">
                    {/* sidebar */}
                    <div className="col-span-3 p-4 border border-gray-600 rounded-md">
                        <div className="flex flex-col items-start gap-y-4">
                            {section.map((section) => (
                                <button
                                    key={section.id}
                                    onClick={() => handleSectionClick(section.id)}
                                    className={`w-full h-12 text-lg rounded-lg transition-all duration-300 cursor-pointer ${activeSection === section.id
                                        ? "bg-zinc-100 text-green-600 shadow-md font-bold"
                                        : "text-gray-400 hover:bg-gray-100 hover:text-green-600 font-semibold"
                                        }`}>
                                    {section.label}
                                </button>
                            ))}
                        </div>
                    </div>
                    {/* main-content */}
                    <div className="col-span-9 p-4 border border-gray-600 rounded-md">
                        {/* dropdown */}
                        <div className='w-40'>
                            <FormControl fullWidth>
                                <InputLabel id="dropdown-label" sx={{ color: 'white' }}>Model</InputLabel>
                                <Select
                                    labelId="dropdown-label"
                                    value={value}
                                    label="Option"
                                    onChange={handleChange}
                                    sx={{
                                        height: 36,
                                        backgroundColor: '#464647',
                                        color: 'white',
                                        borderRadius: '0.375rem', // Tailwind's rounded-md
                                        '& .MuiSvgIcon-root': { color: 'white' }, // dropdown arrow color
                                    }}
                                >
                                    <MenuItem value={'llama2'}>llama2</MenuItem>
                                    <MenuItem value={'llama4'}>llama4</MenuItem>
                                    <MenuItem value={'deepseek'}>deepseek-r1</MenuItem>
                                </Select>
                            </FormControl>
                        </div>
                        
                        {/* Start/End datetime inputs */}
                        <div className="flex gap-4 mb-4">
                            <div>
                                <label className="block mb-1 text-white font-semibold" htmlFor="startDate">Start Date</label>
                                <input
                                    type="datetime-local"
                                    id="startDate"
                                    value={startDate}
                                    onChange={(e) => setStartDate(e.target.value)}
                                    className="rounded p-1 text-black"
                                />
                            </div>
                            <div>
                                <label className="block mb-1 text-white font-semibold" htmlFor="endDate">End Date</label>
                                <input
                                    type="datetime-local"
                                    id="endDate"
                                    value={endDate}
                                    onChange={(e) => setEndDate(e.target.value)}
                                    className="rounded p-1 text-black"
                                />
                            </div>
                        </div>
                        {/* section content */}
                        <div key={activeSection}>
                            {sectionContent[activeSection]}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}