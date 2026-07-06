import { useState } from "react";
import { DashboardPage } from "../../pages/DashboardPage";
import { PortfolioAnalyticsPage } from "../../pages/PortfolioAnalyticsPage";
import { Header } from "./Header";
import { Sidebar, type DashboardView } from "./Sidebar";

export function AppShell(): JSX.Element {
  const [view, setView] = useState<DashboardView>("map");
  return (
    <div className="flex min-h-screen flex-col bg-slate-50 text-slate-900">
      <Header />
      <div className="flex flex-1 flex-col md:flex-row">
        <Sidebar active={view} onChange={setView} />
        <main className="flex-1 p-4 md:p-6">
          {view === "map" ? <DashboardPage /> : <PortfolioAnalyticsPage />}
        </main>
      </div>
    </div>
  );
}
