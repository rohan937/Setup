import { Routes, Route } from "react-router-dom";
import AppShell from "@/components/AppShell";
import Dashboard from "@/pages/Dashboard";
import Strategies from "@/pages/Strategies";
import Timeline from "@/pages/Timeline";
import DataHealth from "@/pages/DataHealth";
import Backtests from "@/pages/Backtests";
import LiveDrift from "@/pages/LiveDrift";
import Alerts from "@/pages/Alerts";
import Settings from "@/pages/Settings";
import NotFound from "@/pages/NotFound";

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Dashboard />} />
        <Route path="strategies" element={<Strategies />} />
        <Route path="timeline" element={<Timeline />} />
        <Route path="data-health" element={<DataHealth />} />
        <Route path="backtests" element={<Backtests />} />
        <Route path="live-drift" element={<LiveDrift />} />
        <Route path="alerts" element={<Alerts />} />
        <Route path="settings" element={<Settings />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
