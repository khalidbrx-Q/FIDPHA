import { useEffect, useState } from 'react'
import { apiFetch } from '../api/client'

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

  if (loading) return <div className="page-state">Loading…</div>
  if (error)   return <div className="page-state error">Error: {error.message}</div>

  return (
    <div className="contracts-page">
      <h1>Contracts</h1>

      <div className="contracts-table-wrap">
        <table className="contracts-table">
          <thead>
            <tr>
              <th>Title</th>
              <th>Status</th>
              <th>Start</th>
              <th>End</th>
              <th>Products</th>
              <th>Units</th>
              <th>Points</th>
            </tr>
          </thead>
          <tbody>
            {data.contracts.map(c => (
              <tr key={c.id} className={c.id === data.active_id ? 'row-active' : ''}>
                <td className="td-title">{c.title}</td>
                <td><span className={`badge-status ${c.status}`}>{c.status}</span></td>
                <td>{c.start_date ?? '—'}</td>
                <td>{c.end_date ?? '—'}</td>
                <td>{c.product_count}</td>
                <td>{c.total_units}</td>
                <td className="td-points">{c.total_points.toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {data.pages > 1 && (
        <div className="pagination">
          <button disabled={page === 1} onClick={() => setPage(p => p - 1)}>← Prev</button>
          <span>Page {data.page} of {data.pages}</span>
          <button disabled={page === data.pages} onClick={() => setPage(p => p + 1)}>Next →</button>
        </div>
      )}
    </div>
  )
}
