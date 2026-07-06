import { Polygon, Tooltip } from "react-leaflet";
import type {
  LgaMapFeatureCollection,
  MultiPolygonGeometry,
  PolygonGeometry,
} from "../../types/geojson";
import { positionsToLatLngs } from "../../utils/geo";

interface Props {
  data: LgaMapFeatureCollection | undefined;
}

export function LgaLayer({ data }: Props): JSX.Element | null {
  if (!data || data.features.length === 0) return null;

  return (
    <>
      {data.features.map((feature, idx) => {
        const props = feature.properties;
        const polygons = featureToRings(feature.geometry);
        return polygons.map((rings, polyIdx) => (
          <Polygon
            key={`${props.lga_code}-${idx}-${polyIdx}`}
            positions={rings.map((ring) => positionsToLatLngs(ring))}
            pathOptions={{
              color: "#1c3f6e",
              weight: 1,
              fillColor: "#1c3f6e",
              fillOpacity: 0.07,
            }}
          >
            <Tooltip sticky>
              <div className="text-xs">
                <p className="font-semibold">{props.lga_name ?? props.lga_code}</p>
                {typeof props.asset_count === "number" ? (
                  <p>Assets: {props.asset_count}</p>
                ) : null}
                {typeof props.high_or_severe_assets === "number" ? (
                  <p>High/Severe: {props.high_or_severe_assets}</p>
                ) : null}
              </div>
            </Tooltip>
          </Polygon>
        ));
      })}
    </>
  );
}

function featureToRings(
  geom: PolygonGeometry | MultiPolygonGeometry,
): Array<Array<Array<[number, number]>>> {
  if (geom.type === "Polygon") {
    return [geom.coordinates];
  }
  return geom.coordinates;
}
