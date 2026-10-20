'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import {
  BarChart3,
  Building2,
  ClipboardList,
  FileText,
  Info,
  MapPinned,
  Menu,
  Scale,
  X,
} from 'lucide-react'
import * as React from 'react'

import { UserMenu } from '@/components/auth/user-menu'
import { cn } from '@/lib/utils'

type NavItem = {
  href: string
  label: string
  icon: React.ComponentType<{ className?: string }>
  description: string
}

const PRIMARY_NAV: NavItem[] = [
  {
    href: '/analyses',
    label: 'Analyses',
    icon: ClipboardList,
    description: 'Site-selection analyses and their results',
  },
  {
    href: '/analyses/new',
    label: 'New analysis',
    icon: MapPinned,
    description: 'Start a site-selection analysis',
  },
]

const REFERENCE_NAV: NavItem[] = [
  {
    href: '/methodology',
    label: 'Methodology',
    icon: Scale,
    description: 'How the ranking is calculated',
  },
  {
    href: '/data-quality',
    label: 'Data quality',
    icon: BarChart3,
    description: 'Coverage, freshness and limitations',
  },
  {
    href: '/reports',
    label: 'Reports',
    icon: FileText,
    description: 'Executive decision reports',
  },
]

function NavLink({ item, onNavigate }: { item: NavItem; onNavigate?: () => void }) {
  const pathname = usePathname()
  const isActive =
    item.href === '/analyses'
      ? pathname === '/analyses' || pathname.startsWith('/analyses/')
      : pathname.startsWith(item.href)

  const Icon = item.icon
  return (
    <Link
      href={item.href}
      onClick={onNavigate}
      aria-current={isActive ? 'page' : undefined}
      className={cn(
        'group flex items-start gap-2.5 rounded-md px-2.5 py-2 transition-colors',
        'focus-visible:ring-ring focus-visible:ring-2 focus-visible:outline-none',
        isActive
          ? 'bg-surface-muted text-ink'
          : 'text-ink-muted hover:bg-surface-muted/70 hover:text-ink',
      )}
    >
      <Icon
        className={cn(
          'mt-0.5 size-4 shrink-0',
          isActive ? 'text-primary' : 'text-ink-subtle group-hover:text-ink-muted',
        )}
        aria-hidden="true"
      />
      <span className="min-w-0">
        <span className="block text-[13px] leading-tight font-medium">{item.label}</span>
        <span className="text-ink-subtle block text-[11px] leading-snug">{item.description}</span>
      </span>
    </Link>
  )
}

function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <>
      <div className="flex items-center gap-2.5 px-2.5 py-4">
        <span className="bg-primary text-primary-foreground flex size-8 shrink-0 items-center justify-center rounded-lg text-[13px] font-bold">
          <Building2 className="size-4" aria-hidden="true" />
        </span>
        <span className="min-w-0">
          <span className="text-ink block text-[13px] leading-tight font-semibold tracking-tight">
            Site Intelligence
          </span>
          <span className="text-ink-subtle block text-[10px] tracking-[0.14em] uppercase">
            Retail expansion
          </span>
        </span>
      </div>

      <nav aria-label="Primary" className="flex flex-col gap-0.5">
        {PRIMARY_NAV.map((item) => (
          <NavLink key={item.href} item={item} onNavigate={onNavigate} />
        ))}
      </nav>

      <div className="mt-6">
        <p className="section-eyebrow px-2.5 pb-1.5">Reference</p>
        <nav aria-label="Reference" className="flex flex-col gap-0.5">
          {REFERENCE_NAV.map((item) => (
            <NavLink key={item.href} item={item} onNavigate={onNavigate} />
          ))}
        </nav>
      </div>

      <div className="mt-auto px-2.5 pt-6">
        <div className="bg-surface-muted border-line rounded-md border p-3">
          <p className="text-ink flex items-center gap-1.5 text-[11px] font-semibold">
            <Info className="size-3.5" aria-hidden="true" />
            Decision support only
          </p>
          <p className="text-ink-muted mt-1 text-[11px] leading-relaxed">
            Rankings express relative fit against your stated requirements. Site
            visits and commercial due diligence remain necessary before capital
            commitment.
          </p>
        </div>
      </div>
    </>
  )
}

/**
 * Application shell: a persistent sidebar on large screens and a slide-over
 * drawer on small ones.  The skip link is the first focusable element so
 * keyboard users can jump straight to the main content.
 */
export function AppShell({ children }: { children: React.ReactNode }) {
  const [mobileOpen, setMobileOpen] = React.useState(false)
  const pathname = usePathname()

  React.useEffect(() => {
    setMobileOpen(false)
  }, [pathname])

  return (
    <div className="min-h-screen lg:flex">
      <a href="#main-content" className="skip-link">
        Skip to main content
      </a>

      {/* Desktop sidebar */}
      <aside className="border-line bg-surface hidden w-[264px] shrink-0 flex-col border-r lg:flex">
        <div className="flex h-full flex-col overflow-y-auto px-3 py-2">
          <SidebarContent />
        </div>
      </aside>

      {/* Mobile drawer */}
      {mobileOpen ? (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button
            type="button"
            className="absolute inset-0 bg-[#111820]/40"
            aria-label="Close navigation"
            onClick={() => setMobileOpen(false)}
          />
          <div className="border-line bg-surface absolute inset-y-0 left-0 flex w-[280px] max-w-[85vw] flex-col border-r shadow-xl">
            <div className="flex items-center justify-end px-3 pt-3">
              <button
                type="button"
                onClick={() => setMobileOpen(false)}
                className="text-ink-muted hover:bg-surface-muted hover:text-ink rounded p-1.5"
                aria-label="Close navigation"
              >
                <X className="size-4" />
              </button>
            </div>
            <div className="flex min-h-0 flex-1 flex-col overflow-y-auto px-3 pb-3">
              <SidebarContent onNavigate={() => setMobileOpen(false)} />
            </div>
          </div>
        </div>
      ) : null}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="border-line bg-surface/90 sticky top-0 z-30 flex h-14 items-center gap-3 border-b px-4 backdrop-blur lg:hidden">
          <button
            type="button"
            onClick={() => setMobileOpen(true)}
            className="text-ink-muted hover:bg-surface-muted hover:text-ink rounded p-1.5"
            aria-label="Open navigation"
            aria-expanded={mobileOpen}
          >
            <Menu className="size-5" />
          </button>
          <span className="text-ink text-[13px] font-semibold">Site Intelligence</span>
          <div className="ml-auto">
            <UserMenu />
          </div>
        </header>

        <main id="main-content" className="min-w-0 flex-1">
          {children}
        </main>
      </div>
    </div>
  )
}
