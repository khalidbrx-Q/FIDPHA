import { useEffect, useState } from 'react'
import { apiFetch } from '../api/client'

export default function Pharmacy() {
  const [data, setData]     = useState(null)
  const [error, setError]   = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    apiFetch('/account/')
      .then(setData)
      .catch(setError)
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="page-state">Loading…</div>
  if (error)   return <div className="page-state error">Error: {error.message}</div>

  const { account, user, email_verified } = data

  return (
    <div className="pharmacy-page">
      <h1>Pharmacy</h1>

      <div className="info-grid">
        <InfoCard title="Account">
          <InfoRow label="Name"     value={account.name} />
          <InfoRow label="Code"     value={account.code} />
          <InfoRow label="City"     value={account.city} />
          <InfoRow label="Phone"    value={account.phone} />
          <InfoRow label="Email"    value={account.email} />
          <InfoRow label="Status"   value={<span className={`badge-status ${account.status}`}>{account.status}</span>} />
        </InfoCard>

        <InfoCard title="User">
          <InfoRow label="Name"     value={`${user.first_name} ${user.last_name}`.trim() || '—'} />
          <InfoRow label="Username" value={user.username} />
          <InfoRow label="Email"    value={user.email} />
          <InfoRow label="Verified" value={email_verified ? '✓ Verified' : '✗ Not verified'} />
        </InfoCard>
      </div>
    </div>
  )
}

function InfoCard({ title, children }) {
  return (
    <div className="info-card">
      <div className="info-card-title">{title}</div>
      <div className="info-rows">{children}</div>
    </div>
  )
}

function InfoRow({ label, value }) {
  return (
    <div className="info-row">
      <span className="info-label">{label}</span>
      <span className="info-value">{value ?? '—'}</span>
    </div>
  )
}
