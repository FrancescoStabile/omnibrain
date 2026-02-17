/**
 * Root loading state — intentionally empty.
 *
 * Route transitions are handled instantly by the Zustand store in AppShell.
 * Pages only render <ViewSync /> (returns null), so there's nothing to "load".
 * Returning null prevents the skeleton flash that Next.js Suspense would show
 * on every router.push().
 */
export default function Loading() {
  return null;
}
