import { useEffect, useState } from "react";
import { Outlet } from "react-router-dom";
import Sidebar from "./Sidebar";
import Topbar from "./Topbar";
import DemoWalkthrough from "./DemoWalkthrough";
import VerifyEmailBanner from "./VerifyEmailBanner";
import { getStrategies } from "@/lib/api";
import { onWalkthroughStart } from "@/lib/demoWalkthrough";
import type { Strategy } from "@/types";

export default function AppShell() {
  // M76: the guided walkthrough panel is mounted once here so it persists as
  // the user navigates between Dashboard / Portfolio / strategy pages.
  const [walkthroughOpen, setWalkthroughOpen] = useState(false);
  const [strategies, setStrategies] = useState<Strategy[]>([]);

  useEffect(() => {
    return onWalkthroughStart(() => {
      getStrategies()
        .then(setStrategies)
        .catch(() => setStrategies([]))
        .finally(() => setWalkthroughOpen(true));
    });
  }, []);

  return (
    <div className="flex h-screen overflow-hidden bg-bg-900">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar />
        <VerifyEmailBanner />
        <main className="flex-1 overflow-y-auto">
          <div className="mx-auto w-full max-w-content px-6 py-7">
            <Outlet />
          </div>
        </main>
      </div>
      {walkthroughOpen && (
        <DemoWalkthrough
          strategies={strategies}
          onClose={() => setWalkthroughOpen(false)}
        />
      )}
    </div>
  );
}
