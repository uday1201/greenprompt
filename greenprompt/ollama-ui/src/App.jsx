import { useState } from 'react';
import axios from 'axios';
import LeaderboardIcon from '@mui/icons-material/Leaderboard';
import CircularProgress from '@mui/material/CircularProgress';
import SendIcon from '@mui/icons-material/Send';
import Alert from '@mui/material/Alert';
import { useNavigate } from 'react-router-dom';

function App() {
  const [model, setModel] = useState('llama2');
  const [prompt, setPrompt] = useState('');
  const [response, setResponse] = useState(null);
  const [showAnalytics, setShowAnalytics] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const navigate = useNavigate();

  const goToDashboard = () => {
    navigate("/dashboard");
  }

  const toggleAnalytics = () => {
    setShowAnalytics(!showAnalytics);
  }

  const sendPrompt = async () => {
    if (!prompt.trim()) return;

    setLoading(true);
    setResponse(null);
    setError('');

    try {
      const res = await axios.post('http://localhost:5000/api/prompt', {
        prompt,
        model,
      });
      setResponse(res.data);
      // console.log(response);
    } catch (err) {
      setError('Failed to connect to the backend.');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col bg-[#3d3b44] text-white">
      {/* Header */}
      <div className="p-4 flex flex-row justify-between w-full bg-[#1f1e24] shadow-md">
        <h1 className="text-2xl font-semibold text-green-500">Green Prompt</h1>
        <button className='border p-2 rounded-md border-gray-600 hover:scale-105 transition-transform duration-200' onClick={goToDashboard}>
          <div className='flex flex-row items-center gap-x-2'>
            <p className='font-medium hover:text-gray-300'>Dashboard</p>
            <LeaderboardIcon className='text-green-600 w-6 h-6' />
          </div>
        </button>
      </div>

      {/* Chat area */}
      <div className="flex-1 overflow-y-auto p-6 w-full max-w-4xl mx-auto space-y-4">
        {response && (
          <div className="text-white w-full max-w-3xl">
            <p className="whitespace-pre-line mt-2">{response.response}</p>
            <button className='bg-green-600 p-2 rounded-lg text-sm font-semibold cursor-pointer hover:bg-green-700' type="button" onClick={toggleAnalytics}>
              {showAnalytics ? 'Hide Analytics' : 'Show Analytics'}
            </button>
          </div>
        )}
        {error && <Alert severity="error">{error}</Alert>}
        {showAnalytics && <Analytics />}
      </div>

      {/* Input area*/}
      <div className="w-full bg-[#1f1e24] p-4">
        <div className="relative max-w-4xl mx-auto">
          <div className="mb-4">
            <label htmlFor="model-select" className="block mb-2 font-semibold text-sm">
              Choose Model:
            </label>
            <select
              id="model-select"
              value={model}
              onChange={(e) => setModel(e.target.value)}
              className="bg-[#4e4d52] text-white p-2 rounded-lg w-full focus:outline-none focus:ring-2 focus:ring-zinc-800 transition-all duration-300"
            >
              <option value="smollm:1.7b">smollm:1.7b</option>
              <option value="llama2">llama2</option>
              <option value="gpt4all">gpt4all</option>
              {/* Add more model options as needed */}
            </select>
          </div>

          <textarea
            className="w-full h-24 p-4 pr-20 bg-[#4e4d52] text-white rounded-lg resize-none shadow focus:outline-none focus:ring-2 focus:ring-zinc-800"
            placeholder="How can I help you today?"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                sendPrompt();
              }
            }}
          />

          <button
            onClick={sendPrompt}
            disabled={loading}
            className="absolute bottom-3 right-3 flex items-center justify-center w-10 h-10 bg-green-600 text-white rounded-full shadow-md hover:bg-green-700 transition-colors duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? (
              <CircularProgress size="30px" color='inherit' />
            ) : (
              <SendIcon className="w-5 h-5" />
            )}
          </button>

        </div>
      </div>
    </div>
  );


}

export default App;
