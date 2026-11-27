import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import SettingsPage from "../src/features/settings/SettingsPage";
import { THEME_STORAGE_KEY } from "../src/lib/theme";

describe("SettingsPage ThemeControl", () => {
  it("switches data-theme and persists choice to localStorage via click and arrow keys", async () => {
    const user = userEvent.setup();
    render(<SettingsPage />);

    const group = screen.getByRole("radiogroup", { name: "Theme" });
    expect(group).toBeInTheDocument();

    const darkRadio = screen.getByRole("radio", { name: "Dark" });
    await user.click(darkRadio);

    expect(darkRadio).toHaveAttribute("aria-checked", "true");
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");

    // ArrowLeft from Dark moves to Light
    await user.keyboard("{ArrowLeft}");
    const lightRadio = screen.getByRole("radio", { name: "Light" });
    expect(lightRadio).toHaveAttribute("aria-checked", "true");
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("light");
  });
});
