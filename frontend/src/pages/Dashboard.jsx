import { useEffect, useState } from 'react'
import ReactECharts from 'echarts-for-react'
import { apiFetch } from '../api/client'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Separator } from '@/components/ui/separator'
import {
  TrendingUp, TrendingDown, Minus,
  Award, ShoppingCart, CheckCircle2,
  ArrowLeft, AlertTriangle,
} from 'lucide-react'

// ── Utilities ────────────────────────────────────────────────────────────────

function greeting() {
  const h = new Date().getHours()
  if (h < 12) return 'Good morning'
  if (h < 18) return 'Good afternoon'
  return 'Good evening'
}

function pct(current, previous) {
  if (!previous) return null
  return Math.round(((current - previous) / previous) * 100)
}

function fmtDate() {
  return new Date().toLocaleDateString('en-US', {
    weekday: 'long', year: 'numeric', month: 'long', day: 'numeric',
  })
}

// ── Main component ───────────────────────────────────────────────────────────

export default function Dashboard() {
  const [stats,      setStats]      = useState(null)
  const [charts,     setCharts]     = useState(null)
  const [recent,     setRecent]     = useState(null)
  const [year,       setYear]       = useState(null)
  const [drillPts,   setDrillPts]   = useState(null)
  const [drillUnits, setDrillUnits] = useState(null)
  const [loading,    setLoading]    = useState(true)
  const [error,      setError]      = useState(null)

  useEffect(() => {
    Promise.all([
      apiFetch('/dashboard/stats/'),
      apiFetch('/dashboard/charts/'),
      apiFetch('/dashboard/recent-sales/'),
    ])
      .then(([s, c, r]) => {
        setStats(s); setCharts(c); setRecent(r)
        const years = Object.keys(c.years_monthly)
        setYear(years[years.length - 1])
      })
      .catch(setError)
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <Spinner />
  if (error)   return <ErrorState message={error.message} />

  const years      = Object.keys(charts.years_monthly)
  const ptsTrend   = pct(stats.this_month_points, stats.last_month_points)
  const unitsTrend = pct(stats.this_month_units,  stats.last_month_units)

  return (
    <div className="space-y-6 max-w-[1400px]">

      {/* ── Header ──────────────────────────────────────────────────── */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs font-medium text-slate-400 uppercase tracking-widest">{fmtDate()}</p>
          <h1 className="text-2xl font-bold text-slate-900 mt-1">{greeting()}</h1>
        </div>
        <div className="flex items-center gap-3 shrink-0">
          {stats.pending_count > 0 && (
            <div className="flex items-center gap-2 bg-amber-50 border border-amber-200 text-amber-700 rounded-xl px-4 py-2.5 text-sm font-medium">
              <AlertTriangle size={14} />
              {stats.pending_count} pending review
            </div>
          )}
          {stats.active_contract && (
            <div className="flex items-center gap-2.5 bg-slate-900 rounded-xl px-4 py-2.5">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse shrink-0" />
              <div>
                <p className="text-[10px] text-slate-400 uppercase tracking-widest font-semibold leading-none mb-0.5">Active contract</p>
                <p className="text-sm font-semibold text-white leading-none">{stats.active_contract.title}</p>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ── KPI cards ───────────────────────────────────────────────── */}
      <div className="grid grid-cols-4 gap-4">
        <KpiCard
          label="Total Points" value={stats.total_points.toLocaleString()}
          icon={Award} color="blue" sub="All time"
        />
        <KpiCard
          label="This Month" value={stats.this_month_points.toLocaleString()}
          icon={TrendingUp} color="violet" trend={ptsTrend} sub="Points earned"
        />
        <KpiCard
          label="Units Sold" value={stats.this_month_units.toLocaleString()}
          icon={ShoppingCart} color="emerald" trend={unitsTrend} sub="This month"
        />
        <KpiCard
          label="Acceptance Rate"
          value={stats.acceptance_rate != null ? `${stats.acceptance_rate}%` : '—'}
          icon={CheckCircle2} color="teal" sub="Last 30 days"
          extra={stats.acceptance_rate != null && (
            <div className="mt-3">
              <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
                <div className="h-full bg-teal-500 rounded-full" style={{ width: `${stats.acceptance_rate}%` }} />
              </div>
            </div>
          )}
        />
      </div>

      {/* ── Row 1: Monthly Points + Acceptance Donut ────────────────── */}
      <div className="grid grid-cols-3 gap-4">
        <ChartCard
          className="col-span-2"
          label="Monthly Points" title={drillPts ? drillPts.label : 'Last 12 months'}
          action={drillPts && <BackBtn onClick={() => setDrillPts(null)} color="violet" />}
          hint={!drillPts && <span className="text-xs text-slate-400 italic">Click a bar to drill down</span>}
        >
          {drillPts
            ? <ReactECharts option={dailyDrillOption(charts, drillPts.key, 'pts', '#818cf8', '#4f46e5')} style={{ height: 230 }} />
            : <ReactECharts
                option={monthlyPtsOption(charts)} style={{ height: 230 }}
                onEvents={{ click: p => {
                  const key = charts.month_keys[p.dataIndex]
                  if (key && charts.daily_drill[key]) setDrillPts({ key, label: charts.month_labels[p.dataIndex] })
                }}}
              />
          }
        </ChartCard>

        <ChartCard label="Acceptance" title="Last 30 days — by status">
          <ReactECharts option={acceptanceDonutOption(stats.acceptance_stats)} style={{ height: 200 }} />
          <div className="flex justify-center gap-5 pb-1 -mt-1 flex-wrap">
            <Legend color="#10b981" label={`${stats.acceptance_stats.accepted} accepted`} />
            <Legend color="#f87171" label={`${stats.acceptance_stats.rejected} rejected`} />
            <Legend color="#fbbf24" label={`${stats.acceptance_stats.pending} pending`} />
          </div>
        </ChartCard>
      </div>

      {/* ── Row 2: Cumulative + Top Products ────────────────────────── */}
      <div className="grid grid-cols-2 gap-4">
        <ChartCard
          label="Cumulative Points" title="Growth trajectory"
          action={
            <div className="flex gap-1">
              {years.map(y => (
                <button key={y} onClick={() => setYear(y)}
                  className={`px-2.5 py-1 rounded-lg text-xs font-semibold border transition-colors ${
                    year === y ? 'bg-violet-600 text-white border-violet-600' : 'bg-white text-slate-500 border-slate-200 hover:bg-slate-50'
                  }`}
                >{y}</button>
              ))}
            </div>
          }
        >
          <ReactECharts option={year ? cumulOption(charts, year) : {}} style={{ height: 220 }} />
        </ChartCard>

        <ChartCard label="Top Products" title="By points earned">
          <ReactECharts option={topProductsOption(charts)} style={{ height: 220 }} />
        </ChartCard>
      </div>

      {/* ── Row 3: Units + Heatmap ───────────────────────────────────── */}
      <div className="grid grid-cols-3 gap-4">
        <ChartCard
          label="Monthly Units" title={drillUnits ? drillUnits.label : 'Last 12 months'}
          action={drillUnits && <BackBtn onClick={() => setDrillUnits(null)} color="emerald" />}
          hint={!drillUnits && <span className="text-xs text-slate-400 italic">Click to drill down</span>}
        >
          {drillUnits
            ? <ReactECharts option={dailyDrillOption(charts, drillUnits.key, 'units', '#34d399', '#059669')} style={{ height: 200 }} />
            : <ReactECharts
                option={monthlyUnitsOption(charts)} style={{ height: 200 }}
                onEvents={{ click: p => {
                  const key = charts.month_keys[p.dataIndex]
                  if (key && charts.daily_drill[key]) setDrillUnits({ key, label: charts.month_labels[p.dataIndex] })
                }}}
              />
          }
        </ChartCard>

        <div className="col-span-2">
          <ActivityHeatmap daily_drill={charts.daily_drill} />
        </div>
      </div>

      {/* ── Recent Sales ─────────────────────────────────────────────── */}
      <Card className="border-slate-200 shadow-sm">
        <div className="flex items-center justify-between px-5 pt-4 pb-3">
          <div>
            <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Recent Sales</p>
            <p className="text-sm font-semibold text-slate-700 mt-0.5">Latest submissions</p>
          </div>
          <span className="text-xs text-slate-500 bg-slate-100 px-2.5 py-1 rounded-full font-medium">
            {recent.items.length} entries
          </span>
        </div>
        <Separator />
        <CardContent className="p-0">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-100">
                {['Date', 'Product', 'Contract', 'Qty', 'Status', 'Points'].map(h => (
                  <th key={h} className="text-left px-5 py-3 text-[10px] font-bold text-slate-400 uppercase tracking-widest">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {recent.items.length === 0
                ? <tr><td colSpan={6} className="text-center py-10 text-slate-400">No sales yet</td></tr>
                : recent.items.map((s, i) => (
                  <tr key={s.id} className={`hover:bg-slate-50/70 transition-colors ${i < recent.items.length - 1 ? 'border-b border-slate-50' : ''}`}>
                    <td className="px-5 py-3.5 text-xs text-slate-400 font-medium tabular-nums">{s.sale_datetime?.slice(0, 10)}</td>
                    <td className="px-5 py-3.5 font-semibold text-slate-800">{s.product_designation}</td>
                    <td className="px-5 py-3.5 text-slate-500">{s.contract_title}</td>
                    <td className="px-5 py-3.5 text-slate-600 font-medium tabular-nums">{s.quantity}</td>
                    <td className="px-5 py-3.5"><StatusBadge status={s.status} /></td>
                    <td className="px-5 py-3.5 font-bold text-violet-600 tabular-nums">{s.points?.toLocaleString() ?? '—'}</td>
                  </tr>
                ))
              }
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  )
}

// ── Layout helpers ───────────────────────────────────────────────────────────

function ChartCard({ label, title, action, hint, children, className = '' }) {
  return (
    <Card className={`border-slate-200 shadow-sm ${className}`}>
      <div className="flex items-center justify-between px-5 pt-4 pb-3">
        <div>
          <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">{label}</p>
          <p className="text-sm font-semibold text-slate-700 mt-0.5">{title}</p>
        </div>
        <div className="flex items-center gap-2">{hint}{action}</div>
      </div>
      <Separator />
      <CardContent className="pt-3 pb-3 px-4">{children}</CardContent>
    </Card>
  )
}

function BackBtn({ onClick, color }) {
  const cls = { violet: 'text-violet-600 bg-violet-50 hover:bg-violet-100', emerald: 'text-emerald-600 bg-emerald-50 hover:bg-emerald-100' }
  return (
    <button onClick={onClick} className={`flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-lg transition-colors ${cls[color]}`}>
      <ArrowLeft size={11} /> Back
    </button>
  )
}

function Legend({ color, label }) {
  return (
    <span className="flex items-center gap-1.5 text-xs text-slate-500">
      <span className="w-2.5 h-2.5 rounded-sm shrink-0" style={{ background: color }} />
      {label}
    </span>
  )
}

// ── KPI Card ─────────────────────────────────────────────────────────────────

const COLORS = {
  blue:    { border: 'border-l-blue-500',    bg: 'bg-blue-50',    text: 'text-blue-600'    },
  violet:  { border: 'border-l-violet-500',  bg: 'bg-violet-50',  text: 'text-violet-600'  },
  emerald: { border: 'border-l-emerald-500', bg: 'bg-emerald-50', text: 'text-emerald-600' },
  teal:    { border: 'border-l-teal-500',    bg: 'bg-teal-50',    text: 'text-teal-600'    },
}

function KpiCard({ label, value, icon: Icon, color, trend, sub, extra }) {
  const c = COLORS[color] ?? COLORS.blue
  return (
    <div className={`bg-white rounded-xl border border-slate-200 border-l-4 ${c.border} shadow-sm p-5`}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest truncate">{label}</p>
          <p className={`text-2xl font-bold mt-1.5 tabular-nums ${c.text}`}>{value}</p>
          <p className="text-xs text-slate-400 mt-0.5">{sub}</p>
        </div>
        <div className={`p-2.5 rounded-xl ${c.bg} shrink-0`}>
          <Icon size={18} className={c.text} />
        </div>
      </div>
      {trend != null && (
        <div className="flex items-center gap-1.5 mt-3">
          {trend > 0 ? <TrendingUp size={12} className="text-emerald-500" />
            : trend < 0 ? <TrendingDown size={12} className="text-red-400" />
            : <Minus size={12} className="text-slate-400" />}
          <span className={`text-xs font-bold ${trend > 0 ? 'text-emerald-600' : trend < 0 ? 'text-red-500' : 'text-slate-400'}`}>
            {trend > 0 ? '+' : ''}{trend}%
          </span>
          <span className="text-xs text-slate-400">vs last month</span>
        </div>
      )}
      {extra}
    </div>
  )
}

// ── Activity Heatmap ─────────────────────────────────────────────────────────

const DOW_LABELS = ['M', 'T', 'W', 'T', 'F', 'S', 'S']

function buildHeatmap(daily_drill) {
  const ptsMap = {}
  for (const [mk, data] of Object.entries(daily_drill)) {
    const [yr, mo] = mk.split('-').map(Number)
    for (let d = 1; d <= data.n; d++) {
      const key = `${yr}-${String(mo).padStart(2, '0')}-${String(d).padStart(2, '0')}`
      ptsMap[key] = data.pts[d - 1] || 0
    }
  }

  const today = new Date()
  const dow = today.getDay()
  const daysToLastMon = dow === 0 ? 6 : dow - 1
  const start = new Date(today)
  start.setDate(today.getDate() - daysToLastMon - 14 * 7)

  const weeks = []
  let week = []
  const cur = new Date(start)
  let maxPts = 1

  for (let i = 0; i < 15 * 7; i++) {
    const key = cur.toISOString().slice(0, 10)
    const pts = ptsMap[key] || 0
    if (pts > maxPts) maxPts = pts
    week.push({ key, pts, future: cur > today, monthStart: cur.getDate() === 1, month: cur.toLocaleDateString('en-US', { month: 'short' }), date: cur.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) })
    if (week.length === 7) { weeks.push(week); week = [] }
    cur.setDate(cur.getDate() + 1)
  }

  return { weeks, maxPts }
}

function heatColor(pts, max) {
  if (pts === 0) return 'bg-slate-100'
  const r = pts / max
  if (r < 0.2)  return 'bg-violet-200'
  if (r < 0.45) return 'bg-violet-400'
  if (r < 0.7)  return 'bg-violet-500'
  return 'bg-violet-700'
}

function ActivityHeatmap({ daily_drill }) {
  const { weeks, maxPts } = buildHeatmap(daily_drill)

  return (
    <Card className="border-slate-200 shadow-sm h-full">
      <div className="px-5 pt-4 pb-3">
        <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Activity</p>
        <p className="text-sm font-semibold text-slate-700 mt-0.5">Daily points — last 15 weeks</p>
      </div>
      <Separator />
      <CardContent className="pt-4 pb-4 px-5">
        <div className="flex gap-2">
          {/* Day-of-week labels */}
          <div className="flex flex-col gap-1 pt-5 shrink-0">
            {DOW_LABELS.map((d, i) => (
              <div key={i} className="h-3.5 flex items-center">
                <span className="text-[9px] text-slate-400 font-medium w-3">{d}</span>
              </div>
            ))}
          </div>

          {/* Week columns */}
          <div className="flex gap-1 flex-1 min-w-0">
            {weeks.map((week, wi) => {
              const monthCell = week.find(c => c.monthStart)
              return (
                <div key={wi} className="flex flex-col gap-1 flex-1 min-w-0">
                  <div className="h-4 flex items-center overflow-hidden">
                    {monthCell && (
                      <span className="text-[9px] text-slate-400 font-semibold leading-none whitespace-nowrap">{monthCell.month}</span>
                    )}
                  </div>
                  {week.map(cell => (
                    <div
                      key={cell.key}
                      title={cell.future ? '' : `${cell.date}: ${cell.pts.toLocaleString()} pts`}
                      className={`h-3.5 rounded-[3px] transition-opacity ${cell.future ? 'bg-slate-50' : heatColor(cell.pts, maxPts)}`}
                    />
                  ))}
                </div>
              )
            })}
          </div>
        </div>

        <div className="flex items-center gap-1.5 mt-3 justify-end">
          <span className="text-[10px] text-slate-400">Less</span>
          {['bg-slate-100', 'bg-violet-200', 'bg-violet-400', 'bg-violet-500', 'bg-violet-700'].map((c, i) => (
            <div key={i} className={`w-3 h-3 rounded-[3px] ${c}`} />
          ))}
          <span className="text-[10px] text-slate-400">More</span>
        </div>
      </CardContent>
    </Card>
  )
}

// ── Status badge ─────────────────────────────────────────────────────────────

function StatusBadge({ status }) {
  const cls = {
    accepted: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    rejected: 'bg-red-50 text-red-600 border-red-200',
    pending:  'bg-amber-50 text-amber-700 border-amber-200',
  }
  return (
    <span className={`inline-flex px-2.5 py-0.5 rounded-full text-xs font-semibold border ${cls[status] ?? cls.pending}`}>
      {status}
    </span>
  )
}

function Spinner() {
  return (
    <div className="flex flex-col items-center justify-center h-[60vh] gap-3">
      <div className="w-7 h-7 border-2 border-violet-200 border-t-violet-600 rounded-full animate-spin" />
      <p className="text-sm text-slate-400">Loading dashboard…</p>
    </div>
  )
}

function ErrorState({ message }) {
  return <div className="flex items-center justify-center h-[60vh] text-red-500 text-sm">Error: {message}</div>
}

// ── Chart option builders ────────────────────────────────────────────────────

function acceptanceDonutOption({ accepted, rejected, pending }) {
  const total = accepted + rejected + pending
  const rate  = total ? Math.round(accepted / total * 100) : 0
  return {
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: { show: false },
    graphic: [{ type: 'text', left: 'center', top: 'center',
      style: { text: `${rate}%`, fontSize: 22, fontWeight: 700, fill: '#1e293b', textAlign: 'center' },
    }],
    series: [{
      type: 'pie', radius: ['52%', '76%'], center: ['50%', '50%'],
      avoidLabelOverlap: false, label: { show: false },
      data: [
        { value: accepted, name: 'Accepted', itemStyle: { color: '#10b981' } },
        { value: rejected, name: 'Rejected', itemStyle: { color: '#f87171' } },
        { value: pending,  name: 'Pending',  itemStyle: { color: '#fbbf24' } },
      ],
      emphasis: { itemStyle: { shadowBlur: 6, shadowColor: 'rgba(0,0,0,.1)' } },
    }],
  }
}

function dailyDrillOption(c, monthKey, field, colorTop, colorBottom) {
  const drill = c.daily_drill[monthKey]
  if (!drill) return {}
  return {
    tooltip: { trigger: 'axis', formatter: p => `Day ${p[0].axisValue}: ${p[0].value.toLocaleString()}` },
    grid: { left: 44, right: 8, top: 8, bottom: 28 },
    xAxis: {
      type: 'category', data: Array.from({ length: drill.n }, (_, i) => i + 1),
      axisLabel: { fontSize: 10, color: '#94a3b8', interval: 4 },
      axisLine: { lineStyle: { color: '#e2e8f0' } }, axisTick: { show: false },
    },
    yAxis: { type: 'value', axisLabel: { fontSize: 10, color: '#94a3b8' }, splitLine: { lineStyle: { color: '#f8fafc' } } },
    series: [{
      type: 'bar', data: drill[field], barMaxWidth: 14, cursor: 'default',
      itemStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: colorTop }, { offset: 1, color: colorBottom }] }, borderRadius: [3, 3, 0, 0] },
    }],
  }
}

function monthlyPtsOption(c) {
  return {
    tooltip: { trigger: 'axis', formatter: p => `${p[0].axisValue}<br/><b>${p[0].value.toLocaleString()} pts</b><br/><span style="color:#94a3b8;font-size:10px">Click to drill down</span>` },
    grid: { left: 44, right: 8, top: 8, bottom: 28 },
    xAxis: { type: 'category', data: c.month_labels, axisLabel: { fontSize: 11, color: '#94a3b8' }, axisLine: { lineStyle: { color: '#e2e8f0' } }, axisTick: { show: false } },
    yAxis: { type: 'value', axisLabel: { fontSize: 11, color: '#94a3b8' }, splitLine: { lineStyle: { color: '#f8fafc' } } },
    series: [{
      type: 'bar', data: c.month_pts, barMaxWidth: 28, cursor: 'pointer',
      itemStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: '#818cf8' }, { offset: 1, color: '#4f46e5' }] }, borderRadius: [4, 4, 0, 0] },
      emphasis: { itemStyle: { opacity: 0.8 } },
    }],
  }
}

