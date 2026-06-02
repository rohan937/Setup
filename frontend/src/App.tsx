import { Routes, Route } from "react-router-dom";
import AppShell from "@/components/AppShell";
import Dashboard from "@/pages/Dashboard";
import Strategies from "@/pages/Strategies";
import StrategyComparison from "@/pages/StrategyComparison";
import MultiRunComparison from "@/pages/MultiRunComparison";
import StrategyDetail from "@/pages/StrategyDetail";
import EvidenceCoverage from "@/pages/EvidenceCoverage";
import Portfolio from "@/pages/Portfolio";
import Timeline from "@/pages/Timeline";
import DataHealth from "@/pages/DataHealth";
import Backtests from "@/pages/Backtests";
import Reports from "@/pages/Reports";
import LiveDrift from "@/pages/LiveDrift";
import Alerts from "@/pages/Alerts";
import Settings from "@/pages/Settings";
import AdminSystemHealth from "@/pages/AdminSystemHealth";
import NotFound from "@/pages/NotFound";

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Dashboard />} />
        <Route path="strategies" element={<Strategies />} />
        <Route path="strategies/compare" element={<StrategyComparison />} />
        <Route path="strategies/run-compare" element={<MultiRunComparison />} />
        <Route path="strategies/:id" element={<StrategyDetail />} />
        <Route path="timeline" element={<Timeline />} />
        <Route path="evidence/coverage" element={<EvidenceCoverage />} />
        <Route path="portfolio" element={<Portfolio />} />
        <Route path="data-health" element={<DataHealth />} />
        <Route path="backtests" element={<Backtests />} />
        <Route path="reports" element={<Reports />} />
        <Route path="reports/:id" element={<Reports />} />
        <Route path="live-drift" element={<LiveDrift />} />
        <Route path="alerts" element={<Alerts />} />
        <Route path="settings" element={<Settings />} />
        <Route path="admin/system-health" element={<AdminSystemHealth />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
