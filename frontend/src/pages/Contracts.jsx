import { useEffect, useState } from 'react'
import { apiFetch } from '../api/client'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

export default function Contracts() {
  const [data, setData]     = useState(null)
  const [page, setPage]     = useState(1)
  const [error, setError]   = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    apiFetch(`/contracts/?page=${page}`)
      .then(setData)
      .catch(setError)
      .finally(() => setLoading(false))
  }, [page])

  if (loading) return <div className="flex items-center justify-center h-[60vh] text-slate-500">Loading…</div>
  if (error)   return <div className="flex items-center justify-center h-[60vh] text-red-500">Error: {error.message}</div>

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Contracts</h1>
        <p className="text-sm text-slate-500 mt-1">All contracts associated with your pharmacy</p>
      </div>

      <Card className="border-slate-200 shadow-sm">
        <CardContent className="p-0">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100">
                {['Title', 'Status', 'Start', 'End', 'Products', 'Units', 'Points'].map(h => (
                  <th key={h} className="text-left px-6 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.contracts.map(c => (
                <tr
                  key={c.id}
                  className={`border-b border-slate-50 transition-colors ${
                    c.id === data.active_id ? 'bg-blue-50/60' : 'hover:bg-slate-50'
                  }`}
                >
                  <td className="px-6 py-3 font-semibold text-slate-800">{c.title}</td>
                  <td className="px-6 py-3"><StatusBadge status={c.status} /></td>
                  <td className="px-6 py-3 text-slate-600">{c.start_date ?? '—'}</td>
                  <td className="px-6 py-3 text-slate-600">{c.end_date ?? '—'}</td>
                  <td className="px-6 py-3 text-slate-600">{c.product_count}</td>
                  <td className="px-6 py-3 text-slate-600">{c.total_units}</td>
                  <td className="px-6 py-3 font-bold text-blue-600">{c.total_points.toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>

      {data.pages > 1 && (
        <div className="flex items-center justify-center gap-4 text-sm text-slate-600">
          <button
            disabled={page === 1}
            onClick={() => setPage(p => p - 1)}
            className="px-4 py-2 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 disabled:opacity-40 disabled:cursor-default transition-colors"
          >← Prev</button>
          <span>Page {data.page} of {data.pages}</span>
          <button
            disabled={page === data.pages}
            onClick={() => setPage(p => p + 1)}
            className="px-4 py-2 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 disabled:opacity-40 disabled:cursor-default transition-colors"
          >Next →</button>
        </div>
      )}
    </div>
  )
}

function StatusBadge({ status }) {
  const cls = {
    active:   'bg-emerald-50 text-emerald-700 border-emerald-200',
    inactive: 'bg-slate-100 text-slate-500 border-slate-200',
  }
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold border ${cls[status] ?? cls.inactive}`}>
      {status}
    </span>
  )
}
