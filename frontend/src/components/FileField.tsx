export function FileField({
  label,
  accept,
  onChange,
}: {
  label: string
  accept: string
  onChange: (file: File | null) => void
}) {
  return (
    <label className="flex flex-col gap-1 text-sm">
      <span className="text-mutedfg">{label}</span>
      <input
        type="file"
        accept={accept}
        className="border border-line bg-bg px-2 py-1.5 text-sm file:mr-3 file:border-0 file:bg-muted file:px-3 file:py-1"
        onChange={(e) => onChange(e.target.files?.[0] ?? null)}
      />
    </label>
  )
}
