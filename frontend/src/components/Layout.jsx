import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { LayoutDashboard, FileText, Star, Building2, LogOut } from 'lucide-react'
import { Separator } from '@/components/ui/separator'
import { cn } from '@/lib/utils'

const NAV = [
  { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/contracts', label: 'Contracts', icon: FileText },
  { to: '/sales',     label: 'Points',    icon: Star },
  { to: '/pharmacy',  label: 'Pharmacy',  icon: Building2 },
]

export default function Layout() {
  const navigate = useNavigate()

  async function handleLogout() {
    await fetch('/admin/logout/', { method: 'POST', credentials: 'include' })
    navigate('/portal/login/')
  }

  return (
    <div className="flex min-h-screen bg-slate-50">
      {/* Sidebar */}
      <aside className="w-56 shrink-0 flex flex-col bg-slate-900 text-slate-100">
        <div className="px-5 py-6">
          <span className="text-base font-bold tracking-wide text-white">WinInPharma</span>
          <p className="text-xs text-slate-400 mt-0.5">Pharmacy Portal</p>
        </div>

        <Separator className="bg-slate-700 mx-3 w-auto" />

        <nav className="flex-1 px-3 py-4 space-y-1">
          {NAV.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors',
                  isActive
                    ? 'bg-blue-600 text-white'
                    : 'text-slate-400 hover:bg-slate-800 hover:text-slate-100'
                )
              }
            >
              <Icon size={16} strokeWidth={2} />
              {label}
            </NavLink>
          ))}
        </nav>

        <Separator className="bg-slate-700 mx-3 w-auto" />

        <div className="px-3 py-4">
          <button
            onClick={handleLogout}
            className="flex items-center gap-3 px-3 py-2.5 w-full rounded-lg text-sm font-medium text-slate-400 hover:bg-slate-800 hover:text-red-400 transition-colors"
          >
            <LogOut size={16} strokeWidth={2} />
            Logout
          </button>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 min-w-0 p-8">
        <Outlet />
      </main>
    </div>
  )
}
