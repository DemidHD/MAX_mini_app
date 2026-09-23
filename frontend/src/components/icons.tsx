import type { ReactNode } from 'react'

/**
 * Линейные иконки экранов P0. Все рисуются `currentColor`, размер задаётся
 * пропсом — цвет и габариты определяет место использования.
 */

interface IconProps {
  size?: number
  strokeWidth?: number
}

function Svg({ size = 20, children, viewBox = '0 0 24 24' }: { size?: number; children: ReactNode; viewBox?: string }) {
  return (
    <svg width={size} height={size} viewBox={viewBox} fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      {children}
    </svg>
  )
}

export function ChevronLeftIcon({ size = 20, strokeWidth = 2 }: IconProps) {
  return (
    <Svg size={size}>
      <path d="M14.5 5.5 8 12l6.5 6.5" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" />
    </Svg>
  )
}

export function ChevronRightIcon({ size = 20, strokeWidth = 2 }: IconProps) {
  return (
    <Svg size={size}>
      <path d="M9.5 5.5 16 12l-6.5 6.5" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" />
    </Svg>
  )
}

export function ArrowLeftIcon({ size = 20, strokeWidth = 2 }: IconProps) {
  return (
    <Svg size={size}>
      <path d="M19.5 12h-15M10.5 5.5 4 12l6.5 6.5" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" />
    </Svg>
  )
}

export function ArrowRightIcon({ size = 20, strokeWidth = 2 }: IconProps) {
  return (
    <Svg size={size}>
      <path d="M4.5 12h15M13.5 5.5 20 12l-6.5 6.5" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" />
    </Svg>
  )
}

export function CheckIcon({ size = 20, strokeWidth = 2.4 }: IconProps) {
  return (
    <Svg size={size}>
      <path d="m5.5 12.5 4.2 4.2 8.8-9.4" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" />
    </Svg>
  )
}

export function CloseIcon({ size = 20, strokeWidth = 2 }: IconProps) {
  return (
    <Svg size={size}>
      <path d="M6 6l12 12M18 6 6 18" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" />
    </Svg>
  )
}

export function MinusIcon({ size = 20, strokeWidth = 2.2 }: IconProps) {
  return (
    <Svg size={size}>
      <path d="M6 12h12" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" />
    </Svg>
  )
}

export function PlusIcon({ size = 20, strokeWidth = 2.2 }: IconProps) {
  return (
    <Svg size={size}>
      <path d="M12 5v14M5 12h14" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" />
    </Svg>
  )
}

export function MoreIcon({ size = 20 }: IconProps) {
  return (
    <Svg size={size}>
      <circle cx="5.5" cy="12" r="1.9" fill="currentColor" />
      <circle cx="12" cy="12" r="1.9" fill="currentColor" />
      <circle cx="18.5" cy="12" r="1.9" fill="currentColor" />
    </Svg>
  )
}

export function CalendarIcon({ size = 20, strokeWidth = 1.8 }: IconProps) {
  return (
    <Svg size={size}>
      <rect x="3.5" y="5.5" width="17" height="15" rx="2.5" stroke="currentColor" strokeWidth={strokeWidth} />
      <path d="M3.5 10h17M8 3.5v3M16 3.5v3" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" />
    </Svg>
  )
}

export function PinIcon({ size = 20, strokeWidth = 1.8 }: IconProps) {
  return (
    <Svg size={size}>
      <path d="M12 21s7-6.5 7-11.5a7 7 0 1 0-14 0C5 14.5 12 21 12 21Z" stroke="currentColor" strokeWidth={strokeWidth} strokeLinejoin="round" />
      <circle cx="12" cy="9.5" r="2.5" stroke="currentColor" strokeWidth={strokeWidth} />
    </Svg>
  )
}

export function ClockIcon({ size = 20, strokeWidth = 1.8 }: IconProps) {
  return (
    <Svg size={size}>
      <circle cx="12" cy="12" r="8.5" stroke="currentColor" strokeWidth={strokeWidth} />
      <path d="M12 7.5V12l3 2" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" />
    </Svg>
  )
}

