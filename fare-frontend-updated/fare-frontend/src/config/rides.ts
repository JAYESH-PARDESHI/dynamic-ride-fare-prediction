import type { RideKind } from '../types'

/**
 * Ride options accepted by the fare service (cab_type + name).
 * Only these pairs are ever sent. Seat counts / descriptions are display metadata.
 */
export interface RideOption { name: string; desc: string; seats: number; kind: RideKind }

export const RIDES: Record<string, RideOption[]> = {
  Uber: [
    { name: 'UberX', desc: 'Everyday rides', seats: 4, kind: 'sedan' },
    { name: 'UberXL', desc: 'Extra room for groups', seats: 6, kind: 'suv' },
    { name: 'UberPool', desc: 'Shared, lower cost', seats: 2, kind: 'shared' },
    { name: 'Black', desc: 'Premium sedan', seats: 4, kind: 'premium' },
    { name: 'Black SUV', desc: 'Premium SUV', seats: 6, kind: 'premium-suv' },
    { name: 'WAV', desc: 'Wheelchair accessible', seats: 4, kind: 'wav' },
  ],
  Lyft: [
    { name: 'Lyft', desc: 'Everyday rides', seats: 4, kind: 'sedan' },
    { name: 'Lyft XL', desc: 'Extra room for groups', seats: 6, kind: 'suv' },
    { name: 'Shared', desc: 'Shared, lower cost', seats: 2, kind: 'shared' },
    { name: 'Lux', desc: 'Premium comfort', seats: 4, kind: 'premium' },
    { name: 'Lux Black', desc: 'Premium black car', seats: 4, kind: 'premium' },
    { name: 'Lux Black XL', desc: 'Premium SUV', seats: 6, kind: 'premium-suv' },
  ],
}

export const DEFAULT_RIDE: Record<string, string> = { Uber: 'UberX', Lyft: 'Lyft' }
export const rideKey = (cab: string, name: string) => `${cab}|${name}`
