import { CircleMarker, Tooltip } from "react-leaflet";
import type { StationMapFeatureCollection } from "../../types/geojson";
import { positionToLatLng } from "../../utils/geo";

interface Props {
  data: StationMapFeatureCollection | undefined;
}

export function StationLayer({ data }: Props): JSX.Element | null {
  if (!data || data.features.length === 0) return null;
  return (
    <>
      {data.features.map((feature) => (
        <CircleMarker
          key={feature.properties.station_id}
          center={positionToLatLng(feature.geometry.coordinates)}
          radius={4}
          pathOptions={{
            color: "#0ea5e9",
            fillColor: "#0ea5e9",
            fillOpacity: 0.6,
            weight: 1,
          }}
        >
          <Tooltip>
            <div className="text-xs">
              <p className="font-semibold">
                {feature.properties.station_name ?? feature.properties.station_id}
              </p>
              {typeof feature.properties.asset_match_count === "number" ? (
                <p>Matched assets: {feature.properties.asset_match_count}</p>
              ) : null}
            </div>
          </Tooltip>
        </CircleMarker>
      ))}
    </>
  );
}
