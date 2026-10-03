export const formatMoney = (n: number, currency = 'USD') => {
  try { return new Intl.NumberFormat('en-US', { style: 'currency', currency }).format(n) }
  catch { return `$${n.toFixed(2)}` }
}
export const formatDistance = (mi: number) => (mi < 0.1 ? '<0.1 mi' : `${mi.toFixed(1)} mi`)
export const formatMinutes = (min: number) => `${Math.max(1, Math.round(min))} min`

export interface Demand { label: string; high: boolean }
export function demandLabel(surge: number | null): Demand {
  if (surge == null || surge <= 1.05) return { label: 'Normal demand', high: false }
  return { label: `Higher demand · ${Number(surge.toFixed(2))}×`, high: true }
}
