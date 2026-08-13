import type { PropsWithChildren, ReactNode } from 'react'

export function Card({ title, children }: PropsWithChildren<{ title: ReactNode }>) {
  return (
    <div className="border border-line bg-surface p-5 mb-4">
      <h2 className="text-base font-semibold mb-4">{title}</h2>
      {children}
    </div>
  )
}
