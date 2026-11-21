import { Suspense, useEffect, useState } from "react";
import { Link, Navigate, Outlet, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { BarChart2, Loader2, Menu } from "lucide-react";
import { Sidebar } from "./Sidebar";
import { RouteFade } from "./RouteFade";
import { LanguageSwitcher } from "@/components/ui/LanguageSwitcher";
import { useAuthStore } from "@/store/authStore";
import { useExitAnimation } from "@/lib/motion";
import { cn } from "@/lib/utils";

const DRAWER_EXIT_MS = 180;

export function AppLayout() {
  const { user, isReady } = useAuthStore();
  const { pathname } = useLocation();
  const { t } = useTranslation();

  // Below md the sidebar is a drawer. On a 390px phone a fixed 240px column
  // left about 150px for the page itself.
  const [menuOpen, setMenuOpen] = useState(false);
  const { mounted: drawerMounted, closing: drawerClosing } = useExitAnimation(menuOpen, DRAWER_EXIT_MS);
  useEffect(() => { setMenuOpen(false); }, [pathname]);
  useEffect(() => {
    if (!menuOpen) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setMenuOpen(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [menuOpen]);

  // Wait for init() to resolve the session before judging. Redirecting on the
  // first render — while `user` is still null — bounced a logged-in user who
  // refreshed or opened a link directly out to /auth, and dropped the query
  // string on the way, so /report?id=… never reached the report.
  if (!isReady) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-ground">
        <Loader2 size={28} className="animate-spin text-brand-blue" />
      </div>
    );
  }
  if (!user) return <Navigate to="/auth" replace />;

  return (
    // App shell: the ROOT owns the viewport height and forbids its own scroll,
    // so the only scrollable region is <main>. Previously this was
    // `min-h-screen` with no overflow rule — the root grew past the viewport,
    // <main>'s `overflow-auto` never had a definite height to scroll inside, so
    // the whole DOCUMENT scrolled and carried the sidebar off-screen with it.
    // Constraining height here is what actually pins the sidebar; h-screen on
    // <aside> alone could not, since it still sat in normal document flow.
    <div className="flex h-screen overflow-hidden bg-ground">
      <div className="hidden md:flex h-full">
        <Sidebar />
      </div>
      <div className="flex-1 flex flex-col overflow-hidden min-w-0">
        <header className="h-13 bg-transparent border-b border-brand-border flex items-center justify-between md:justify-end gap-2 pl-1 pr-3 md:px-6 shrink-0">
          <div className="flex items-center min-w-0 md:hidden">
            <button
              type="button"
              onClick={() => setMenuOpen(true)}
              aria-label={t("nav.open_menu")}
              aria-expanded={menuOpen}
              aria-controls="mobile-nav"
              className="h-11 w-11 flex items-center justify-center text-brand-muted hover:text-brand-dark transition-colors duration-200 ease-out active:translate-y-px"
            >
              <Menu size={20} />
            </button>
            <Link to="/dashboard" className="flex items-center gap-2 min-h-11 pr-2">
              <span className="w-6 h-6 rounded border border-accent/70 flex items-center justify-center">
                <BarChart2 size={12} className="text-accent" />
              </span>
              <span className="text-brand-dark font-bold tracking-tight">ByteReport</span>
            </Link>
          </div>
          <LanguageSwitcher />
        </header>
        <main className="flex-1 overflow-y-auto">
          <RouteFade routeKey={pathname}>
            {/* Pages load on demand; the shell stays put while one does. */}
            <Suspense fallback={<div className="p-8"><div className="skeleton h-8 w-56" /></div>}>
              <Outlet />
            </Suspense>
          </RouteFade>
        </main>
      </div>

      {/* Mobile navigation drawer — the same overlay language as the chat
          panel: a dimmed backdrop that fades, a surface that slides 16px. */}
      {drawerMounted && (
        <div className="md:hidden">
          <div
            className={cn("fixed inset-0 z-40 bg-ground/60", drawerClosing ? "anim-fade-out" : "anim-fade-in")}
            onClick={() => setMenuOpen(false)}
            aria-hidden="true"
          />
          <div
            id="mobile-nav"
            role="dialog"
            aria-modal="true"
            aria-label={t("nav.menu")}
            className={cn(
              "fixed inset-y-0 left-0 z-50 w-[min(18rem,85vw)]",
              drawerClosing ? "anim-drawer-out" : "anim-drawer-in"
            )}
          >
            <Sidebar onClose={() => setMenuOpen(false)} />
          </div>
        </div>
      )}
    </div>
  );
}
