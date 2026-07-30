import { useQuery } from '@tanstack/react-query'
import { reviewApi } from '@/api/review'
import { useProjectId } from '@/hooks/useProjectId'
import { IMAGE_PROVIDERS, type ReviewProvider } from '@/lib/providers'

// The review queue for one kind of work. Every caller on a surface passes the
// same `providers`, and react-query dedupes on the key — so the Flow rail's
// counters ride the panel's fetch rather than adding one.
//
// `providers` is not optional in spirit: image and video both write into this
// queue, so an unscoped read would show a surface other surfaces' work. It is
// part of the query key, so Flow and Video keep separate caches.
//
// 200 rows per fetch caps the *rows*, not the counters: those come from
// `status_counts`, which the backend computes with a GROUP BY over the same
// scope. Poll fast only while something is dispatched and its result is still
// pending; otherwise a slow refresh is enough.
export const useReviewRequests = (
  providers: readonly ReviewProvider[] = IMAGE_PROVIDERS,
) => {
  const projectId = useProjectId() ?? undefined
  return useQuery({
    queryKey: ['review-requests', [...providers].sort().join(','), projectId ?? 'all'],
    queryFn: () =>
      reviewApi.listRequests({
        per_page: 200,
        project_id: projectId,
        provider: [...providers],
      }),
    refetchInterval: query =>
      (query.state.data?.items ?? []).some(i => i.status === 'dispatched') ? 5000 : 30000,
  })
}
