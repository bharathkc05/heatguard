import * as Location from "expo-location";

export interface Coordinates {
  lat: number;
  lon: number;
}

export const FALLBACK_COORDINATES: Coordinates = {
  lat: 13.08,
  lon: 80.27,
};

export async function getCurrentCoordinates(): Promise<Coordinates> {
  try {
    const permission = await Location.requestForegroundPermissionsAsync();
    if (permission.status !== "granted") {
      return FALLBACK_COORDINATES;
    }

    const current = await Location.getCurrentPositionAsync({
      accuracy: Location.Accuracy.Balanced,
    });

    return {
      lat: current.coords.latitude,
      lon: current.coords.longitude,
    };
  } catch {
    return FALLBACK_COORDINATES;
  }
}
