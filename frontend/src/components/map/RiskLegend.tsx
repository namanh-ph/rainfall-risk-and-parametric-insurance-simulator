import { RISK_BAND_ORDER, getRiskColour } from "../../utils/riskColours";

export function RiskLegend(): JSX.Element {
  const unknown = getRiskColour(null);
  return (
    <div className="rounded-md border border-slate-200 bg-white p-3 text-xs shadow-sm">
      <p className="mb-2 font-semibold text-slate-700">Risk band</p>
      <ul className="space-y-1">
        {RISK_BAND_ORDER.map((band) => {
          const colour = getRiskColour(band);
          return (
            <li key={band} className="flex items-centre gap-2">
              <span
                className="inline-block h-3 w-3 rounded-full"
                style={{ backgroundColor: colour.hex }}
                aria-hidden
              />
              <span>{band}</span>
            </li>
          );
        })}
        <li className="flex items-centre gap-2">
          <span
            className="inline-block h-3 w-3 rounded-full"
            style={{ backgroundColor: unknown.hex }}
            aria-hidden
          />
          <span>Unknown</span>
        </li>
      </ul>
    </div>
  );
}
