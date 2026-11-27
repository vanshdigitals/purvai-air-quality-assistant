import { useQuery } from "@tanstack/react-query";
import { FileText, Home, Info, Leaf, Menu, MessageSquare, Settings, Wind, X } from "lucide-react";
import { useEffect, useState, type ComponentType } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router";

import { ApiError, fetchHealth, fetchHousehold } from "../lib/api";
import { applyReduceMotionToDocument, setThemePreference } from "../lib/theme";

interface NavItem {
  to: string;
  label: string;
  icon: ComponentType<{ size?: number; "aria-hidden"?: boolean }>;
}

const PRIMARY_NAV: readonly NavItem[] = [
  { to: "/today", label: "Today", icon: Wind },
  { to: "/ask", label: "Ask", icon: MessageSquare },
  { to: "/home-air", label: "Home Air", icon: Home },
  { to: "/impact", label: "Impact", icon: Leaf },
];

const SECONDARY_NAV: readonly NavItem[] = [
  { to: "/reports", label: "Reports & Data", icon: FileText },
  { to: "/settings", label: "Settings", icon: Settings },
];

export function AppShell() {
  const [openMenuPath, setOpenMenuPath] = useState<string | null>(null);
  const location = useLocation();
  const navigate = useNavigate();
  const menuOpen = openMenuPath === location.pathname;

  const { data: health } = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
  });

  const householdQuery = useQuery({
    queryKey: ["household"],
    queryFn: fetchHousehold,
    retry: false,
  });

  useEffect(() => {
    if (householdQuery.data) {
      setThemePreference(householdQuery.data.settings.theme);
      applyReduceMotionToDocument(householdQuery.data.settings.reduce_motion);
    }
  }, [householdQuery.data]);

  useEffect(() => {
    const err = householdQuery.error;
    if (err instanceof ApiError && err.status === 404 && location.pathname !== "/reports") {
      void navigate("/welcome", { replace: true });
    }
  }, [householdQuery.error, location.pathname, navigate]);

  useEffect(() => {
    if (!menuOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpenMenuPath(null);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [menuOpen]);

  const isDemo = health?.mode === "demo";

  return (
    <div className="min-h-screen bg-bg text-text">
      <a href="#main-content" className="purvai-skip-link">
        Skip to main content
      </a>

      <div className="lg:grid lg:min-h-screen lg:grid-cols-[232px_1fr]">
        {/* Desktop Sidebar (>= 1024px) */}
        <aside className="hidden lg:flex lg:flex-col lg:justify-between lg:border-r lg:border-border lg:bg-surface lg:px-4 lg:py-6">
          <div className="space-y-6">
            <div className="px-3">
              <span className="font-heading text-xl font-semibold tracking-tight text-primary">
                Purvai
              </span>
              <p className="mt-1 text-xs text-muted">Know the air. Act in time.</p>
            </div>

            <nav aria-label="Primary" className="space-y-1">
              {PRIMARY_NAV.map((item) => {
                const Icon = item.icon;
                return (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    className="purvai-nav-link gap-3 px-3 text-sm"
                  >
                    <Icon size={20} aria-hidden />
                    <span>{item.label}</span>
                  </NavLink>
                );
              })}
            </nav>
          </div>

          <nav aria-label="Workspace" className="space-y-1 border-t border-border pt-4">
            {SECONDARY_NAV.map((item) => {
              const Icon = item.icon;
              return (
                <NavLink key={item.to} to={item.to} className="purvai-nav-link gap-3 px-3 text-sm">
                  <Icon size={20} aria-hidden />
                  <span>{item.label}</span>
                </NavLink>
              );
            })}
          </nav>
        </aside>

        <div className="flex min-h-screen min-w-0 flex-col">
          {/* Top Header */}
          <header className="border-b border-border bg-surface">
            <div className="mx-auto flex max-w-[1120px] items-center justify-between px-4 py-3 lg:px-8">
              <div className="flex items-center gap-2 lg:hidden">
                <span className="font-heading text-lg font-semibold tracking-tight text-primary">
                  Purvai
                </span>
              </div>

              <p className="hidden text-sm text-text-2 lg:block">Know the air. Act in time.</p>

              <div className="relative lg:hidden">
                <button
                  type="button"
                  aria-expanded={menuOpen}
                  aria-controls="mobile-profile-menu"
                  aria-label="Reports and settings menu"
                  onClick={() =>
                    setOpenMenuPath((prev) =>
                      prev === location.pathname ? null : location.pathname
                    )
                  }
                  className="purvai-btn purvai-btn-ghost min-w-[44px] px-2"
                >
                  {menuOpen ? <X size={20} aria-hidden /> : <Menu size={20} aria-hidden />}
                  <span className="text-sm">Menu</span>
                </button>

                {menuOpen && (
                  <nav
                    id="mobile-profile-menu"
                    aria-label="Account and workspace"
                    className="purvai-card absolute right-0 top-12 z-40 w-56 p-2"
                  >
                    {SECONDARY_NAV.map((item) => {
                      const Icon = item.icon;
                      return (
                        <NavLink
                          key={item.to}
                          to={item.to}
                          className="purvai-nav-link gap-3 px-3 text-sm"
                        >
                          <Icon size={20} aria-hidden />
                          <span>{item.label}</span>
                        </NavLink>
                      );
                    })}
                  </nav>
                )}
              </div>
            </div>

            {isDemo && (
              <div
                role="status"
                className="border-t border-border bg-info-tint px-4 py-2 text-sm text-info lg:px-8"
              >
                <div className="mx-auto flex max-w-[1120px] items-center gap-2">
                  <Info size={18} aria-hidden />
                  <span>Demo data resets. Export to keep it.</span>
                </div>
              </div>
            )}
          </header>

          {/* Main Content */}
          <main
            id="main-content"
            tabIndex={-1}
            className="mx-auto w-full max-w-[1120px] flex-1 px-4 py-6 pb-24 lg:px-8 lg:py-8 lg:pb-8"
          >
            <Outlet />
          </main>
        </div>
      </div>

      {/* Mobile Bottom Navigation (< 1024px) */}
      <nav
        aria-label="Mobile navigation"
        className="fixed inset-x-0 bottom-0 z-30 flex h-[68px] items-center justify-around border-t border-border bg-surface px-2 lg:hidden"
      >
        {PRIMARY_NAV.map((item) => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.to}
              to={item.to}
              className="purvai-nav-link flex-1 flex-col justify-center gap-1 px-2 py-1 text-xs"
            >
              <Icon size={20} aria-hidden />
              <span>{item.label}</span>
            </NavLink>
          );
        })}
      </nav>
    </div>
  );
}
