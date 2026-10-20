import { Analytics } from '@vercel/analytics/next'
import type { Metadata, Viewport } from 'next'

import './globals.css'

export const metadata: Metadata = {
  title: {
    default: 'Retail Site Intelligence & Site Selection',
    template: '%s · Retail Site Intelligence',
  },
  description:
    'Decision-support platform for retail site selection: candidate evaluation, explicit weighting, explainable ranking, cost analysis and executive reporting.',
  applicationName: 'Retail Site Intelligence',
  keywords: [
    'retail site selection',
    'location intelligence',
    'multi-criteria decision analysis',
    'site scoring',
    'expansion planning',
  ],
  icons: {
    icon: [
      { url: '/icon-light-32x32.png', media: '(prefers-color-scheme: light)' },
      { url: '/icon.svg', type: 'image/svg+xml' },
    ],
    apple: '/apple-icon.png',
  },
}

export const viewport: Viewport = {
  colorScheme: 'light',
  themeColor: '#f4f6f8',
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="en">
      <body className="antialiased">
        {children}
        {process.env.NODE_ENV === 'production' && <Analytics />}
      </body>
    </html>
  )
}
