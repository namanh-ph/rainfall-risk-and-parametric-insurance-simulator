import type { PortfolioSummaryResponse } from "../../types/api";
import {
  formatCurrency,
  formatNumber,
  formatPercent,
  formatRiskScore,
} from "../../utils/formatters";
import { MetricCard } from "../common/MetricCard";

interface Props {
  summary: PortfolioSummaryResponse;
}

export function PortfolioSummaryCards({ summary }: Props): JSX.Element {
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-4">
      <MetricCard title="Total assets" value={formatNumber(summary.total_assets)} />
      <MetricCard
        title="Total coverage limit"
        value={formatCurrency(summary.total_coverage_limit)}
      />
      <MetricCard
        title="Total estimated payout"
        value={formatCurrency(summary.total_estimated_payout)}
        accent="amber"
      />
      <MetricCard
        title="Average risk score"
        value={formatRiskScore(summary.average_risk_score)}
      />
      <MetricCard
        title="High or Severe assets"
        value={formatNumber(summary.high_or_severe_assets)}
        accent="red"
      />
      <MetricCard
        title="Triggered assets"
        value={formatNumber(summary.triggered_assets)}
        accent="amber"
      />
      <MetricCard
        title="Average ML probability"
        value={formatPercent(summary.average_ml_risk_probability ?? null, 2)}
      />
      <MetricCard
        title="Simulation"
        value={summary.simulation_id}
        hint={`As of ${summary.as_of_date}`}
        accent="slate"
      />
    </div>
  );
}
