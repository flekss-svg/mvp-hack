import type { Frame, LiveVehicle, SlowSegment } from '../api/types'

/** Provider-independent map contract. Neither the map nor adapters invent a vehicle. */
export interface MapVehicle {
  vehicleId: string | number
  tripId?: string | number
  route?: string
  mode?: string
  lat: number
  lon: number
  risk?: number | null
  level?: number | null
  delay?: number | null
  updatedAt?: string | number
}

const coordinate = (value: unknown) => typeof value === 'number' && Number.isFinite(value)

export function replayVehicles(frame: Frame | null): MapVehicle[] {
  if (!frame) return []
  const { vehicles } = frame
  return vehicles.id.flatMap((vehicleId, index) => coordinate(vehicles.lat[index]) && coordinate(vehicles.lon[index]) ? [{
    vehicleId, tripId: vehicleId, route: vehicles.route?.[index], mode: vehicles.mode?.[index],
    lat: vehicles.lat[index], lon: vehicles.lon[index], risk: vehicles.risk[index],
    level: vehicles.level[index], delay: vehicles.late[index],
  }] : [])
}

/** Future live integration only needs to map its response to this same contract. */
export function liveVehicles(vehicles: LiveVehicle[] | undefined): MapVehicle[] {
  return (vehicles ?? []).flatMap((vehicle) => coordinate(vehicle.lat) && coordinate(vehicle.lon) ? [{ ...vehicle }] : [])
}

export function replaySlowSegments(frame: Frame | null): SlowSegment[] { return frame?.slowSegments ?? [] }
