import { ArrowDown, ArrowUp, ArrowUpDown } from 'lucide-react'

export interface SortState<Key extends string> {
  key: Key
  direction: 'asc' | 'desc'
}

interface SortableHeaderProps<Key extends string> {
  columnKey: Key
  label: string
  sort: SortState<Key>
  onSort: (key: Key) => void
}

export function SortableHeader<Key extends string>({
  columnKey,
  label,
  sort,
  onSort,
}: SortableHeaderProps<Key>) {
  const active = sort.key === columnKey
  const Icon = !active ? ArrowUpDown : sort.direction === 'asc' ? ArrowUp : ArrowDown
  return (
    <button
      className={`sort-header ${active ? 'active' : ''}`}
      onClick={() => onSort(columnKey)}
      aria-label={`Ordenar por ${label}`}
      title={`Ordenar por ${label}`}
    >
      <span>{label}</span><Icon size={12} />
    </button>
  )
}

export function compareSortValues(
  first: unknown,
  second: unknown,
  direction: 'asc' | 'desc' = 'asc',
) {
  if (first == null || first === '') return second == null || second === '' ? 0 : 1
  if (second == null || second === '') return -1
  const order = direction === 'asc' ? 1 : -1
  if (typeof first === 'number' && typeof second === 'number') return (first - second) * order
  const firstDate = typeof first === 'string' ? Date.parse(first) : Number.NaN
  const secondDate = typeof second === 'string' ? Date.parse(second) : Number.NaN
  if (Number.isFinite(firstDate) && Number.isFinite(secondDate)) return (firstDate - secondDate) * order
  return String(first).localeCompare(String(second), 'pt-BR', {
    numeric: true,
    sensitivity: 'base',
  }) * order
}
