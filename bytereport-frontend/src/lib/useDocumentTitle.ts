import { useEffect } from "react";
import { useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useReportStore } from "@/store/reportStore";

// Route -> the page's own name. The report tab carries the business name, so
// an accountant with three clients' reports open can tell the tabs apart.
const TITLE_KEYS: Record<string, string> = {
  "/auth":          "meta.title_auth",
  "/dashboard":     "nav.dashboard",
  "/upload":        "nav.new_analysis",
  "/report":        "nav.report",
  "/voice-note":    "nav.voice_note",
  "/pricing":       "nav.tariffs",
  "/demo":          "meta.title_demo",
  "/tax-simulator": "nav.tax_simulator",
};

/** Sets the tab title and <html lang> for whatever route is showing. */
export function useDocumentTitle() {
  const { pathname } = useLocation();
  const { t, i18n } = useTranslation();
  const businessName = useReportStore((s) => s.businessInfo.name);

  useEffect(() => {
    const key = TITLE_KEYS[pathname];
    const page = pathname === "/report" && businessName ? businessName : key ? t(key) : null;
    document.title = page ? `${page} · ByteReport` : t("meta.title_home");
    document.documentElement.lang = (i18n.language || "en").slice(0, 2);
  }, [pathname, t, i18n.language, businessName]);
}
