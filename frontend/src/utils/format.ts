export function formatClock(value: string | null | undefined) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return new Intl.DateTimeFormat('pt-BR', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).format(date)
}

export function formatMinutes(seconds: number | null | undefined) {
  if (seconds == null) return 'Indisponível'
  const minutes = Math.max(0, Math.round(seconds / 60))
  if (minutes < 60) return `${minutes} min`
  const hours = Math.floor(minutes / 60)
  const remainder = minutes % 60
  return `${hours}h ${remainder.toString().padStart(2, '0')}min`
}

export function formatDistance(meters: number) {
  if (meters < 1000) return `${Math.round(meters)} m`
  return `${(meters / 1000).toFixed(1).replace('.', ',')} km`
}

export function formatPercent(value: number) {
  return `${Math.round(value * 100)}%`
}
