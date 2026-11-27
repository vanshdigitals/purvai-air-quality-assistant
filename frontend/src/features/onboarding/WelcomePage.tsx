import { ArrowRight, ShieldCheck, Wind } from "lucide-react";
import { useNavigate } from "react-router";

import { OnboardingFrame } from "./OnboardingLayout";

export default function WelcomePage() {
  const navigate = useNavigate();

  return (
    <OnboardingFrame step={1}>
      <section className="purvai-verdict-hero space-y-6 p-6 sm:p-8">
        <div className="inline-flex items-center gap-2 rounded-full border border-border bg-surface px-3 py-1 text-xs font-medium text-text-2">
          <Wind size={16} aria-hidden />
          <span>Know the air. Act in time.</span>
        </div>

        <h1>Clear air-safety actions for your household</h1>

        <p className="text-text-2">
          Purvai turns official CPCB station readings and modelled CAMS air data into a clear daily
          plan, tailored to who lives in your home.
        </p>

        <ul className="space-y-3 text-sm text-text-2">
          <li className="flex items-start gap-2.5">
            <ShieldCheck size={18} className="mt-0.5 shrink-0 text-accent" aria-hidden />
            <span>Deterministic safety rules decide every verdict. No accounts required.</span>
          </li>
          <li className="flex items-start gap-2.5">
            <ShieldCheck size={18} className="mt-0.5 shrink-0 text-accent" aria-hidden />
            <span>Setup takes under 60 seconds and you can skip optional steps.</span>
          </li>
        </ul>

        <div className="pt-2">
          <button
            type="button"
            onClick={() => {
              void navigate("/welcome/location");
            }}
            className="purvai-btn purvai-btn-primary"
          >
            <span>Get started</span>
            <ArrowRight size={18} aria-hidden />
          </button>
        </div>
      </section>
    </OnboardingFrame>
  );
}
