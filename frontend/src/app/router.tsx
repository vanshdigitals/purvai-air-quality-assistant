import { useQuery } from "@tanstack/react-query";
import { lazy, Suspense, type ReactNode } from "react";
import { createBrowserRouter, Navigate, type RouteObject } from "react-router";

import { AppShell } from "../components/AppShell";
import { OnboardingLayout } from "../features/onboarding/OnboardingLayout";
import { ApiError, fetchHousehold } from "../lib/api";

const WelcomePage = lazy(() => import("../features/onboarding/WelcomePage"));
const LocationStepPage = lazy(() => import("../features/onboarding/LocationStepPage"));
const HouseholdStepPage = lazy(() => import("../features/onboarding/HouseholdStepPage"));
const CommuteStepPage = lazy(() => import("../features/onboarding/CommuteStepPage"));

const TodayPage = lazy(() => import("../features/today/TodayPage"));
const PlanPage = lazy(() => import("../features/plan/PlanPage"));
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
        <div aria-busy="true" className="space-y-3 p-6">
          <div className="h-8 w-40 animate-pulse rounded bg-subtle" />
          <div className="h-5 w-72 animate-pulse rounded bg-subtle" />
        </div>
      }
    >
      {element}
    </Suspense>
  );
}

function RootGate() {
  const householdQuery = useQuery({
    queryKey: ["household"],
    queryFn: fetchHousehold,
    retry: false,
  });

  if (householdQuery.isLoading) {
    return (
      <div aria-busy="true" className="mx-auto max-w-[720px] space-y-3 p-8">
        <div className="h-8 w-40 animate-pulse rounded bg-subtle" />
        <div className="h-5 w-72 animate-pulse rounded bg-subtle" />
      </div>
    );
  }

  if (householdQuery.error instanceof ApiError && householdQuery.error.status === 404) {
    return <Navigate to="/welcome" replace />;
  }

  return <Navigate to="/today" replace />;
}

export const routes: RouteObject[] = [
  { path: "/", element: <RootGate /> },
  {
    path: "/welcome",
    element: <OnboardingLayout />,
    children: [
      { index: true, element: withSuspense(<WelcomePage />) },
      { path: "location", element: withSuspense(<LocationStepPage />) },
      { path: "household", element: withSuspense(<HouseholdStepPage />) },
      { path: "commute", element: withSuspense(<CommuteStepPage />) },
    ],
  },
  {
    path: "/",
    element: <AppShell />,
    children: [
      { path: "today", element: withSuspense(<TodayPage />) },
      { path: "plan", element: withSuspense(<PlanPage />) },
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
