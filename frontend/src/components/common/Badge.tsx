import clsx from "clsx";
import type { RiskBand } from "../../types/api";
import { getRiskColour } from "../../utils/riskColours";

interface Props {
  band: RiskBand | string | null | undefined;
  className?: string;
}

export function RiskBandBadge({ band, className }: Props): JSX.Element {
  const colour = getRiskColour(band);
  const label = band ?? "Unknown";
  return (
    <span
      className={clsx(
        "inline-flex items-centre rounded-full px-2 py-0.5 text-xs font-semibold",
        colour.bg,
        colour.text,
        className,
      )}
    >
      {label}
    </span>
  );
}
