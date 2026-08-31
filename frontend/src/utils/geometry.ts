export type Coordinate = [number, number]

function distance(first: Coordinate, second: Coordinate) {
  const averageLatitude = ((first[1] + second[1]) / 2) * (Math.PI / 180)
  const x = (second[0] - first[0]) * Math.cos(averageLatitude)
  const y = second[1] - first[1]
  return Math.hypot(x, y)
}

function pointAtFraction(coordinates: Coordinate[], fraction: number) {
  if (coordinates.length < 2) return { coordinate: coordinates[0], segmentIndex: 0 }
  const boundedFraction = Math.min(1, Math.max(0, fraction))
  const lengths = coordinates.slice(1).map((item, index) => distance(coordinates[index], item))
  const total = lengths.reduce((sum, item) => sum + item, 0)
  const target = total * boundedFraction
  let travelled = 0

  for (let index = 0; index < lengths.length; index += 1) {
    const length = lengths[index]
    if (travelled + length >= target || index === lengths.length - 1) {
      const ratio = length === 0 ? 0 : (target - travelled) / length
      const start = coordinates[index]
      const end = coordinates[index + 1]
      return {
        coordinate: [
          start[0] + (end[0] - start[0]) * ratio,
          start[1] + (end[1] - start[1]) * ratio,
        ] as Coordinate,
        segmentIndex: index,
      }
    }
    travelled += length
  }
  return { coordinate: coordinates.at(-1)!, segmentIndex: coordinates.length - 2 }
}

export function sliceLineBetweenFractions(
  coordinates: Coordinate[],
  startFraction: number,
  endFraction: number,
) {
  if (coordinates.length < 2) return coordinates
  const start = Math.min(startFraction, endFraction)
  const end = Math.max(startFraction, endFraction)
  const startPoint = pointAtFraction(coordinates, start)
  const endPoint = pointAtFraction(coordinates, end)
  const middle = coordinates.slice(startPoint.segmentIndex + 1, endPoint.segmentIndex + 1)
  return [startPoint.coordinate, ...middle, endPoint.coordinate]
}

export function splitLineAtFraction(coordinates: Coordinate[], fraction: number) {
  return {
    completed: sliceLineBetweenFractions(coordinates, 0, fraction),
    remaining: sliceLineBetweenFractions(coordinates, fraction, 1),
  }
}
