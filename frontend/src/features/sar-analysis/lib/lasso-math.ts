// Ray-casting point-in-polygon.

export interface Point {
  x: number;
  y: number;
}

export interface IdPoint {
  moleculeId: string;
  x: number;
  y: number;
}

export function pointInPolygon(p: Point, poly: Point[]): boolean {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const xi = poly[i].x, yi = poly[i].y;
    const xj = poly[j].x, yj = poly[j].y;
    const intersect =
      ((yi > p.y) !== (yj > p.y)) &&
      p.x < ((xj - xi) * (p.y - yi)) / (yj - yi || Number.EPSILON) + xi;
    if (intersect) inside = !inside;
  }
  return inside;
}

export function idsInsidePolygon(points: IdPoint[], poly: Point[]): string[] {
  if (poly.length < 3) return [];
  return points.filter((pt) => pointInPolygon(pt, poly)).map((pt) => pt.moleculeId);
}
