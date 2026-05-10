import { useEffect, useState } from 'react'
import ReactECharts from 'echarts-for-react'
import { apiFetch } from '../api/client'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Separator } from '@/components/ui/separator'
import {
  TrendingUp, TrendingDown, Minus,
  Package, FileText, Award, Zap, ArrowLeft,
  ShoppingCart, Calendar, Activity,
} from 'lucide-react'

// ── Helpers ─────────────────────────────────────────────────────────────────

function greeting() {
  const h = new Date().getHours()
  if (h < 12) return 'Good morning'
  if (h < 18) return 'Good afternoon'
  return 'Good evening'
}

function trend(current, previous) {
  if (!previous) return null
  const pct = Math.round(((current - previous) / previous) * 100)
  return pct
}

// ── Main page ────────────────────────────────────────────────────────────────

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

  const years = Object.keys(charts.years_monthly)

  // Derive month-over-month trends from the last two months of chart data
  const n = charts.month_pts.length
  const ptsThisMonth  = charts.month_pts[n - 1]  ?? 0
  const ptsLastMonth  = charts.month_pts[n - 2]  ?? 0
  const unitsThisMonth = charts.month_units[n - 1] ?? 0
  const unitsLastMonth = charts.month_units[n - 2] ?? 0

  const today = new Date().toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })

  return (
    <div className="space-y-7">

      {/* ── Page header ─────────────────────────────────────────────────── */}
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm font-medium text-slate-500">{today}</p>
          <h1 className="text-2xl font-bold text-slate-900 mt-0.5">{greeting()}</h1>
        </div>
        {stats.active_contract && (
          <div className="flex items-center gap-2 bg-blue-50 border border-blue-100 rounded-xl px-4 py-2.5">
            <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            <div>
              <p className="text-xs text-blue-500 font-medium uppercase tracking-wide">Active Contract</p>
              <p className="text-sm font-semibold text-blue-900 leading-tight">{stats.active_contract.title}</p>
            </div>
          </div>
        )}
      </div>

      {/* ── KPI cards row ────────────────────────────────────────────────── */}
      <div className="grid grid-cols-4 gap-4">
        <KpiCard
          label="Total Points"
          value={stats.total_points.toLocaleString()}
          icon={Award}
          color="blue"
        />
        <KpiCard
          label="Points This Month"
          value={ptsThisMonth.toLocaleString()}
          icon={TrendingUp}
          color="violet"
          trend={trend(ptsThisMonth, ptsLastMonth)}
        />
        <KpiCard
          label="Units This Month"
          value={unitsThisMonth.toLocaleString()}
          icon={ShoppingCart}
          color="emerald"
          trend={trend(unitsThisMonth, unitsLastMonth)}
        />
        <KpiCard
          label="Products in Contract"
          value={stats.products_count}
          icon={Package}
          color="amber"
        />
      </div>

      {/* ── Charts row 1 ─────────────────────────────────────────────────── */}
      <div className="grid grid-cols-3 gap-4">
        {/* Points — drillable */}
        <Card className="col-span-2 border-slate-200 shadow-sm">
          <CardHeader className="pb-2 flex flex-row items-center justify-between">
            <div>
              <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                {drillPts ? `Daily Breakdown` : 'Monthly Points'}
              </p>
              <p className="text-sm font-semibold text-slate-700 mt-0.5">
                {drillPts ? drillPts.label : 'Last 12 months'}
              </p>
            </div>
            {drillPts ? (
              <button
                onClick={() => setDrillPts(null)}
                className="flex items-center gap-1.5 text-xs font-medium text-blue-600 hover:text-blue-800 bg-blue-50 hover:bg-blue-100 px-3 py-1.5 rounded-lg transition-colors"
              >
                <ArrowLeft size={12} /> Back to overview
              </button>
            ) : (
              <span className="text-xs text-slate-400 italic">Click a bar to drill down</span>
            )}
          </CardHeader>
          <Separator className="mb-0" />
          <CardContent className="pt-3 pb-3">
            {drillPts ? (
              <ReactECharts
                option={dailyDrillOption(charts, drillPts.key, 'pts', '#6366f1', '#4f46e5')}
                style={{ height: 220 }}
              />
            ) : (
              <ReactECharts
                option={monthlyPtsOption(charts)}
                style={{ height: 220 }}
                onEvents={{ click: (p) => {
                  const key = charts.month_keys[p.dataIndex]
                  if (key && charts.daily_drill[key])
                    setDrillPts({ key, label: charts.month_labels[p.dataIndex] })
                }}}
              />
            )}
          </CardContent>
        </Card>

        {/* Top products */}
        <Card className="border-slate-200 shadow-sm">
          <CardHeader className="pb-2">
            <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Top Products</p>
            <p className="text-sm font-semibold text-slate-700 mt-0.5">By points earned</p>
          </CardHeader>
          <Separator className="mb-0" />
          <CardContent className="pt-3 pb-3">
            <ReactECharts option={topProductsOption(charts)} style={{ height: 220 }} />
          </CardContent>
        </Card>
      </div>

      {/* ── Charts row 2 ─────────────────────────────────────────────────── */}
      <div className="grid grid-cols-3 gap-4">
        {/* Cumulative */}
        <Card className="col-span-2 border-slate-200 shadow-sm">
          <CardHeader className="pb-2 flex flex-row items-center justify-between">
            <div>
              <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Cumulative Points</p>
              <p className="text-sm font-semibold text-slate-700 mt-0.5">Growth trajectory</p>
            </div>
            <div className="flex gap-1">
              {years.map(y => (
                <button
                  key={y}
                  onClick={() => setYear(y)}
                  className={`px-3 py-1 rounded-lg text-xs font-semibold border transition-colors ${
                    year === y
                      ? 'bg-violet-600 text-white border-violet-600'
                      : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50'
                  }`}
                >{y}</button>
              ))}
            </div>
          </CardHeader>
          <Separator className="mb-0" />
          <CardContent className="pt-3 pb-3">
            <ReactECharts option={year ? cumulOption(charts, year) : {}} style={{ height: 220 }} />
          </CardContent>
        </Card>

        {/* Units — drillable */}
        <Card className="border-slate-200 shadow-sm">
          <CardHeader className="pb-2 flex flex-row items-center justify-between">
            <div>
              <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                {drillUnits ? 'Daily Breakdown' : 'Monthly Units'}
              </p>
              <p className="text-sm font-semibold text-slate-700 mt-0.5">
                {drillUnits ? drillUnits.label : 'Last 12 months'}
              </p>
            </div>
            {drillUnits && (
              <button
                onClick={() => setDrillUnits(null)}
                className="flex items-center gap-1.5 text-xs font-medium text-emerald-600 hover:text-emerald-800 bg-emerald-50 hover:bg-emerald-100 px-3 py-1.5 rounded-lg transition-colors"
              >
                <ArrowLeft size={12} /> Back
              </button>
            )}
          </CardHeader>
          <Separator className="mb-0" />
          <CardContent className="pt-3 pb-3">
            {drillUnits ? (
              <ReactECharts
                option={dailyDrillOption(charts, drillUnits.key, 'units', '#34d399', '#059669')}
                style={{ height: 220 }}
              />
            ) : (
              <ReactECharts
                option={monthlyUnitsOption(charts)}
                style={{ height: 220 }}
                onEvents={{ click: (p) => {
                  const key = charts.month_keys[p.dataIndex]
                  if (key && charts.daily_drill[key])
                    setDrillUnits({ key, label: charts.month_labels[p.dataIndex] })
                }}}
              />
            )}
          </CardContent>
        </Card>
      </div>

      {/* ── Recent sales ─────────────────────────────────────────────────── */}
      <Card className="border-slate-200 shadow-sm">
        <CardHeader className="pb-2 flex flex-row items-center justify-between">
          <div>
            <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Recent Sales</p>
            <p className="text-sm font-semibold text-slate-700 mt-0.5">Latest submissions</p>
          </div>
          <span className="text-xs text-slate-400 bg-slate-100 px-2.5 py-1 rounded-full font-medium">
            {recent.items.length} entries
          </span>
        </CardHeader>
        <Separator />
        <CardContent className="p-0">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-100">
                {['Date', 'Product', 'Contract', 'Qty', 'Status', 'Points'].map(h => (
                  <th key={h} className="text-left px-5 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {recent.items.length === 0 ? (
                <tr>
                  <td colSpan={6} className="text-center py-10 text-slate-400">
                    No sales yet
                  </td>
                </tr>
              ) : recent.items.map((s, i) => (
                <tr
                  key={s.id}
                  className={`border-b border-slate-50 hover:bg-slate-50 transition-colors ${i === recent.items.length - 1 ? 'border-0' : ''}`}
                >
                  <td className="px-5 py-3.5 text-slate-500 text-xs font-medium">{s.sale_datetime?.slice(0, 10)}</td>
                  <td className="px-5 py-3.5 font-semibold text-slate-800">{s.product_designation}</td>
                  <td className="px-5 py-3.5 text-slate-500">{s.contract_title}</td>
                  <td className="px-5 py-3.5 text-slate-600 font-medium">{s.quantity}</td>
                  <td className="px-5 py-3.5"><StatusBadge status={s.status} /></td>
                  <td className="px-5 py-3.5">
                    <span className="font-bold text-violet-600">{s.points?.toLocaleString() ?? '—'}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  )
}

// ── Sub-components ───────────────────────────────────────────────────────────

const COLOR_MAP = {
  blue:    { bg: 'bg-blue-500',    light: 'bg-blue-50',    text: 'text-blue-600',    border: 'border-l-blue-500' },
  violet:  { bg: 'bg-violet-500',  light: 'bg-violet-50',  text: 'text-violet-600',  border: 'border-l-violet-500' },
  emerald: { bg: 'bg-emerald-500', light: 'bg-emerald-50', text: 'text-emerald-600', border: 'border-l-emerald-500' },
  amber:   { bg: 'bg-amber-500',   light: 'bg-amber-50',   text: 'text-amber-600',   border: 'border-l-amber-500' },
}

function KpiCard({ label, value, icon: Icon, color, trend: trendVal }) {
  const c = COLOR_MAP[color] ?? COLOR_MAP.blue
  const hasTrend = trendVal !== null && trendVal !== undefined

  return (
    <div className={`bg-white rounded-xl border border-slate-200 border-l-4 ${c.border} shadow-sm p-5`}>
      <div className="flex items-start justify-between">
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider truncate">{label}</p>
          <p className={`text-2xl font-bold mt-1.5 ${c.text}`}>{value ?? 0}</p>
        </div>
        <div className={`p-2.5 rounded-xl ${c.light} shrink-0 ml-3`}>
          <Icon size={18} className={c.text} />
        </div>
      </div>
      {hasTrend && (
        <div className="mt-3 flex items-center gap-1.5">
          {trendVal > 0
            ? <TrendingUp size={13} className="text-emerald-500" />
            : trendVal < 0
            ? <TrendingDown size={13} className="text-red-400" />
            : <Minus size={13} className="text-slate-400" />}
          <span className={`text-xs font-semibold ${trendVal > 0 ? 'text-emerald-600' : trendVal < 0 ? 'text-red-500' : 'text-slate-400'}`}>
            {trendVal > 0 ? '+' : ''}{trendVal}%
          </span>
          <span className="text-xs text-slate-400">vs last month</span>
        </div>
      )}
    </div>
  )
}

function StatusBadge({ status }) {
  const cls = {
    accepted: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    rejected: 'bg-red-50 text-red-600 border-red-200',
    pending:  'bg-amber-50 text-amber-700 border-amber-200',
  }
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold border ${cls[status] ?? cls.pending}`}>
      {status}
    </span>
  )
}

function Spinner() {
  return (
    <div className="flex flex-col items-center justify-center h-[60vh] gap-3">
      <div className="w-8 h-8 border-2 border-blue-200 border-t-blue-600 rounded-full animate-spin" />
      <p className="text-sm text-slate-500">Loading dashboard…</p>
    </div>
  )
}

function ErrorState({ message }) {
  return (
    <div className="flex items-center justify-center h-[60vh] text-red-500 text-sm">
      Error: {message}
    </div>
  )
}

// ── Chart option builders ────────────────────────────────────────────────────

function dailyDrillOption(c, monthKey, field, colorTop, colorBottom) {
  const drill = c.daily_drill[monthKey]
  if (!drill) return {}
  const labels = Array.from({ length: drill.n }, (_, i) => i + 1)
  return {
    tooltip: { trigger: 'axis', formatter: (p) => `Day ${p[0].axisValue}: ${p[0].value.toLocaleString()}` },
    grid: { left: 44, right: 12, top: 12, bottom: 32 },
    xAxis: {
      type: 'category', data: labels,
      axisLabel: { fontSize: 10, color: '#94a3b8', interval: 4 },
      axisLine: { lineStyle: { color: '#e2e8f0' } },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value',
      axisLabel: { fontSize: 10, color: '#94a3b8' },
      splitLine: { lineStyle: { color: '#f8fafc' } },
    },
    series: [{
      type: 'bar', data: drill[field], barMaxWidth: 14,
      cursor: 'default',
      itemStyle: {
        color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [{ offset: 0, color: colorTop }, { offset: 1, color: colorBottom }] },
        borderRadius: [3, 3, 0, 0],
      },
    }],
  }
}

function monthlyPtsOption(c) {
  return {
    tooltip: {
      trigger: 'axis',
      formatter: (p) => `${p[0].axisValue}<br/><b>${p[0].value.toLocaleString()} pts</b><br/><span style="color:#94a3b8;font-size:11px">Click to see daily breakdown</span>`,
    },
    grid: { left: 44, right: 12, top: 12, bottom: 32 },
    xAxis: {
      type: 'category', data: c.month_labels,
      axisLabel: { fontSize: 11, color: '#94a3b8' },
      axisLine: { lineStyle: { color: '#e2e8f0' } },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value',
      axisLabel: { fontSize: 11, color: '#94a3b8' },
      splitLine: { lineStyle: { color: '#f8fafc' } },
    },
    series: [{
      type: 'bar', data: c.month_pts, barMaxWidth: 28, cursor: 'pointer',
      itemStyle: {
        color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [{ offset: 0, color: '#818cf8' }, { offset: 1, color: '#4f46e5' }] },
        borderRadius: [4, 4, 0, 0],
      },
      emphasis: { itemStyle: { opacity: 0.85 } },
    }],
  }
}

function monthlyUnitsOption(c) {
  return {
    tooltip: {
      trigger: 'axis',
      formatter: (p) => `${p[0].axisValue}<br/><b>${p[0].value.toLocaleString()} units</b><br/><span style="color:#94a3b8;font-size:11px">Click to see daily breakdown</span>`,
    },
    grid: { left: 44, right: 12, top: 12, bottom: 32 },
    xAxis: {
      type: 'category', data: c.month_labels,
      axisLabel: { fontSize: 11, color: '#94a3b8' },
      axisLine: { lineStyle: { color: '#e2e8f0' } },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value',
      axisLabel: { fontSize: 11, color: '#94a3b8' },
      splitLine: { lineStyle: { color: '#f8fafc' } },
    },
    series: [{
      type: 'bar', data: c.month_units, barMaxWidth: 28, cursor: 'pointer',
      itemStyle: {
        color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [{ offset: 0, color: '#34d399' }, { offset: 1, color: '#059669' }] },
        borderRadius: [4, 4, 0, 0],
      },
      emphasis: { itemStyle: { opacity: 0.85 } },
    }],
  }
}

function cumulOption(c, year) {
  const yd = c.years_monthly[year]
  if (!yd) return {}
  return {
    tooltip: { trigger: 'axis' },
    grid: { left: 52, right: 12, top: 12, bottom: 32 },
    xAxis: {
      type: 'category', data: yd.labels,
      axisLabel: { fontSize: 11, color: '#94a3b8' },
      axisLine: { lineStyle: { color: '#e2e8f0' } },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value',
      axisLabel: { fontSize: 11, color: '#94a3b8' },
      splitLine: { lineStyle: { color: '#f8fafc' } },
    },
    series: [{
      type: 'line', data: yd.cumul,
      smooth: true, symbol: 'circle', symbolSize: 5,
      lineStyle: { color: '#8b5cf6', width: 2.5 },
      itemStyle: { color: '#8b5cf6' },
      areaStyle: {
        color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: 'rgba(139,92,246,.18)' },
            { offset: 1, color: 'rgba(139,92,246,0)' },
          ],
        },
      },
    }],
  }
}

function topProductsOption(c) {
  const labels = c.top_product_labels.slice(0, 7)
  const data   = c.top_product_data.slice(0, 7)
  return {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: 110, right: 20, top: 8, bottom: 20 },
    xAxis: {
      type: 'value',
      axisLabel: { fontSize: 10, color: '#94a3b8' },
      splitLine: { lineStyle: { color: '#f8fafc' } },
    },
    yAxis: {
      type: 'category', data: labels,
      axisLabel: { fontSize: 10, color: '#475569', width: 100, overflow: 'truncate' },
    },
    series: [{
      type: 'bar', data, barMaxWidth: 18,
      itemStyle: {
        color: { type: 'linear', x: 0, y: 0, x2: 1, y2: 0,
          colorStops: [{ offset: 0, color: '#fbbf24' }, { offset: 1, color: '#f97316' }] },
        borderRadius: [0, 4, 4, 0],
      },
    }],
  }
}
