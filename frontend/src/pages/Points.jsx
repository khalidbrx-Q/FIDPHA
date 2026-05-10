import { useEffect, useState } from 'react'
import { apiFetch } from '../api/client'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'

const STATUS_OPTS = [
  { value: '',         label: 'All' },
  { value: 'accepted', label: 'Accepted' },
  { value: 'pending',  label: 'Pending' },
  { value: 'rejected', label: 'Rejected' },
]

export default function Points() {
  const [data, setData]       = useState(null)
  const [page, setPage]       = useState(1)
  const [status, setStatus]   = useState('')
  const [product, setProduct] = useState('')
  const [error, setError]     = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    const params = new URLSearchParams({ page })
    if (status)  params.set('status', status)
    if (product) params.set('product', product)
    apiFetch(`/sales/?${params}`)
      .then(setData)
      .catch(setError)
      .finally(() => setLoading(false))
  }, [page, status, product])

  function handleStatusChange(val) { setStatus(val); setPage(1) }
  function handleProductChange(e)  { setProduct(e.target.value); setPage(1) }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Points</h1>
        <p className="text-sm text-slate-500 mt-1">Your sales and points breakdown</p>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex gap-1 p-1 bg-slate-100 rounded-lg">
          {STATUS_OPTS.map(opt => (
            <button
              key={opt.value}
              onClick={() => handleStatusChange(opt.value)}
              className={cn(
                'px-3 py-1.5 rounded-md text-xs font-semibold transition-colors',
                status === opt.value
                  ? 'bg-white text-slate-900 shadow-sm'
                  : 'text-slate-500 hover:text-slate-700'
              )}
            >
              {opt.label}
            </button>
          ))}
        </div>
        <Input
          className="w-56 h-9 text-sm border-slate-200"
          placeholder="Search product…"
          value={product}
          onChange={handleProductChange}
        />
      </div>

      {loading ? (
        <div className="flex items-center justify-center h-40 text-slate-500">Loading…</div>
      ) : error ? (
        <div className="flex items-center justify-center h-40 text-red-500">Error: {error.message}</div>
      ) : (
        <>
          <Card className="border-slate-200 shadow-sm">
            <CardContent className="p-0">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-100">
                    {['Date', 'Product', 'Contract', 'Qty', 'Status', 'Points'].map(h => (
                      <th key={h} className="text-left px-6 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.items.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="text-center py-10 text-slate-400">No sales found</td>
                    </tr>
                  ) : data.items.map(s => (
                    <tr key={s.id} className="border-b border-slate-50 hover:bg-slate-50 transition-colors">
                      <td className="px-6 py-3 text-slate-600">{s.sale_datetime?.slice(0, 10) ?? '—'}</td>
                      <td className="px-6 py-3 font-medium text-slate-800">{s.product_designation}</td>
                      <td className="px-6 py-3 text-slate-600">{s.contract_title}</td>
                      <td className="px-6 py-3 text-slate-600">{s.quantity}</td>
                      <td className="px-6 py-3"><StatusBadge status={s.status} /></td>
                      <td className="px-6 py-3 font-bold text-blue-600">
                        {s.points != null ? s.points.toLocaleString() : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardContent>
          </Card>

          <div className="flex items-center justify-between text-sm text-slate-500">
            <span>{data.total} sale{data.total !== 1 ? 's' : ''}</span>
            {data.pages > 1 && (
              <div className="flex items-center gap-3">
                <button
                  disabled={!data.has_prev}
                  onClick={() => setPage(p => p - 1)}
                  className="px-4 py-2 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 disabled:opacity-40 disabled:cursor-default transition-colors"
                >← Prev</button>
                <span>Page {data.page} of {data.pages}</span>
                <button
                  disabled={!data.has_next}
                  onClick={() => setPage(p => p + 1)}
                  className="px-4 py-2 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 disabled:opacity-40 disabled:cursor-default transition-colors"
                >Next →</button>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}

function StatusBadge({ status }) {
  const cls = {
    accepted: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    rejected: 'bg-red-50 text-red-700 border-red-200',
    pending:  'bg-amber-50 text-amber-700 border-amber-200',
  }
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold border ${cls[status] ?? cls.pending}`}>
      {status}
    </span>
  )
}
