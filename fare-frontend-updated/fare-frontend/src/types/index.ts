export type LatLng = [number, number]
export type Field = 'pickup' | 'destination'

/** Item returned by the location search / reverse lookup endpoints. */
export interface GeoResult {
  display_name: string
  name: string
  latitude: number
  longitude: number
  neighborhood?: string | null
  /** Internal category. Used only for a pre-check, never displayed. */
  model_area?: string | null
  supported: boolean
  message?: string | null
}

/** A location the rider has chosen. */
export interface Place {
  name: string
  subtitle: string
  /** Compact label sent with fare requests. */
  label: string
  lat: number
  lng: number
  /** Internal grouping used for a same-area pre-check; never shown. */
  area: string | null
}

export interface PredictPoint { latitude: number; longitude: number; display_name: string }
export interface PredictRequest { pickup: PredictPoint; destination: PredictPoint; cab_type: string; name: string }

export interface WeatherInfo { tempF: number; summary: string; raining: boolean }

export interface FareQuote {
  fare: number
  currency: string
  distanceMi: number | null
  durationMin: number | null
  surge: number | null
  weather: WeatherInfo | null
}

export interface FareResponse { quote: FareQuote; route: LatLng[] | null }

export type RideKind = 'shared' | 'sedan' | 'suv' | 'wav' | 'premium' | 'premium-suv'
