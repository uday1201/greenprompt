import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import { BrowserRouter as Router, Route, Routes } from "react-router-dom";
import App from './App.jsx'
import Dashboard from './components/Dashboard.jsx';
import './App.css'

createRoot(document.getElementById('root')).render(
  <Router>
    <Routes>
      <Route path='/chat' element={<App />} />
      <Route path='/dashboard' element={<Dashboard />} />
    </Routes>
  </Router>,
)
