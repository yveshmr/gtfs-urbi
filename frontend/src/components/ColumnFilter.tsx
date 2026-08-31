interface ColumnFilterProps {
  label: string
  value: string
  onChange: (value: string) => void
  placeholder?: string
}

export function ColumnFilter({ label, value, onChange, placeholder }: ColumnFilterProps) {
  return (
    <input
      className="column-filter"
      value={value}
      onChange={(event) => onChange(event.target.value)}
      placeholder={placeholder ?? 'Filtrar'}
      aria-label={`Filtrar ${label}`}
    />
  )
}
