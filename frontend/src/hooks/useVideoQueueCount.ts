import { useReviewRequests } from '@/hooks/useReviewRequests'
import { VIDEO_PROVIDERS } from '@/lib/providers'

// Video rows waiting on a human: prompts to approve plus failures to retry.
//
// Scoped to the video providers because image and video share one queue — an
// unscoped count would badge Video with image work and vice versa. Rides the
// Video page's own fetch via the shared query key, so the sidebar badge costs
// one request whether or not that page is open.
export const useVideoQueueCount = (): number => {
  const { data } = useReviewRequests(VIDEO_PROVIDERS)
  const counts = data?.status_counts
  return (counts?.pending_review ?? 0) + (counts?.failed ?? 0)
}