export function BriefcaseIcon({ size = 20, strokeWidth = 1.8 }: IconProps) {
  return (
    <Svg size={size}>
      <rect x="3.5" y="7.5" width="17" height="12" rx="2" stroke="currentColor" strokeWidth={strokeWidth} />
      <path d="M8.5 7.5V6a2 2 0 0 1 2-2h3a2 2 0 0 1 2 2v1.5M3.5 12.5h17" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" />
    </Svg>
  )
}

export function RubleIcon({ size = 20, strokeWidth = 1.9 }: IconProps) {
  return (
    <Svg size={size}>
      <path d="M8.5 20V4.5h5a4 4 0 0 1 0 8h-7M6.5 16.5h8" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" />
    </Svg>
  )
}

export function BoltIcon({ size = 20, strokeWidth = 1.8 }: IconProps) {
  return (
    <Svg size={size}>
      <path d="M13 3 5.5 13.5H12L11 21l7.5-10.5H12L13 3Z" stroke="currentColor" strokeWidth={strokeWidth} strokeLinejoin="round" />
    </Svg>
  )
}

export function SendIcon({ size = 20, strokeWidth = 1.9 }: IconProps) {
  return (
    <Svg size={size}>
      <path d="M20.5 3.5 3.5 10.2l6.9 2.9m10.1-9.6-5.4 17-4.7-7.4m10.1-9.6L10.4 13.1" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" />
    </Svg>
  )
}

export function BookmarkIcon({ size = 20, strokeWidth = 1.9 }: IconProps) {
  return (
    <Svg size={size}>
      <path d="M6.5 4.5h11v16L12 16.5l-5.5 4v-16Z" stroke="currentColor" strokeWidth={strokeWidth} strokeLinejoin="round" />
    </Svg>
  )
}

export function InfoIcon({ size = 20, strokeWidth = 1.8 }: IconProps) {
  return (
    <Svg size={size}>
      <circle cx="12" cy="12" r="8.5" stroke="currentColor" strokeWidth={strokeWidth} />
      <path d="M12 11v5.5" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" />
      <circle cx="12" cy="7.8" r="1.1" fill="currentColor" />
    </Svg>
  )
}

export function BellIcon({ size = 20, strokeWidth = 1.8 }: IconProps) {
  return (
    <Svg size={size}>
      <path d="M6 10a6 6 0 1 1 12 0c0 4 1.5 5.5 1.5 5.5h-15S6 14 6 10Z" stroke="currentColor" strokeWidth={strokeWidth} strokeLinejoin="round" />
      <path d="M10 19a2 2 0 0 0 4 0" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" />
    </Svg>
  )
}

export function SlidersIcon({ size = 20, strokeWidth = 1.8 }: IconProps) {
  return (
    <Svg size={size}>
      <path d="M4 6.5h16M4 12h16M4 17.5h16" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" />
      <circle cx="9" cy="6.5" r="2" fill="#fff" stroke="currentColor" strokeWidth={strokeWidth} />
      <circle cx="15" cy="12" r="2" fill="#fff" stroke="currentColor" strokeWidth={strokeWidth} />
      <circle cx="8" cy="17.5" r="2" fill="#fff" stroke="currentColor" strokeWidth={strokeWidth} />
    </Svg>
  )
}

export function SortIcon({ size = 20, strokeWidth = 1.8 }: IconProps) {
  return (
    <Svg size={size}>
      <path d="M8 19V5M4.5 8.5 8 5l3.5 3.5M16 5v14M12.5 15.5 16 19l3.5-3.5" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" />
    </Svg>
  )
}

export function CoinsIcon({ size = 20, strokeWidth = 1.8 }: IconProps) {
  return (
    <Svg size={size}>
      <ellipse cx="10" cy="6.5" rx="6" ry="2.5" stroke="currentColor" strokeWidth={strokeWidth} />
      <path d="M4 6.5v4c0 1.4 2.7 2.5 6 2.5s6-1.1 6-2.5v-4M4 10.5v4c0 1.4 2.7 2.5 6 2.5" stroke="currentColor" strokeWidth={strokeWidth} />
      <ellipse cx="15.5" cy="15" rx="4.5" ry="2" stroke="currentColor" strokeWidth={strokeWidth} />
      <path d="M11 15v2.5c0 1.1 2 2 4.5 2s4.5-.9 4.5-2V15" stroke="currentColor" strokeWidth={strokeWidth} />
    </Svg>
  )
}

