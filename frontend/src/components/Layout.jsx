import { NavLink, Outlet, useNavigate } from 'react-router-dom'

const NAV = [
  { to: '/dashboard', label: 'Dashboard',  icon: '▦' },
  { to: '/contracts', label: 'Contracts',  icon: '📄' },
  { to: '/sales',     label: 'Points',     icon: '⭐' },
  { to: '/pharmacy',  label: 'Pharmacy',   icon: '🏪' },
]

export default function Layout() {
  const navigate = useNavigate()

  function handleLogout() {
    fetch('/admin/logout/', { credentials: 'include' })
      .finally(() => navigate('/portal/login/'))
  }

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="sidebar-brand">WinInPharma</div>

        <nav className="sidebar-nav">
          {NAV.map(({ to, label, icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) => 'nav-item' + (isActive ? ' active' : '')}
            >
              <span className="nav-icon">{icon}</span>
              {label}
            </NavLink>
          ))}
        </nav>

        <button className="sidebar-logout" onClick={handleLogout}>
          ⏻ Logout
        </button>
      </aside>

      <main className="main-content">
        <Outlet />
      </main>
    </div>
  )
}