function monthlyUnitsOption(c) {
  return {
    tooltip: { trigger: 'axis', formatter: p => `${p[0].axisValue}<br/><b>${p[0].value.toLocaleString()} units</b><br/><span style="color:#94a3b8;font-size:10px">Click to drill down</span>` },
    grid: { left: 44, right: 8, top: 8, bottom: 28 },
    xAxis: { type: 'category', data: c.month_labels, axisLabel: { fontSize: 11, color: '#94a3b8' }, axisLine: { lineStyle: { color: '#e2e8f0' } }, axisTick: { show: false } },
    yAxis: { type: 'value', axisLabel: { fontSize: 11, color: '#94a3b8' }, splitLine: { lineStyle: { color: '#f8fafc' } } },
    series: [{
      type: 'bar', data: c.month_units, barMaxWidth: 28, cursor: 'pointer',
      itemStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: '#34d399' }, { offset: 1, color: '#059669' }] }, borderRadius: [4, 4, 0, 0] },
      emphasis: { itemStyle: { opacity: 0.8 } },
    }],
  }
}

function cumulOption(c, year) {
  const yd = c.years_monthly[year]
  if (!yd) return {}
  return {
    tooltip: { trigger: 'axis' },
    grid: { left: 52, right: 8, top: 8, bottom: 28 },
    xAxis: { type: 'category', data: yd.labels, axisLabel: { fontSize: 11, color: '#94a3b8' }, axisLine: { lineStyle: { color: '#e2e8f0' } }, axisTick: { show: false } },
    yAxis: { type: 'value', axisLabel: { fontSize: 11, color: '#94a3b8' }, splitLine: { lineStyle: { color: '#f8fafc' } } },
    series: [{
      type: 'line', data: yd.cumul, smooth: true, symbol: 'circle', symbolSize: 5,
      lineStyle: { color: '#8b5cf6', width: 2.5 }, itemStyle: { color: '#8b5cf6' },
      areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(139,92,246,.15)' }, { offset: 1, color: 'rgba(139,92,246,0)' }] } },
    }],
  }
}

function topProductsOption(c) {
  const labels = c.top_product_labels.slice(0, 7)
  const data   = c.top_product_data.slice(0, 7)
  return {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: 110, right: 16, top: 8, bottom: 20 },
    xAxis: { type: 'value', axisLabel: { fontSize: 10, color: '#94a3b8' }, splitLine: { lineStyle: { color: '#f8fafc' } } },
    yAxis: { type: 'category', data: labels, axisLabel: { fontSize: 10, color: '#475569', width: 100, overflow: 'truncate' } },
    series: [{
      type: 'bar', data, barMaxWidth: 18,
      itemStyle: { color: { type: 'linear', x: 0, y: 0, x2: 1, y2: 0, colorStops: [{ offset: 0, color: '#fbbf24' }, { offset: 1, color: '#f97316' }] }, borderRadius: [0, 4, 4, 0] },
    }],
  }
}
