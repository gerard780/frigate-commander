import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import JobList from './pages/JobList'
import JobNew from './pages/JobNew'
import JobDetail from './pages/JobDetail'
import Files from './pages/Files'
import Settings from './pages/Settings'

function NavItem({ to, children }: { to: string; children: React.ReactNode }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        `px-4 py-2 rounded-lg font-medium transition-colors ${
          isActive
            ? 'bg-frigate-600 text-white'
            : 'text-gray-600 hover:bg-gray-100'
        }`
      }
    >
      {children}
    </NavLink>
  )
}

function Layout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen">
      <header className="bg-white shadow-sm border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center gap-2">
              <svg className="w-8 h-8 text-frigate-600" viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" />
              </svg>
              <span className="text-xl font-bold text-gray-900">Frigate Commander</span>
            </div>
            <nav className="flex items-center gap-1">
              <NavItem to="/">Dashboard</NavItem>
              <NavItem to="/jobs">Jobs</NavItem>
              <NavItem to="/jobs/new">New Job</NavItem>
              <NavItem to="/files">Files</NavItem>
              <NavItem to="/settings">Settings</NavItem>
            </nav>
          </div>
        </div>
      </header>
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {children}
      </main>
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/jobs" element={<JobList />} />
          <Route path="/jobs/new" element={<JobNew />} />
          <Route path="/jobs/:id" element={<JobDetail />} />
          <Route path="/files" element={<Files />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  )
}
