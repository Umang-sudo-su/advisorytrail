import { Routes, Route, Navigate } from 'react-router-dom';
import Layout from './components/Layout';
import Placeholder from './pages/Placeholder';
import Repositories from './pages/Repositories';

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard"    element={<Placeholder name="Dashboard" />} />
        <Route path="/repositories" element={<Repositories />} />
        <Route path="/scans"        element={<Placeholder name="Scans" />} />
        <Route path="/findings"     element={<Placeholder name="Findings" />} />
        <Route path="/policies"     element={<Placeholder name="Policies" />} />
        <Route path="/audit-logs"   element={<Placeholder name="Audit Logs" />} />
      </Route>
    </Routes>
  );
}
