import { useState } from "react";
import {
  usePayoutSimulationMutation,
  useThresholdSensitivityMutation,
} from "../../hooks/useSimulation";
import type { SensitivityMode } from "../../types/api";
import {
  formatCurrency,
  formatNumber,
  formatPercent,
} from "../../utils/formatters";
import { ErrorState } from "../common/ErrorState";
import { LoadingState } from "../common/LoadingState";

interface FormState {
  simulation_id: string;
  simulation_name: string;
  coverage_multiplier: number;
  replace_existing: boolean;
  include_risk_band: boolean;
}

const INITIAL: FormState = {
  simulation_id: "API_FRONTEND_BASELINE",
  simulation_name: "Frontend baseline payout simulation",
  coverage_multiplier: 1.0,
  replace_existing: true,
  include_risk_band: true,
};

export function PayoutSimulatorPanel(): JSX.Element {
  const [form, setForm] = useState<FormState>(INITIAL);
  const [sensitivityMode, setSensitivityMode] = useState<SensitivityMode>("combined");

  const payoutMutation = usePayoutSimulationMutation();
  const sensitivityMutation = useThresholdSensitivityMutation();

  return (
    <div className="space-y-4 rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div>
        <h3 className="text-sm font-semibold text-slate-700">Payout simulator</h3>
        <p className="text-xs text-slate-500">
          Submits to <code>POST /api/v1/simulate/payout</code>. This mutates
          <code> simulation_runs</code> and <code>payout_results</code> on the
          backend.
        </p>
      </div>

      <form
        className="grid grid-cols-1 gap-3 md:grid-cols-2"
        onSubmit={(e) => {
          e.preventDefault();
          payoutMutation.mutate({
            simulation_id: form.simulation_id,
            simulation_name: form.simulation_name,
            coverage_multiplier: Number(form.coverage_multiplier),
            replace_existing: form.replace_existing,
            include_risk_band: form.include_risk_band,
          });
        }}
      >
        <label className="text-sm">
          <span className="block text-xs font-semibold uppercase text-slate-500">
            Simulation ID
          </span>
          <input
            className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1 font-mono text-sm"
            value={form.simulation_id}
            onChange={(e) => setForm({ ...form, simulation_id: e.target.value })}
            required
          />
        </label>
        <label className="text-sm">
          <span className="block text-xs font-semibold uppercase text-slate-500">
            Simulation name
          </span>
          <input
            className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1 text-sm"
            value={form.simulation_name}
            onChange={(e) =>
              setForm({ ...form, simulation_name: e.target.value })
            }
            required
          />
        </label>
        <label className="text-sm">
          <span className="block text-xs font-semibold uppercase text-slate-500">
            Coverage multiplier
          </span>
          <input
            type="number"
            step="0.05"
            min="0.1"
            className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1 text-sm"
            value={form.coverage_multiplier}
            onChange={(e) =>
              setForm({
                ...form,
                coverage_multiplier: Number(e.target.value),
              })
            }
          />
        </label>
        <div className="flex items-centre gap-4 text-sm">
          <label className="flex items-centre gap-2">
            <input
              type="checkbox"
              checked={form.replace_existing}
              onChange={(e) =>
                setForm({ ...form, replace_existing: e.target.checked })
              }
            />
            Replace existing
          </label>
          <label className="flex items-centre gap-2">
            <input
              type="checkbox"
              checked={form.include_risk_band}
              onChange={(e) =>
                setForm({ ...form, include_risk_band: e.target.checked })
              }
            />
            Include risk band
          </label>
        </div>
        <div className="md:col-span-2">
          <button
            type="submit"
            disabled={payoutMutation.isPending}
            className="rounded-md bg-brand px-3 py-2 text-sm font-semibold text-white shadow-sm hover:bg-brand/90 disabled:opacity-50"
          >
            {payoutMutation.isPending ? "Submitting…" : "Run payout simulation"}
          </button>
        </div>
      </form>

      {payoutMutation.isError ? (
        <ErrorState error={payoutMutation.error} title="Simulation failed" />
      ) : null}

      {payoutMutation.data ? (
        <div
          data-testid="payout-result"
          className="rounded-md border border-slate-200 bg-slate-50 p-3 text-sm"
        >
          <p className="font-semibold text-slate-700">
            Run {payoutMutation.data.simulation_id} succeeded
          </p>
          <ul className="mt-1 grid grid-cols-2 gap-1 text-xs text-slate-700">
            <li>
              Records generated:{" "}
              {formatNumber(payoutMutation.data.payout_records_generated)}
            </li>
            <li>
              Triggered assets: {formatNumber(payoutMutation.data.triggered_assets)}
            </li>
            <li>
              Total estimated payout:{" "}
              {formatCurrency(payoutMutation.data.total_estimated_payout)}
            </li>
            <li>
              Average payout rate:{" "}
              {formatPercent(payoutMutation.data.average_payout_rate ?? null, 2)}
            </li>
          </ul>
        </div>
      ) : null}

      <div className="space-y-2 border-t border-slate-200 pt-3">
        <h4 className="text-sm font-semibold text-slate-700">
          Threshold sensitivity
        </h4>
        <p className="text-xs text-slate-500">
          Submits to <code>POST /api/v1/simulate/threshold-sensitivity</code>.
        </p>
        <div className="flex items-centre gap-3 text-sm">
          <label>
            Mode
            <select
              className="ml-2 rounded-md border border-slate-300 px-2 py-1 text-sm"
              value={sensitivityMode}
              onChange={(e) =>
                setSensitivityMode(e.target.value as SensitivityMode)
              }
            >
              <option value="thresholds">thresholds</option>
              <option value="coverage_multipliers">coverage_multipliers</option>
              <option value="combined">combined</option>
            </select>
          </label>
          <button
            type="button"
            disabled={sensitivityMutation.isPending}
            onClick={() =>
              sensitivityMutation.mutate({
                mode: sensitivityMode,
                replace_existing: true,
                include_risk_band: true,
              })
            }
            className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-100 disabled:opacity-50"
          >
            {sensitivityMutation.isPending ? "Running…" : "Run sensitivity"}
          </button>
        </div>

        {sensitivityMutation.isPending ? <LoadingState /> : null}
        {sensitivityMutation.isError ? (
          <ErrorState error={sensitivityMutation.error} title="Sensitivity failed" />
        ) : null}

        {sensitivityMutation.data ? (
          <div className="overflow-x-auto rounded-md border border-slate-200">
            <table className="min-w-full text-xs">
              <thead className="bg-slate-50 text-left uppercase text-slate-500">
                <tr>
                  <th className="px-2 py-1">Simulation</th>
                  <th className="px-2 py-1 text-right">Triggered</th>
                  <th className="px-2 py-1 text-right">Trigger rate</th>
                  <th className="px-2 py-1 text-right">Estimated payout</th>
                  <th className="px-2 py-1 text-right">Avg rate</th>
                </tr>
              </thead>
              <tbody>
                {sensitivityMutation.data.scenarios.map((scenario) => (
                  <tr
                    key={scenario.simulation_id}
                    className="border-t border-slate-100"
                  >
                    <td className="px-2 py-1 font-mono">
                      {scenario.simulation_id}
                    </td>
                    <td className="px-2 py-1 text-right">
                      {formatNumber(scenario.triggered_assets)}
                    </td>
                    <td className="px-2 py-1 text-right">
                      {formatPercent(scenario.trigger_rate, 1)}
                    </td>
                    <td className="px-2 py-1 text-right">
                      {formatCurrency(scenario.total_estimated_payout)}
                    </td>
                    <td className="px-2 py-1 text-right">
                      {formatPercent(scenario.average_payout_rate, 2)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </div>
    </div>
  );
}
