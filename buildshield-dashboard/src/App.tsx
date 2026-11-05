import { Routes, Route, Navigate } from 'react-router-dom';
import Layout from './components/Layout';
import Placeholder from './pages/Placeholder';
import Dashboard from './pages/Dashboard';
import Repositories from './pages/Repositories';
import Scans from './pages/Scans';
import Findings from './pages/Findings';
import Policies from './pages/Policies';

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard"    element={<Dashboard />} />
        <Route path="/repositories" element={<Repositories />} />
        <Route path="/scans"        element={<Scans />} />
        <Route path="/findings"     element={<Findings />} />
        <Route path="/policies"     element={<Policies />} />
        <Route path="/audit-logs"   element={<Placeholder name="Audit Logs" />} />
      </Route>
    </Routes>
  );
}