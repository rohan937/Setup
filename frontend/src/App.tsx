import { Routes, Route } from "react-router-dom";
import AppShell from "@/components/AppShell";
import Home from "@/pages/Home";
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
import DeploymentReadiness from "@/pages/DeploymentReadiness";
import NotFound from "@/pages/NotFound";
import CommandCenter from "@/pages/CommandCenter";
import Experiments from "@/pages/Experiments";
import ReviewCases from "@/pages/ReviewCases";
import PromotionGates from "@/pages/PromotionGates";
import RegressionTests from "@/pages/RegressionTests";
import Policies from "@/pages/Policies";
import SLAMonitor from "@/pages/SLAMonitor";
import AuditTrail from "@/pages/AuditTrail";
import DeveloperSDK from "@/pages/DeveloperSDK";
import EvidenceBundles from "@/pages/EvidenceBundles";
import WorkspaceSettings from "@/pages/WorkspaceSettings";
import Members from "@/pages/Members";
import DemoControls from "@/pages/DemoControls";
import Login from "@/pages/Login";
import Register from "@/pages/Register";
import VerifyEmail from "@/pages/VerifyEmail";
import ForgotPassword from "@/pages/ForgotPassword";
import ResetPassword from "@/pages/ResetPassword";
import { AuthProvider } from "@/context/AuthContext";
import RequirePermission from "@/components/RequirePermission";

export default function App() {
  return (
    <AuthProvider>
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Home />} />
        <Route path="dashboard" element={<Dashboard />} />
        <Route path="command-center" element={<CommandCenter />} />
        <Route path="portfolio" element={<Portfolio />} />
        <Route path="strategies" element={<Strategies />} />
        <Route path="strategies/compare" element={<StrategyComparison />} />
        <Route path="strategies/run-compare" element={<MultiRunComparison />} />
        <Route path="strategies/:id" element={<StrategyDetail />} />
        <Route path="experiments" element={<Experiments />} />
        <Route path="backtests" element={<Backtests />} />
        <Route path="evidence/coverage" element={<EvidenceCoverage />} />
        <Route path="timeline" element={<Timeline />} />
        <Route path="data-health" element={<DataHealth />} />
        <Route path="reports" element={<Reports />} />
        <Route path="reports/:id" element={<Reports />} />
        <Route path="live-drift" element={<LiveDrift />} />
        <Route path="alerts" element={<Alerts />} />
        <Route path="review-cases" element={<ReviewCases />} />
        <Route path="promotion-gates" element={<PromotionGates />} />
        <Route path="regression-tests" element={<RegressionTests />} />
        <Route path="policies" element={<Policies />} />
        <Route path="sla-monitor" element={<SLAMonitor />} />
        <Route path="audit-trail" element={<AuditTrail />} />
        <Route path="developer/sdk" element={<DeveloperSDK />} />
        <Route path="developer/evidence-bundles" element={<EvidenceBundles />} />
        <Route path="settings" element={<Settings />} />
        <Route path="workspace/settings" element={<WorkspaceSettings />} />
        <Route path="workspace/members" element={<Members />} />
        <Route
          path="admin/system-health"
          element={
            <RequirePermission perm="manage_workspace" title="System Health">
              <AdminSystemHealth />
            </RequirePermission>
          }
        />
        <Route
          path="admin/demo-controls"
          element={
            <RequirePermission perm="seed_demo" title="Demo Controls">
              <DemoControls />
            </RequirePermission>
          }
        />
        <Route
          path="admin/deployment-readiness"
          element={
            <RequirePermission perm="manage_workspace" title="Deployment Readiness">
              <DeploymentReadiness />
            </RequirePermission>
          }
        />
        <Route path="*" element={<NotFound />} />
      </Route>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route path="/verify-email" element={<VerifyEmail />} />
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="/reset-password" element={<ResetPassword />} />
    </Routes>
    </AuthProvider>
  );
}
