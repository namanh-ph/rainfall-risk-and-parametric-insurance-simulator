import {
  Bar,
  BarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { IndustryRiskSummaryItem } from "../../types/api";

interface Props {
  data: IndustryRiskSummaryItem[];
}

export function IndustryRiskChart({ data }: Props): JSX.Element {
  const sanitised = data
    .map((row) => ({
      industry: row.industry,
      average_risk_score: row.average_risk_score ?? 0,
      high_or_severe_assets: row.high_or_severe_assets,
    }))
    .sort((a, b) => b.average_risk_score - a.average_risk_score);

  return (
    <div
      className="h-72 rounded-lg border border-slate-200 bg-white p-4 shadow-sm"
      data-testid="industry-risk-chart"
    >
      <h3 className="text-sm font-semibold text-slate-700">
        Average risk score by industry
      </h3>
      <ResponsiveContainer width="100%" height="85%">
        <BarChart
          data={sanitised}
          layout="vertical"
          margin={{ top: 8, right: 16, left: 24, bottom: 8 }}
        >
          <XAxis type="number" tick={{ fontSize: 12 }} />
          <YAxis dataKey="industry" type="category" width={120} tick={{ fontSize: 12 }} />
          <Tooltip />
          <Bar dataKey="average_risk_score" fill="#1c3f6e" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
