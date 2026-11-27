import { lazy, Suspense, type ReactNode } from "react";
import { createBrowserRouter, Navigate, type RouteObject } from "react-router";

import { AppShell } from "../components/AppShell";

const TodayPage = lazy(() => import("../features/today/TodayPage"));
const AskPage = lazy(() => import("../features/ask/AskPage"));
const HomeAirPage = lazy(() => import("../features/home-air/HomeAirPage"));
const ImpactPage = lazy(() => import("../features/impact/ImpactPage"));
const ReportsPage = lazy(() => import("../features/reports/ReportsPage"));
const SettingsPage = lazy(() => import("../features/settings/SettingsPage"));
const NotFoundPage = lazy(() => import("../features/not-found/NotFoundPage"));

function withSuspense(element: ReactNode): ReactNode {
  return (
    <Suspense
      fallback={
        <div aria-busy="true" className="space-y-3">
          <div className="h-8 w-40 animate-pulse rounded bg-subtle" />
          <div className="h-5 w-72 animate-pulse rounded bg-subtle" />
        </div>
      }
    >
      {element}
    </Suspense>
  );
}

export const routes: RouteObject[] = [
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, element: <Navigate to="/today" replace /> },
      { path: "today", element: withSuspense(<TodayPage />) },
      { path: "ask", element: withSuspense(<AskPage />) },
      { path: "home-air", element: withSuspense(<HomeAirPage />) },
      { path: "impact", element: withSuspense(<ImpactPage />) },
      { path: "reports", element: withSuspense(<ReportsPage />) },
      { path: "settings", element: withSuspense(<SettingsPage />) },
      { path: "*", element: withSuspense(<NotFoundPage />) },
    ],
  },
];

export function createAppRouter() {
  return createBrowserRouter(routes);
}
