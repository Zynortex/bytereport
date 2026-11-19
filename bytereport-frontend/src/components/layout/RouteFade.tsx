import { useLocation } from "react-router-dom";

/**
 * Fades page content in on every route change.
 *
 * The `key` is what makes it work: React tears the subtree down and builds a
 * fresh one, so the CSS animation runs again instead of being stuck on the
 * "already finished" state it reached the first time.
 *
 * Which key matters. Inside the app shell this keys on the full pathname, so
 * dashboard -> report crossfades the content column. At the top level it keys
 * on the route GROUP (see `routeGroup`) — every authenticated route shares one
 * key there, so navigating inside the shell does not re-mount the sidebar and
 * make the whole window blink.
 */
export function RouteFade({ routeKey, children }: { routeKey: string; children: React.ReactNode }) {
  return (
    <div key={routeKey} className="anim-route">
      {children}
    </div>
  );
}

const SHELL_ROUTES = ["/dashboard", "/upload", "/report", "/voice-note", "/tax-simulator"];

/** Collapses every route rendered inside AppLayout into a single key. */
export function routeGroup(pathname: string): string {
  return SHELL_ROUTES.some((r) => pathname.startsWith(r)) ? "shell" : pathname;
}

/** Convenience for the top-level <Routes>, which has no pathname of its own. */
export function useRouteGroup(): string {
  return routeGroup(useLocation().pathname);
}
