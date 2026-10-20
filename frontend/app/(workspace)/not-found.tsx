import Link from 'next/link'

import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { EmptyState } from '@/components/ui/feedback'

export default function NotFound() {
  return (
    <div className="mx-auto w-full max-w-2xl px-4 py-10">
      <Card>
        <CardContent className="p-0">
          <EmptyState
            title="Page not found"
            description="The page you asked for does not exist. It may have been moved, or the link may be out of date."
            action={
              <Button nativeButton={false} render={<Link href="/analyses" />}>
                Go to the analyses
              </Button>
            }
          />
        </CardContent>
      </Card>
    </div>
  )
}
