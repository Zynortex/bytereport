import { useEffect } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { LayoutDashboard, Upload, FileText, LogOut, BarChart2, Mic, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/store/authStore";
import { Button } from "@/components/ui/button";
import { exhaustedKey, isOutOfReports, useCreditsStore } from "@/store/creditsStore";

interface SidebarProps {
  /** Rendered inside the mobile drawer: full width, with a close button, and
   *  every link closes the drawer on the way out. */
  onClose?: () => void;
}

export function Sidebar({ onClose }: SidebarProps = {}) {
  const { pathname } = useLocation();
  const { user, logout } = useAuthStore();
  const navigate = useNavigate();
  const { t, i18n } = useTranslation();
  const { credits, load: loadCredits, clear: clearCredits } = useCreditsStore();

  // Loaded once per account; the upload page refreshes it after each run.
  useEffect(() => { if (user) loadCredits(); }, [user?.id, loadCredits]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleLogout = async () => {
    onClose?.();
    clearCredits();
    await logout();
    navigate("/auth");
  };

  const switchLang = (lang: string) => {
    i18n.changeLanguage(lang);
    localStorage.setItem("br_lang", lang);
  };

  const NAV = [
    { to: "/dashboard",     icon: LayoutDashboard, label: t("nav.dashboard") },
    { to: "/upload",        icon: Upload,          label: t("nav.new_analysis") },
    { to: "/report",        icon: FileText,        label: t("nav.report") },
    { to: "/voice-note",    icon: Mic,             label: t("nav.voice_note") },
    // The tax simulator is off the menu until it is fixed: the business type
    // it asks for does not change the result, and its rates are labelled
    // 2024. The /tax-simulator route still works for anyone with the link.
    // No pricing item: sales are in person for now. /pricing still exists
    // (direct link) and returns with online payment.
  ];

  return (
    // h-full, not h-screen: the shell root is already exactly one viewport tall
    // and does not scroll, so the sidebar fills it and stays put. Its <nav>
    // keeps overflow-y-auto for the case where menu items outgrow the column.
    <aside className={cn(
      "flex flex-col h-full overflow-hidden bg-header border-r border-line shrink-0",
      onClose ? "w-full" : "w-60"
    )}>
      {/* Logo */}
      <div className="flex items-center border-b border-line">
        <Link to="/" onClick={onClose} className="flex-1 flex items-center gap-2.5 px-6 py-5 hover:opacity-80 transition-opacity">
          <div className="w-7 h-7 rounded border border-accent/70 flex items-center justify-center">
            <BarChart2 size={14} className="text-accent" />
          </div>
          <span className="text-fg font-bold text-lg tracking-tight">ByteReport</span>
        </Link>
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            autoFocus
            aria-label={t("nav.close_menu")}
            className="h-11 w-11 mr-2 flex items-center justify-center text-fg/60 hover:text-fg transition-colors duration-200 ease-out active:translate-y-px"
          >
            <X size={20} />
          </button>
        )}
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
        {NAV.map(({ to, icon: Icon, label }) => (
          <Link
            key={to}
            to={to}
            onClick={onClose}
            className={cn(
              "flex items-center gap-3 px-3 py-2.5 max-md:min-h-11 rounded-lg text-sm font-medium transition-colors duration-200 ease-out active:bg-fg/5",
              pathname === to
                ? "bg-brand-blue/12 text-fg font-semibold"
                : "text-fg/60 hover:text-fg hover:bg-transparent/10"
            )}
          >
            <Icon size={16} />
            {label}
          </Link>
        ))}
      </nav>

      {/* Reports left — always in view, so zero is never a surprise. */}
      {credits && (
        <div className="px-6 pb-3 text-xs">
          {credits.unlimited ? (
            <span className="text-fg/50">{t("credits.unlimited")}</span>
          ) : (
            <span className={isOutOfReports(credits) ? "text-sev-medium" : "text-fg/50"}>
              {isOutOfReports(credits)
                ? t(exhaustedKey(credits))
                : t("credits.left", { count: credits.balance ?? 0 })}
            </span>
          )}
        </div>
      )}

      {/* Language switcher */}
      <div className="px-3 pb-2 border-t border-line pt-3">
        <div className="flex gap-1">
          {(["uz", "ru", "en"] as const).map((lang) => (
            <button
              key={lang}
              onClick={() => switchLang(lang)}
              className={cn(
                "flex-1 py-1.5 max-md:min-h-11 text-xs font-bold rounded-md transition-colors duration-200 ease-out active:translate-y-px",
                i18n.language === lang
                  ? "bg-brand-blue text-accent-ink"
                  : "text-fg/40 hover:text-fg hover:bg-transparent/10"
              )}
            >
              {lang.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      {/* User */}
      <div className="px-3 pb-4 pt-2">
        <div className="flex items-center gap-3 px-3 py-2 mb-2">
          <div className="w-8 h-8 rounded-full bg-brand-blue flex items-center justify-center text-accent-ink text-xs font-bold">
            {user?.name?.[0]?.toUpperCase() ?? user?.email?.[0]?.toUpperCase() ?? "U"}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-fg text-xs font-medium truncate">{user?.name ?? user?.email}</p>
            <p className="text-fg/40 text-xs truncate">{user?.email}</p>
          </div>
        </div>
        <Button
          variant="ghost"
          size="sm"
          className="w-full justify-start text-fg/60 hover:text-fg hover:bg-transparent/10"
          onClick={handleLogout}
        >
          <LogOut size={14} className="mr-2" />
          {t("common.logout")}
        </Button>
      </div>
    </aside>
  );
}
