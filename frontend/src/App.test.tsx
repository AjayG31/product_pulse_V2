import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { App } from "./App";

describe("application foundation", () => {
  it("renders the minimal ProductPulse shell", () => {
    render(<App />);

    expect(screen.getByText("ProductPulse")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Product quality monitoring" })).toBeVisible();
    expect(screen.getByText(/application shell is ready/i)).toBeVisible();
  });
});

