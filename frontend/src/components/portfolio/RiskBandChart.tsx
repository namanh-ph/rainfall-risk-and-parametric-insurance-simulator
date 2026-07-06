import {
  Bar,
  BarChart,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { RiskBandDistributionItem } from "../../types/api";
import { RISK_BAND_ORDER, getRiskHex } from "../../utils/riskColours";

interface Props {
  data: RiskBandDistributionItem[];
}

export function RiskBandChart({ data }: Props): JSX.Element {
  const indexed = new Map(data.map((item) => [item.risk_band, item]));
  const ordered = RISK_BAND_ORDER.map((band) => ({
    risk_band: band,
    asset_count: indexed.get(band)?.asset_count ?? 0,
  }));

  return (
    <div
      className="h-64 rounded-lg border border-slate-200 bg-white p-4 shadow-sm"
      data-testid="risk-band-chart"
    >
      <h3 className="text-sm font-semibold text-slate-700">Risk band distribution</h3>
      <ResponsiveContainer width="100%" height="85%">
        <BarChart data={ordered} margin={{ top: 8, right: 8, left: 0, bottom: 8 }}>
          <XAxis dataKey="risk_band" tick={{ fontSize: 12 }} />
          <YAxis tick={{ fontSize: 12 }} allowDecimals={false} />
          <Tooltip />
          <Bar dataKey="asset_count">
            {ordered.map((entry) => (
              <Cell key={entry.risk_band} fill={getRiskHex(entry.risk_band)} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