export function GraduationIcon({ size = 20, strokeWidth = 1.8 }: IconProps) {
  return (
    <Svg size={size}>
      <path d="M2.5 9.5 12 5l9.5 4.5L12 14 2.5 9.5Z" stroke="currentColor" strokeWidth={strokeWidth} strokeLinejoin="round" />
      <path d="M6.5 11.5v4c1.5 1.6 3.3 2.4 5.5 2.4s4-.8 5.5-2.4v-4M21.5 9.5v5" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" />
    </Svg>
  )
}

export function DocumentIcon({ size = 20, strokeWidth = 1.8 }: IconProps) {
  return (
    <Svg size={size}>
      <path d="M6.5 3.5h7l4 4v11.5a1.5 1.5 0 0 1-1.5 1.5h-9.5A1.5 1.5 0 0 1 5 19V5a1.5 1.5 0 0 1 1.5-1.5Z" stroke="currentColor" strokeWidth={strokeWidth} strokeLinejoin="round" />
      <path d="M13.5 3.5V7.5h4" stroke="currentColor" strokeWidth={strokeWidth} strokeLinejoin="round" />
    </Svg>
  )
}

export function CupIcon({ size = 20, strokeWidth = 1.8 }: IconProps) {
  return (
    <Svg size={size}>
      <path d="M5 8.5h11v5.5a5 5 0 0 1-5 5h-1a5 5 0 0 1-5-5V8.5Z" stroke="currentColor" strokeWidth={strokeWidth} strokeLinejoin="round" />
      <path d="M16 10h1.5a2.5 2.5 0 0 1 0 5H16M8 3.5c-.6.8-.6 1.7 0 2.5M11.5 3.5c-.6.8-.6 1.7 0 2.5" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" />
    </Svg>
  )
}

export function SearchIcon({ size = 20, strokeWidth = 1.9 }: IconProps) {
  return (
    <Svg size={size}>
      <circle cx="11" cy="11" r="6.5" stroke="currentColor" strokeWidth={strokeWidth} />
      <path d="m16 16 4 4" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" />
    </Svg>
  )
}

export function UserIcon({ size = 20, strokeWidth = 1.8 }: IconProps) {
  return (
    <Svg size={size}>
      <circle cx="12" cy="8" r="3.8" stroke="currentColor" strokeWidth={strokeWidth} />
      <path d="M4.5 20c.8-3.6 3.8-5.8 7.5-5.8s6.7 2.2 7.5 5.8" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" />
    </Svg>
  )
}

export function FileListIcon({ size = 20, strokeWidth = 1.8 }: IconProps) {
  return (
    <Svg size={size}>
      <path d="M6.5 3.5h7l4 4v11.5a1.5 1.5 0 0 1-1.5 1.5h-9.5A1.5 1.5 0 0 1 5 19V5a1.5 1.5 0 0 1 1.5-1.5Z" stroke="currentColor" strokeWidth={strokeWidth} strokeLinejoin="round" />
      <path d="M8.5 11.5h7M8.5 15h7M8.5 8h3" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" />
    </Svg>
  )
}

/** Иконка сервиса MAX в синей плитке — для строк «уведомление отправлено в MAX». */
export function MaxChatIcon({ size = 24 }: IconProps) {
  return (
    <Svg size={size}>
      <path
        d="M12 3.5a8.5 8.5 0 0 0-7.4 12.7L3.5 20.5l4.5-1a8.5 8.5 0 1 0 4-16Zm0 4.2a4.3 4.3 0 1 1 0 8.6 4.3 4.3 0 0 1 0-8.6Z"
        fill="currentColor"
        fillRule="evenodd"
      />
    </Svg>
  )
}

/** Две черточки-«искры» из макетов. */
export function AccentMarks({ className = '' }: { className?: string }) {
  return (
    <svg className={`accentMarks ${className}`} viewBox="0 0 44 40" fill="none" aria-hidden="true">
      <path d="M8 4 6 20" stroke="currentColor" strokeWidth="4" strokeLinecap="round" />
      <path d="M36 12 22 24" stroke="currentColor" strokeWidth="4" strokeLinecap="round" />
    </svg>
  )
}
