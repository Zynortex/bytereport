import { lazy, Suspense, useEffect } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { LazyMotion, MotionConfig, domAnimation } from "motion/react";
import { EASE } from "@/lib/motionTokens";
import { RouteFade, useRouteGroup } from "@/components/layout/RouteFade";
import { AppLayout } from "@/components/layout/AppLayout";
import { ServerWakeOverlay } from "@/components/layout/ServerWakeOverlay";
import { useAuthStore } from "@/store/authStore";
import { useDocumentTitle } from "@/lib/useDocumentTitle";
import Landing from "@/pages/Landing";

// Everything but the landing page is loaded on demand. The landing used to
// ship the whole product — charts, the report, the voice recorder — in one
// 1.3 MB chunk before the first headline could paint.
const Auth         = lazy(() => import("@/pages/Auth"));
const Demo         = lazy(() => import("@/pages/Demo"));
const Pricing      = lazy(() => import("@/pages/Pricing"));
const Dashboard    = lazy(() => import("@/pages/Dashboard"));
const UploadPage   = lazy(() => import("@/pages/Upload"));
const Report       = lazy(() => import("@/pages/Report"));
const TaxSimulator = lazy(() => import("@/pages/TaxSimulator"));
const VoiceNote    = lazy(() => import("@/pages/VoiceNote"));

export default function App() {
  const { init } = useAuthStore();
  useEffect(() => { init(); }, [init]);

  return (
    // LazyMotion + domAnimation: only the animation features the site uses,
    // and `strict` refuses the full-size `motion.*` components by accident.
    // reducedMotion="user": under the OS setting, transforms are dropped and
    // only fades remain.
    <LazyMotion features={domAnimation} strict>
      <MotionConfig reducedMotion="user" transition={{ ease: EASE }}>
        <BrowserRouter>
          <AnimatedRoutes />
        </BrowserRouter>
        <ServerWakeOverlay />
      </MotionConfig>
    </LazyMotion>
  );
}

/**
 * Split out because useLocation() only works below <BrowserRouter>.
 * Every route inside AppLayout shares one key, so switching pages in the
 * sidebar re-runs the fade in <main> (see AppLayout) and leaves the shell
 * itself untouched.
 */
function AnimatedRoutes() {
  useDocumentTitle();
  return (
    <RouteFade routeKey={useRouteGroup()}>
      <Suspense fallback={null}>
      <Routes>
        <Route path="/"        element={<Landing />} />
        <Route path="/auth"    element={<Auth />} />
        <Route path="/demo"    element={<Demo />} />
        <Route path="/pricing" element={<Pricing />} />

        <Route element={<AppLayout />}>
          <Route path="/dashboard"     element={<Dashboard />} />
          <Route path="/upload"        element={<UploadPage />} />
          <Route path="/report"        element={<Report />} />
          <Route path="/voice-note"    element={<VoiceNote />} />
          <Route path="/tax-simulator" element={<TaxSimulator />} />
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      </Suspense>
    </RouteFade>
  );
}
