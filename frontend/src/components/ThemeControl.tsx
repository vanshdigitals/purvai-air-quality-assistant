import { useRef, type KeyboardEvent } from "react";

import type { ThemeChoice } from "../lib/theme";

interface ThemeOption {
  value: ThemeChoice;
  label: string;
}

const OPTIONS: readonly ThemeOption[] = [
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
  { value: "system", label: "System" },
];

interface ThemeControlProps {
  value: ThemeChoice;
  onChange: (choice: ThemeChoice) => void;
}

export function ThemeControl({ value, onChange }: ThemeControlProps) {
  const buttonRefs = useRef<Array<HTMLButtonElement | null>>([]);

  const handleKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    let nextIndex: number | null = null;
    if (event.key === "ArrowRight" || event.key === "ArrowDown") {
      nextIndex = (index + 1) % OPTIONS.length;
    } else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
      nextIndex = (index - 1 + OPTIONS.length) % OPTIONS.length;
    } else if (event.key === "Home") {
      nextIndex = 0;
    } else if (event.key === "End") {
      nextIndex = OPTIONS.length - 1;
    }

    if (nextIndex !== null) {
      event.preventDefault();
      const target = OPTIONS[nextIndex];
      if (target) {
        onChange(target.value);
        buttonRefs.current[nextIndex]?.focus();
      }
    }
  };

  return (
    <div
      role="radiogroup"
      aria-label="Theme"
      className="inline-flex flex-wrap gap-1 rounded-[10px] border border-border bg-subtle p-1"
    >
      {OPTIONS.map((option, index) => {
        const isSelected = value === option.value;
        return (
          <button
            key={option.value}
            ref={(el) => {
              buttonRefs.current[index] = el;
            }}
            type="button"
            role="radio"
            aria-checked={isSelected}
            tabIndex={isSelected ? 0 : -1}
            onClick={() => onChange(option.value)}
            onKeyDown={(event) => handleKeyDown(event, index)}
            className="purvai-segment"
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
