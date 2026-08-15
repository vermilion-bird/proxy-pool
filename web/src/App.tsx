import { Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import { ToastProvider } from './components/Toast'
import Dashboard from './pages/Dashboard'
import Nodes from './pages/Nodes'
import Acquire from './pages/Acquire'
import Audit from './pages/Audit'
import Settings from './pages/Settings'
import './App.css'

export default function App() {
  return (
    <ToastProvider>
      <Layout>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/nodes" element={<Nodes />} />
          <Route path="/acquire" element={<Acquire />} />
          <Route path="/audit" element={<Audit />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </Layout>
    </ToastProvider>
  )
}
