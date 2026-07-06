import { CloudRain } from "lucide-react";
import { API_BASE_URL } from "../../api/client";

export function Header(): JSX.Element {
  return (
    <header className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-3">
        <div className="flex items-center gap-3">
          <CloudRain className="h-6 w-6 text-brand" aria-hidden />
          <div>
            <h1 className="text-lg font-semibold text-brand">
              Rainfall Risk &amp; Parametric Insurance Simulator
            </h1>
          </div>
        </div>
        <p className="hidden text-xs text-slate-500 md:block">
          API: <code className="font-mono">{API_BASE_URL}</code>
        </p>
      </div>
    </header>
  );
}
