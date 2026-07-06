import { MapContainer, TileLayer } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import type {
  AssetMapFeatureCollection,
  LgaMapFeatureCollection,
  StationMapFeatureCollection,
} from "../../types/geojson";
import { VICTORIA_CENTER, VICTORIA_INITIAL_ZOOM } from "../../utils/constants";
import { EmptyState } from "../common/EmptyState";
import { AssetMarker } from "./AssetMarker";
import { LgaLayer } from "./LgaLayer";
import { RiskLegend } from "./RiskLegend";
import { StationLayer } from "./StationLayer";

interface Props {
  assets: AssetMapFeatureCollection | undefined;
  lgas?: LgaMapFeatureCollection;
  stations?: StationMapFeatureCollection;
  showLgas: boolean;
  showStations: boolean;
  onSelectAsset: (assetId: string) => void;
}

export function RiskMap({
  assets,
  lgas,
  stations,
  showLgas,
  showStations,
  onSelectAsset,
}: Props): JSX.Element {
  const features = assets?.features ?? [];
  return (
    <div className="relative h-[560px] w-full overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
      <MapContainer
        center={VICTORIA_CENTER}
        zoom={VICTORIA_INITIAL_ZOOM}
        scrollWheelZoom
        className="h-full w-full"
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        {showLgas ? <LgaLayer data={lgas} /> : null}
        {showStations ? <StationLayer data={stations} /> : null}
        {features.map((feature) => (
          <AssetMarker
            key={feature.properties.asset_id}
            feature={feature}
            onSelect={onSelectAsset}
          />
        ))}
      </MapContainer>

      <div className="pointer-events-none absolute right-3 top-3">
        <div className="pointer-events-auto">
          <RiskLegend />
        </div>
      </div>

      {features.length === 0 ? (
        <div className="absolute inset-x-4 bottom-4 z-[400]">
          <EmptyState
            title="No asset features"
            message="The map asset endpoint returned an empty FeatureCollection."
          />
        </div>
      ) : null}
    </div>
  );
}
