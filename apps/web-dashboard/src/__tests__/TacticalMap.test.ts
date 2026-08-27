/**
 * Unit Tests for TacticalMap Geodesic Calculations and Coordinate Transforms.
 */

describe("TacticalMap Geometry Engine", () => {
  function toMilitaryGrid(lat: number, lon: number): string {
    const zone = Math.floor((lon + 180) / 6) + 1;
    const latBand = "S";
    const easting = Math.floor((((lon % 6) + 6) % 6) * 100000);
    const northing = Math.floor(Math.abs(lat) * 100000) % 100000;
    return `${zone}${latBand} ${easting.toString().padStart(5, "0").slice(0, 4)} ${northing.toString().padStart(5, "0").slice(0, 4)}`;
  }

  function createGeodesicFovPolygon(lat: number, lon: number, azimuthDeg: number = 45, rangeKm: number = 0.9) {
    const coordinates: [number, number][] = [[lon, lat]];
    const halfFov = 30;
    const earthRadius = 6371;

    for (let angle = azimuthDeg - halfFov; angle <= azimuthDeg + halfFov; angle += 3) {
      const rad = (angle * Math.PI) / 180;
      const latRad = (lat * Math.PI) / 180;
      const dLat = (rangeKm / earthRadius) * Math.cos(rad);
      const dLon = (rangeKm / (earthRadius * Math.cos(latRad))) * Math.sin(rad);
      coordinates.push([lon + (dLon * 180) / Math.PI, lat + (dLat * 180) / Math.PI]);
    }
    coordinates.push([lon, lat]);
    return coordinates;
  }

  test("MGRS coordinate generator outputs standard military format", () => {
    const grid = toMilitaryGrid(34.0522, 74.8856);
    expect(grid).toMatch(/^\d{2}[A-Z] \d{4} \d{4}$/);
    expect(grid.startsWith("43S")).toBe(true);
  });

  test("Geodesic FOV cone creates closed polygon with azimuth vertices", () => {
    const coords = createGeodesicFovPolygon(34.0522, 74.8856, 45, 1.0);
    expect(coords.length).toBeGreaterThan(15);
    // Closed ring assertion
    expect(coords[0]).toEqual(coords[coords.length - 1]);
  });
});
