'use client'

import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { EmptyState } from '@/components/ui/feedback'

/**
 * The in-application error boundary.
 *
 * A failure in one workspace view is contained here, so the rest of the
 * application — the navigation, the other views — keeps working.
 */
export default function WorkspaceError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  return (
    <div className="mx-auto w-full max-w-2xl px-4 py-10">
      <Card>
        <CardContent className="p-0">
          <EmptyState
            title="This view could not be loaded"
            description={
              error.message ||
              'An unexpected error occurred. The rest of the analysis is unaffected.'
            }
            action={
              <Button type="button" onClick={reset}>
                Try again
              </Button>
            }
          />
        </CardContent>
      </Card>
    </div>
  )
}
