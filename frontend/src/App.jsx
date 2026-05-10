import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Contracts from './pages/Contracts'
import Points from './pages/Points'
import Pharmacy from './pages/Pharmacy'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/dashboard" replace />} />
      <Route element={<Layout />}>
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/contracts" element={<Contracts />} />
        <Route path="/sales"     element={<Points />} />
        <Route path="/pharmacy"  element={<Pharmacy />} />
      </Route>
    </Routes>
  )
}
