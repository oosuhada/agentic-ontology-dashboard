import { expect, test } from "@playwright/test";

test("a stalled session check returns /app visitors to sign in", async ({ page }) => {
  await page.route("**/api/auth/me", async () => {
    await new Promise((resolve) => setTimeout(resolve, 10_000));
  });

  await page.goto("/app");
  await expect(page.getByRole("status", { name: "Checking session" })).toBeVisible();
  await expect(page).toHaveURL(/\/login$/, { timeout: 8_000 });
  await expect(page.getByRole("button", { name: "로그인" })).toBeVisible();
});
