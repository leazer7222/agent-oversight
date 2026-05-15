import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

const CST: Intl.DateTimeFormatOptions = { timeZone: 'America/Chicago' }

export function formatDateTime(date: string | Date | null | undefined): string {
  if (!date) return '—'
  return new Date(date).toLocaleString('en-US', CST)
}

export function formatDate(date: string | Date | null | undefined): string {
  if (!date) return '—'
  return new Date(date).toLocaleDateString('en-US', CST)
}

export function formatTime(date: string | Date | null | undefined): string {
  if (!date) return '—'
  return new Date(date).toLocaleTimeString('en-US', CST)
}
