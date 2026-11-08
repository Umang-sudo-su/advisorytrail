import { Routes, Route, Navigate, Outlet } from 'react-router-dom';
import Layout from './components/Layout';
import Placeholder from './pages/Placeholder';
import Dashboard from './pages/Dashboard';
import Repositories from './pages/Repositories';
import Scans from './pages/Scans';
import Findings from './pages/Findings';
import Policies from './pages/Policies';
import Login from './pages/Login';

// This wrapper checks for a token before rendering any child routes
function ProtectedRoute() {
  const token = localStorage.getItem('buildshield_token');
  
  if (!token) {
    // No token found? Send them directly to the login page
    return <Navigate to="/login" replace />;
  }
  
  // Token exists? Let them through to the layout and pages
  return <Outlet />;
}

export default function App() {
  return (
    <Routes>
      {/* Public Routes (No token required) */}
      <Route path="/login" element={<Login />} />

      {/* Protected Routes (Require a valid token) */}
      <Route element={<ProtectedRoute />}>
        <Route element={<Layout />}>
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard"    element={<Dashboard />} />
          <Route path="/repositories" element={<Repositories />} />
          <Route path="/scans"        element={<Scans />} />
          <Route path="/findings"     element={<Findings />} />
          <Route path="/policies"     element={<Policies />} />
          <Route path="/audit-logs"   element={<Placeholder name="Audit Logs" />} />
        </Route>
      </Route>
    </Routes>
  );
}