import { useEffect, useState } from 'react'
import { apiFetch } from '../api/client'

export default function Dashboard() {
  const [stats, setStats]   = useState(null)
  const [error, setError]   = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    apiFetch('/dashboard/stats/')
      .then(setStats)
      .catch(setError)
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="page-state">Loading…</div>
  if (error)   return <div className="page-state error">Error: {error.message}</div>

  return (
    <div className="dashboard">
      <h1>Dashboard</h1>

      <div className="stats-grid">
        <StatCard label="Total Points"      value={stats.total_points}                          />
        <StatCard label="Points This Month" value={stats.this_month_points}                     />
        <StatCard label="Units This Month"  value={stats.this_month_units}                      />
        <StatCard label="Products"          value={stats.products_count}                        />
        <StatCard label="Contracts"         value={stats.contracts_count}                       />
        <StatCard label="Active Contract"   value={stats.active_contract?.title ?? '—'}         />
      </div>
    </div>
  )
}

function StatCard({ label, value }) {
  return (
    <div className="stat-card">
      <span className="stat-value">{value ?? 0}</span>
      <span className="stat-label">{label}</span>
    </div>
  )
}
