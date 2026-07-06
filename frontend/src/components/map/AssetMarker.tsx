import { CircleMarker, Popup } from "react-leaflet";
import type {
  AssetMapFeatureProperties,
  PointGeometry,
  Feature,
} from "../../types/geojson";
import { positionToLatLng } from "../../utils/geo";
import { getRiskHex } from "../../utils/riskColours";
import {
  formatCurrency,
  formatMm,
  formatPercent,
  formatRiskScore,
} from "../../utils/formatters";
import { RiskBandBadge } from "../common/Badge";

interface Props {
  feature: Feature<PointGeometry, AssetMapFeatureProperties>;
  onSelect: (assetId: string) => void;
}

export function AssetMarker({ feature, onSelect }: Props): JSX.Element {
  const props = feature.properties;
  const colour = getRiskHex(props.risk_band);
  return (
    <CircleMarker
      center={positionToLatLng(feature.geometry.coordinates)}
      radius={5}
      pathOptions={{
        color: colour,
        fillColor: colour,
        fillOpacity: 0.7,
        weight: 1,
      }}
      eventHandlers={{
        click: () => onSelect(props.asset_id),
      }}
    >
      <Popup>
        <div className="space-y-1 text-xs">
          <p className="font-semibold">{props.asset_id}</p>
          <p>{props.postcode}</p>
          <p className="text-slate-600">{props.industry}</p>
          <p className="flex items-centre gap-2">
            <RiskBandBadge band={props.risk_band ?? null} />
            <span>Risk {formatRiskScore(props.risk_score ?? null)}</span>
          </p>
          <p>
            ML probability {formatPercent(props.ml_risk_probability ?? null, 2)}
          </p>
          <p>
            Rainfall 3d {formatMm(props.rainfall_3d_mm ?? null)} Â· Payout{" "}
            {formatCurrency(props.estimated_payout ?? null)}
          </p>
          <button
            type="button"
            className="mt-1 text-xs font-semibold text-brand underline"
            onClick={() => onSelect(props.asset_id)}
          >
            Open details
          </button>
        </div>
      </Popup>
    </CircleMarker>
  );
}
