import { AuthProvider } from '@/lib/auth/session'

import { AppShell } from '@/components/shell/app-shell'

export default function WorkspaceLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <AuthProvider>
      <AppShell>{children}</AppShell>
    </AuthProvider>
  )
}
