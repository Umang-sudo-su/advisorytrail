import { NavLink, Outlet, useLocation } from 'react-router-dom';
import { LayoutDashboard, Library, ScanLine, Search, ShieldCheck, ClipboardList, Shield } from 'lucide-react';

const navItems = [
  { to: '/dashboard',    label: 'Dashboard',    icon: LayoutDashboard },
  { to: '/repositories', label: 'Repositories', icon: Library },
  { to: '/scans',        label: 'Scans',        icon: ScanLine },
  { to: '/findings',     label: 'Findings',     icon: Search },
  { to: '/policies',     label: 'Policies',     icon: ShieldCheck },
  { to: '/audit-logs',   label: 'Audit Logs',   icon: ClipboardList },
];

export default function Layout() {
  const { pathname } = useLocation();
  const current = navItems.find((item) => item.to === pathname);

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <Shield aria-hidden="true" />
          <span>BuildShield</span>
        </div>

        <nav aria-label="Main">
          {navItems.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} className="nav-link">
              <Icon aria-hidden="true" size={20} />
              {label}
            </NavLink>
          ))}
        </nav>
      </aside>

      <div className="main">
        <header className="topbar">
          <h1>{current?.label ?? 'BuildShield'}</h1>
        </header>
        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}