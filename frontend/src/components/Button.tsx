import type { ButtonHTMLAttributes } from 'react'

type Variant = 'primary' | 'secondary'

export function Button({
  variant = 'primary',
  className = '',
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  const base = 'px-4 py-2 text-sm font-medium border disabled:opacity-50 disabled:cursor-not-allowed'
  const styles =
    variant === 'primary'
      ? 'bg-fg text-bg border-fg hover:opacity-90'
      : 'bg-surface text-fg border-line hover:bg-muted'
  return <button className={`${base} ${styles} ${className}`} {...props} />
}
