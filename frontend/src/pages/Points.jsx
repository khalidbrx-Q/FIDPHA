import { useEffect, useState } from 'react'
import { apiFetch } from '../api/client'

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

  function handleStatusChange(val) {
    setStatus(val)
    setPage(1)
  }

  function handleProductChange(e) {
    setProduct(e.target.value)
    setPage(1)
  }

  return (
    <div className="points-page">
      <h1>Points</h1>

      <div className="filters-bar">
        <div className="filter-group">
          {STATUS_OPTS.map(opt => (
            <button
              key={opt.value}
              className={'filter-btn' + (status === opt.value ? ' active' : '')}
              onClick={() => handleStatusChange(opt.value)}
            >
              {opt.label}
            </button>
          ))}
        </div>
        <input
          className="filter-input"
          placeholder="Search product…"
          value={product}
          onChange={handleProductChange}
        />
      </div>

      {loading ? (
        <div className="page-state">Loading…</div>
      ) : error ? (
        <div className="page-state error">Error: {error.message}</div>
      ) : (
        <>
          <div className="contracts-table-wrap">
            <table className="contracts-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Product</th>
                  <th>Contract</th>
                  <th>Qty</th>
                  <th>Status</th>
                  <th>Points</th>
                </tr>
              </thead>
              <tbody>
                {data.items.length === 0 ? (
                  <tr><td colSpan={6} style={{ textAlign: 'center', color: '#94a3b8', padding: '32px' }}>No sales found</td></tr>
                ) : data.items.map(s => (
                  <tr key={s.id}>
                    <td>{s.sale_datetime?.slice(0, 10) ?? '—'}</td>
                    <td>{s.product_designation}</td>
                    <td>{s.contract_title}</td>
                    <td>{s.quantity}</td>
                    <td><span className={`badge-status ${s.status}`}>{s.status}</span></td>
                    <td className="td-points">{s.points != null ? s.points.toLocaleString() : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="table-footer">
            <span>{data.total} sale{data.total !== 1 ? 's' : ''}</span>
            {data.pages > 1 && (
              <div className="pagination">
                <button disabled={!data.has_prev} onClick={() => setPage(p => p - 1)}>← Prev</button>
                <span>Page {data.page} of {data.pages}</span>
                <button disabled={!data.has_next} onClick={() => setPage(p => p + 1)}>Next →</button>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}
