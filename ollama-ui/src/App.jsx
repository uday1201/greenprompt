import { useState } from 'react';
import axios from 'axios';

function App() {
  const [prompt, setPrompt] = useState('');
  const [response, setResponse] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const sendPrompt = async () => {
    if (!prompt.trim()) return;

    setLoading(true);
    setResponse(null);
    setError('');

    try {
      const res = await axios.post('http://localhost:5000/api/prompt', {
        prompt,
        model: 'llama2',
      });
      setResponse(res.data);
      console.log(response);
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
      <header className="w-full bg-[#1f1e24] py-4 text-center shadow-md">
        <h1 className="text-2xl font-bold text-green-500">Green Prompt</h1>
      </header>

      {/* Chat area */}
      <div className="flex-1 overflow-y-auto p-6 w-full max-w-4xl mx-auto space-y-4">
        {response && (
          <div className="text-white w-full max-w-3xl">
            <p className="whitespace-pre-line mt-2">{response.response}</p>
            <div className="text-sm text-gray-600 mt-4 space-y-1">
              <div>Tokens Used: {response.total_tokens}</div>
              <div>Time Taken: {response.duration_sec?.toFixed(2) || 'N/A'} sec</div>
              <div>Estimated Energy: {response.energy_wh?.toFixed(6) || 'N/A'} Wh</div>
            </div>
          </div>
        )}
        {error && <div className="text-red-500 font-medium">{error}</div>}
      </div>

      {/* Input area*/}
      <div className="w-full bg-[#1f1e24] p-4">
        <div className="relative max-w-4xl mx-auto">
          <textarea
            className="w-full h-24 p-4 pr-20 bg-[#4e4d52] text-white rounded-lg resize-none shadow focus:outline-none focus:ring-2 focus:ring-zinc-800"
            placeholder="How can I help you today?"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
          />

          <button
            onClick={sendPrompt}
            disabled={loading}
            className="absolute bottom-3 right-3 h-10 px-4 bg-green-600 text-white rounded-full hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? '...' : <span>➤</span>}
          </button>
        </div>
      </div>

    </div>
  );


}

export default App;
