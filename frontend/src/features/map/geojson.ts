import type { Zone } from "@/shared/api/types";

type Geometry = GeoJSON.Geometry;

interface FeatureLike {
  id: string;
  geometry: { type: string; coordinates: unknown };
  properties: object;
}

/** Colección GeoJSON para MapLibre; copia el id del feature a `featureId` (propiedades). */
export function toMapCollection(features: readonly FeatureLike[]): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: features.map((f) => ({
      type: "Feature",
      geometry: f.geometry as unknown as Geometry,
      properties: { ...f.properties, featureId: f.id },
    })),
  };
}

export function zonesToCollection(zones: readonly Zone[]): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: zones.map((z) => ({
      type: "Feature",
      geometry: z.geometry as unknown as Geometry,
      properties: { featureId: z.id, name: z.name, cover_type: z.cover_type },
    })),
  };
}

export const EMPTY_COLLECTION: GeoJSON.FeatureCollection = {
  type: "FeatureCollection",
  features: [],
};
