import { useState, useEffect } from "react";
import { useNavigate, useSearchParams, Link } from "react-router-dom";
import { BarChart2, Eye, EyeOff, Loader2, MailCheck } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { LanguageSwitcher } from "@/components/ui/LanguageSwitcher";
import { useAuthStore } from "@/store/authStore";
import { warmUp } from "@/api/serverWake";
import { FREE_REPORTS_ON_SIGNUP } from "@/lib/pricing";

export default function Auth() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const defaultTab = params.get("tab") === "register" ? "register" : "login";
  const { t } = useTranslation();

  const { login, register, loading, error, user, needsEmailConfirmation } = useAuthStore();
  const [showPw, setShowPw] = useState(false);

  const [loginEmail, setLoginEmail] = useState("");
  const [loginPw, setLoginPw]       = useState("");
  const [regName, setRegName]       = useState("");
  const [regEmail, setRegEmail]     = useState("");
  const [regPw, setRegPw]           = useState("");

  useEffect(() => {
    if (user) navigate("/dashboard", { replace: true });
  }, [user, navigate]);

  // Signing in goes to Supabase, not to our backend; the upload right after it
  // does. Wake the backend now so it is up by then.
  useEffect(() => { warmUp(); }, []);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    await login(loginEmail, loginPw);
  };

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    await register(regEmail, regPw, regName);
  };

  // ── Early return: email confirmation pending ────────────────────────────
  if (needsEmailConfirmation) {
    return (
      <div className="min-h-screen bg-ground flex items-center justify-center p-6 relative">
        <div className="absolute top-4 right-4">
          <LanguageSwitcher />
        </div>
        <div className="w-full max-w-md text-center">
          <div className="w-16 h-16 rounded-2xl bg-line/40 flex items-center justify-center mx-auto mb-6">
            <MailCheck size={32} className="text-brand-blue" />
          </div>
          <h2 className="text-2xl font-bold text-brand-dark mb-2">{t("auth.check_email")}</h2>
          <p className="text-brand-muted text-sm mb-2">
            {t("auth.email_sent_prefix")}{" "}
            <span className="font-medium text-brand-dark">{regEmail}</span>
          </p>
          <p className="text-brand-muted text-sm mb-8">{t("auth.email_sent_detail")}</p>
          <Link to="/auth" className="text-sm text-brand-blue hover:underline">
            {t("auth.back_to_login")}
          </Link>
        </div>
      </div>
    );
  }

  // ── Main auth screen ────────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-ground flex relative">
      {/* Language switcher — always visible top-right */}
      <div className="absolute top-4 right-4 z-10">
        <LanguageSwitcher />
      </div>

      {/* Left panel */}
      <div className="hidden lg:flex w-1/2 bg-header flex-col justify-between p-12">
        <Link to="/" className="flex items-center gap-2 min-h-11">
          <div className="w-7 h-7 rounded border border-accent/70 flex items-center justify-center">
            <BarChart2 size={14} className="text-accent" />
          </div>
          <span className="text-white font-bold text-lg">ByteReport</span>
        </Link>
        <div>
          <div className="text-5xl font-black text-white leading-tight mb-4">
            {t("auth.tagline")}
          </div>
          <p className="text-white/50 text-base leading-relaxed max-w-sm">
            {t("auth.tagline_sub")}
          </p>
        </div>
        <p className="text-white/20 text-sm">{t("auth.copyright", { year: new Date().getFullYear() })}</p>
      </div>

      {/* Right panel */}
      <div className="flex-1 flex items-center justify-center p-6">
        <div className="w-full max-w-md">

          {/* Mobile logo */}
          <div className="lg:hidden flex items-center gap-2 mb-8">
            <div className="w-7 h-7 rounded border border-accent/70 flex items-center justify-center">
            <BarChart2 size={14} className="text-accent" />
          </div>
            <span className="font-bold text-brand-dark text-lg">ByteReport</span>
          </div>

          <Tabs defaultValue={defaultTab}>
            <TabsList className="w-full mb-8">
              <TabsTrigger value="login"    className="flex-1">{t("auth.login_tab")}</TabsTrigger>
              <TabsTrigger value="register" className="flex-1">{t("auth.register_tab")}</TabsTrigger>
            </TabsList>

            {/* ── Login ── */}
            <TabsContent value="login">
              <h2 className="text-2xl font-bold text-brand-dark mb-1">{t("auth.welcome_back")}</h2>
              <p className="text-brand-muted text-sm mb-6">{t("auth.enter_credentials")}</p>
              <form onSubmit={handleLogin} className="space-y-4">
                <div className="space-y-1.5">
                  <Label htmlFor="l-email">Email</Label>
                  <Input
                    id="l-email" type="email" placeholder="you@company.com"
                    value={loginEmail} onChange={(e) => setLoginEmail(e.target.value)}
                    required
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="l-pw">{t("auth.password")}</Label>
                  {/* pr-10 on the field clears the eye toggle, which is
                      absolutely positioned inside it — without the padding a
                      long value runs underneath the icon. */}
                  <div className="relative">
                    <Input
                      id="l-pw" type={showPw ? "text" : "password"} placeholder="••••••••"
                      value={loginPw} onChange={(e) => setLoginPw(e.target.value)}
                      className="pr-10"
                      required
                    />
                    <button
                      type="button" onClick={() => setShowPw(!showPw)}
                      aria-label={showPw ? t("auth.hide_password") : t("auth.show_password")}
                      className="absolute right-0 top-1/2 -translate-y-1/2 h-11 w-11 flex items-center justify-center text-brand-muted hover:text-brand-dark transition-colors duration-200 ease-out"
                    >
                      {showPw ? <EyeOff size={15} /> : <Eye size={15} />}
                    </button>
                  </div>
                </div>
                {error && (
                  <p className="text-sm text-sev-high bg-sev-high/15 px-3 py-2 rounded-lg">{error}</p>
                )}
                <Button className="w-full" size="lg" disabled={loading}>
                  {loading && <Loader2 size={16} className="animate-spin mr-2" />}
                  {t("auth.login_btn")}
                </Button>
              </form>
            </TabsContent>

            {/* ── Register ── */}
            <TabsContent value="register">
              <h2 className="text-2xl font-bold text-brand-dark mb-1">{t("auth.create_account")}</h2>
              <p className="text-brand-muted text-sm mb-6">{t("auth.free_reports", { count: FREE_REPORTS_ON_SIGNUP })}</p>
              <form onSubmit={handleRegister} className="space-y-4">
                <div className="space-y-1.5">
                  <Label htmlFor="r-name">{t("auth.name_label")}</Label>
                  <Input
                    id="r-name" placeholder={t("auth.name_placeholder")}
                    value={regName} onChange={(e) => setRegName(e.target.value)}
                    required
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="r-email">Email</Label>
                  <Input
                    id="r-email" type="email" placeholder="you@company.com"
                    value={regEmail} onChange={(e) => setRegEmail(e.target.value)}
                    required
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="r-pw">{t("auth.password")}</Label>
                  <div className="relative">
                    <Input
                      id="r-pw" type={showPw ? "text" : "password"} placeholder={t("auth.password_min")}
                      value={regPw} onChange={(e) => setRegPw(e.target.value)}
                      className="pr-10"
                      minLength={8} required
                    />
                    <button
                      type="button" onClick={() => setShowPw(!showPw)}
                      aria-label={showPw ? t("auth.hide_password") : t("auth.show_password")}
                      className="absolute right-0 top-1/2 -translate-y-1/2 h-11 w-11 flex items-center justify-center text-brand-muted hover:text-brand-dark transition-colors duration-200 ease-out"
                    >
                      {showPw ? <EyeOff size={15} /> : <Eye size={15} />}
                    </button>
                  </div>
                </div>
                {error && (
                  <p className="text-sm text-sev-high bg-sev-high/15 px-3 py-2 rounded-lg">{error}</p>
                )}
                <Button className="w-full" size="lg" disabled={loading}>
                  {loading && <Loader2 size={16} className="animate-spin mr-2" />}
                  {t("auth.register_btn")}
                </Button>
                <p className="text-xs text-brand-muted text-center">{t("auth.terms")}</p>
              </form>
            </TabsContent>
          </Tabs>

        </div>
      </div>
    </div>
  );
}
