import { useEffect, useState } from 'react'
import { apiFetch } from '../api/client'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Building2, User, CheckCircle2, XCircle } from 'lucide-react'

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

  if (loading) return <div className="flex items-center justify-center h-[60vh] text-slate-500">Loading…</div>
  if (error)   return <div className="flex items-center justify-center h-[60vh] text-red-500">Error: {error.message}</div>

  const { account, user, email_verified } = data

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Pharmacy</h1>
        <p className="text-sm text-slate-500 mt-1">Your account and user details</p>
      </div>

      <div className="grid grid-cols-2 gap-6">
        <InfoCard title="Account" icon={Building2}>
          <InfoRow label="Name"   value={account.name} />
          <InfoRow label="Code"   value={account.code} />
          <InfoRow label="City"   value={account.city} />
          <InfoRow label="Phone"  value={account.phone} />
          <InfoRow label="Email"  value={account.email} />
          <InfoRow label="Status" value={
            <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold border ${
              account.status === 'active'
                ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                : 'bg-slate-100 text-slate-500 border-slate-200'
            }`}>{account.status}</span>
          } />
        </InfoCard>

        <InfoCard title="User" icon={User}>
          <InfoRow label="Name"     value={`${user.first_name} ${user.last_name}`.trim() || '—'} />
          <InfoRow label="Username" value={user.username} />
          <InfoRow label="Email"    value={user.email} />
          <InfoRow label="Verified" value={
            <span className={`inline-flex items-center gap-1 text-xs font-semibold ${email_verified ? 'text-emerald-600' : 'text-slate-400'}`}>
              {email_verified
                ? <><CheckCircle2 size={13} /> Verified</>
                : <><XCircle size={13} /> Not verified</>}
            </span>
          } />
        </InfoCard>
      </div>
    </div>
  )
}

function InfoCard({ title, icon: Icon, children }) {
  return (
    <Card className="border-slate-200 shadow-sm">
      <CardHeader className="pb-2 border-b border-slate-100">
        <CardTitle className="flex items-center gap-2 text-xs font-semibold text-slate-500 uppercase tracking-wider">
          <Icon size={14} />
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        {children}
      </CardContent>
    </Card>
  )
}

function InfoRow({ label, value }) {
  return (
    <div className="flex items-center justify-between px-5 py-3 border-b border-slate-50 last:border-0 text-sm">
      <span className="text-slate-400 text-xs font-medium">{label}</span>
      <span className="text-slate-800 font-medium">{value ?? '—'}</span>
    </div>
  )
}
