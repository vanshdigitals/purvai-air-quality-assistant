import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, Check, LocateFixed, Search } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { useNavigate, useOutletContext, useSearchParams } from "react-router";

import {
  ApiError,
  fetchHousehold,
  saveHousehold,
  searchLocations,
  type GeocodingResult,
  type LocationPayload,
} from "../../lib/api";
import { getStoredReduceMotion, getStoredTheme } from "../../lib/theme";
import { OnboardingFrame, type OnboardingOutletContext } from "./OnboardingLayout";

export default function LocationStepPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const fromSettings = searchParams.get("from") === "settings";
  const queryClient = useQueryClient();
  const { draft, setDraft } = useOutletContext<OnboardingOutletContext>();

  const existingHousehold = useQuery({
    queryKey: ["household"],
    queryFn: fetchHousehold,
    enabled: fromSettings,
    retry: false,
  });

  const headingRef = useRef<HTMLHeadingElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);

  const [queryText, setQueryText] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [selected, setSelected] = useState<LocationPayload | null>(draft.location);
  const [geoMessage, setGeoMessage] = useState<string | null>(null);
  const [manualOverride, setManualOverride] = useState<boolean | null>(null);
  const [manualLabel, setManualLabel] = useState("");
  const [manualLat, setManualLat] = useState("");
  const [manualLon, setManualLon] = useState("");
  const [manualError, setManualError] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);

  useEffect(() => {
    headingRef.current?.focus();
  }, []);

  useEffect(() => {
    const trimmed = queryText.trim();
    if (trimmed.length < 2) {
      return;
    }
    const timer = window.setTimeout(() => {
      setDebouncedQuery(trimmed);
    }, 300);
    return () => window.clearTimeout(timer);
  }, [queryText]);

  const activeQuery = queryText.trim().length >= 2 ? debouncedQuery : "";

  const searchQuery = useQuery({
    queryKey: ["locations", "search", activeQuery],
    queryFn: () => searchLocations(activeQuery),
    enabled: activeQuery.length >= 2,
    retry: false,
  });

  const showManual = manualOverride ?? searchQuery.isError;

  const saveMutation = useMutation({
    mutationFn: saveHousehold,
    onSuccess: (saved) => {
      queryClient.setQueryData(["household"], saved);
      void navigate(fromSettings ? "/settings" : "/today", { replace: true });
    },
    onError: (err) => {
      setSubmitError(err instanceof Error ? err.message : "Could not save location.");
    },
  });

  const handleUseMyLocation = () => {
    setGeoMessage(null);
    if (!("geolocation" in navigator)) {
      setGeoMessage("Location access is unavailable in this browser. Search for your city below.");
      searchInputRef.current?.focus();
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const lat = Number(pos.coords.latitude.toFixed(4));
        const lon = Number(pos.coords.longitude.toFixed(4));
        const loc: LocationPayload = {
          label: `Current location (${lat.toFixed(2)}, ${lon.toFixed(2)})`,
          lat,
          lon,
          city: null,
          admin1: null,
          admin2: null,
        };
        setSelected(loc);
        setDraft((prev) => ({ ...prev, location: loc }));
      },
      () => {
        setGeoMessage("Location permission was denied. Search for your city or area below.");
        searchInputRef.current?.focus();
      },
      { timeout: 10000 }
    );
  };

  const handleSelectResult = (item: GeocodingResult) => {
    const loc: LocationPayload = {
      label: item.label,
      lat: item.lat,
      lon: item.lon,
      city: item.city,
      admin1: item.admin1,
      admin2: item.admin2,
    };
    setSelected(loc);
    setDraft((prev) => ({ ...prev, location: loc }));
    setSubmitError(null);
  };

  const handleManualApply = (event: FormEvent) => {
    event.preventDefault();
    setManualError(null);
    const lat = Number(manualLat);
    const lon = Number(manualLon);
    if (!manualLabel.trim()) {
      setManualError("Enter a location label.");
      return;
    }
    if (
      !Number.isFinite(lat) ||
      lat < 6 ||
      lat > 38 ||
      !Number.isFinite(lon) ||
      lon < 68 ||
      lon > 98
    ) {
      setManualError("Purvai currently supports coordinates in India (lat 6 to 38, lon 68 to 98).");
      return;
    }
    const loc: LocationPayload = {
      label: manualLabel.trim().slice(0, 60),
      lat: Number(lat.toFixed(4)),
      lon: Number(lon.toFixed(4)),
      city: null,
      admin1: null,
      admin2: null,
    };
    setSelected(loc);
    setDraft((prev) => ({ ...prev, location: loc }));
  };

  const handleContinue = () => {
    if (!selected) return;
    setDraft((prev) => ({ ...prev, location: selected }));
    if (fromSettings && existingHousehold.data) {
      saveMutation.mutate({
        members: existingHousehold.data.members,
        location: selected,
        settings: existingHousehold.data.settings,
      });
      return;
    }
    void navigate("/welcome/household");
  };

  const handleSkip = () => {
    if (!selected) return;
    saveMutation.mutate({
      members: [{ kind: "adult", count: 1 }],
      location: selected,
      settings: {
        theme: getStoredTheme(),
        commute_mode: "metro",
        ai_enabled: true,
        save_chat: false,
        reduce_motion: getStoredReduceMotion(),
      },
    });
  };

  const searchErrorMessage =
    searchQuery.error instanceof ApiError && searchQuery.error.code === "RATE_LIMIT_EXCEEDED"
      ? searchQuery.error.message
      : "Location search is unavailable. Enter coordinates manually below.";

  return (
    <OnboardingFrame step={fromSettings ? 1 : 2} totalSteps={fromSettings ? 1 : 4}>
      <div className="space-y-6">
        <div className="space-y-2">
          <h1 ref={headingRef} tabIndex={-1} className="outline-none">
            {fromSettings ? "Change primary location" : "Where are you checking air quality?"}
          </h1>
          <p className="text-text-2">
            Use GPS or search for an Indian city or neighbourhood. Coordinates are rounded before
            caching.
          </p>
        </div>

        <div className="purvai-card space-y-5 p-6">
          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={handleUseMyLocation}
              className="purvai-btn purvai-btn-secondary"
            >
              <LocateFixed size={18} aria-hidden />
              <span>Use my location</span>
            </button>

            <button
              type="button"
              onClick={() => setManualOverride(!showManual)}
              className="purvai-btn purvai-btn-ghost"
            >
              {showManual ? "Hide manual coordinates" : "Enter coordinates manually"}
            </button>
          </div>

          {geoMessage && (
            <p role="status" className="rounded-[6px] bg-info-tint px-3 py-2 text-sm text-info">
              {geoMessage}
            </p>
          )}

          <div className="space-y-1.5">
            <label htmlFor="location-search" className="block text-sm font-medium text-text">
              Search city or neighbourhood
            </label>
            <div className="relative">
              <Search
                size={18}
                aria-hidden
                className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted"
              />
              <input
                ref={searchInputRef}
                id="location-search"
                type="search"
                value={queryText}
                onChange={(e) => {
                  const next = e.target.value;
                  setQueryText(next);
                  if (next.trim().length < 2) {
                    setDebouncedQuery("");
                  }
                }}
                placeholder="Type at least 2 characters, e.g. Noida"
                className="purvai-input pl-10"
              />
            </div>
          </div>

          {searchQuery.isFetching && (
            <p aria-live="polite" className="text-sm text-muted">
              Searching locations...
            </p>
          )}

          {searchQuery.isError && (
            <div
              role="alert"
              className="flex items-start gap-2 rounded-[6px] border border-danger bg-danger-tint p-3 text-sm text-danger"
            >
              <AlertCircle size={18} className="mt-0.5 shrink-0" aria-hidden />
              <span>{searchErrorMessage}</span>
            </div>
          )}

          {searchQuery.data && searchQuery.data.length === 0 && activeQuery.length >= 2 && (
            <p className="text-sm text-text-2">
              No matching places found in India. Try another name or enter coordinates manually.
            </p>
          )}

          {searchQuery.data && searchQuery.data.length > 0 && (
            <div role="radiogroup" aria-label="Search results" className="space-y-2">
              {searchQuery.data.map((item) => {
                const isSelected =
                  selected?.label === item.label &&
                  selected?.lat === item.lat &&
                  selected?.lon === item.lon;
                return (
                  <button
                    key={`${item.label}-${item.lat}-${item.lon}`}
                    type="button"
                    role="radio"
                    aria-checked={isSelected}
                    data-selected={isSelected}
                    onClick={() => handleSelectResult(item)}
                    className="purvai-choice-card w-full text-left"
                  >
                    <div>
                      <div className="font-medium text-text">{item.label}</div>
                      <div className="tabular-data text-xs text-muted">
                        {item.lat.toFixed(4)}, {item.lon.toFixed(4)}
                        {item.nearest_station_km !== null
                          ? ` · Nearest CPCB station ${item.nearest_station_km} km`
                          : ""}
                      </div>
                    </div>
                    {isSelected && (
                      <Check size={18} className="shrink-0 text-primary" aria-hidden />
                    )}
                  </button>
                );
              })}
            </div>
          )}

          {showManual && (
            <form onSubmit={handleManualApply} className="space-y-4 border-t border-border pt-4">
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                <div>
                  <label htmlFor="manual-label" className="mb-1 block text-sm font-medium">
                    Place label
                  </label>
                  <input
                    id="manual-label"
                    type="text"
                    value={manualLabel}
                    onChange={(e) => setManualLabel(e.target.value)}
                    placeholder="Sector 62, Noida"
                    className="purvai-input"
                  />
                </div>
                <div>
                  <label htmlFor="manual-lat" className="mb-1 block text-sm font-medium">
                    Latitude
                  </label>
                  <input
                    id="manual-lat"
                    type="number"
                    step="0.0001"
                    value={manualLat}
                    onChange={(e) => setManualLat(e.target.value)}
                    placeholder="28.6271"
                    className="purvai-input tabular-data"
                  />
                </div>
                <div>
                  <label htmlFor="manual-lon" className="mb-1 block text-sm font-medium">
                    Longitude
                  </label>
                  <input
                    id="manual-lon"
                    type="number"
                    step="0.0001"
                    value={manualLon}
                    onChange={(e) => setManualLon(e.target.value)}
                    placeholder="77.3716"
                    className="purvai-input tabular-data"
                  />
                </div>
              </div>
              {manualError && (
                <p role="alert" className="text-sm text-danger">
                  {manualError}
                </p>
              )}
              <button type="submit" className="purvai-btn purvai-btn-secondary">
                Use these coordinates
              </button>
            </form>
          )}

          {selected && (
            <div className="rounded-[6px] border border-selected-border bg-selected px-4 py-3 text-sm">
              <span className="font-medium">Selected:</span> {selected.label}{" "}
              <span className="tabular-data text-text-2">
                ({selected.lat.toFixed(4)}, {selected.lon.toFixed(4)})
              </span>
            </div>
          )}

          {submitError && (
            <p role="alert" className="text-sm text-danger">
              {submitError}
            </p>
          )}

          <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
            <div className="flex flex-wrap items-center gap-3">
              <button
                type="button"
                disabled={!selected || saveMutation.isPending}
                onClick={handleContinue}
                className="purvai-btn purvai-btn-primary"
              >
                {fromSettings ? "Save location" : "Continue"}
              </button>

              {!fromSettings && selected && (
                <button
                  type="button"
                  disabled={saveMutation.isPending}
                  onClick={handleSkip}
                  className="purvai-btn purvai-btn-ghost"
                >
                  Skip for now
                </button>
              )}
            </div>

            <button
              type="button"
              onClick={() => {
                void navigate(fromSettings ? "/settings" : "/welcome");
              }}
              className="purvai-btn purvai-btn-secondary"
            >
              Back
            </button>
          </div>
        </div>
      </div>
    </OnboardingFrame>
  );
}
