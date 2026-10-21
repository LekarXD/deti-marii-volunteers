/** Ordinary UI editing and server persistence; full two-role browser proof is CUA. */
import {expect, test} from '@playwright/test';

test('a fresh applicant edits the real form and reloads a server draft', async ({page, context}) => {
  await page.goto('/apply');
  const firstName = page.locator('#application-firstName');
  await expect(firstName).toBeVisible();
  await firstName.fill('Мария');
  await page.locator('#application-lastName').fill('Проверочная');
  await expect(page.getByRole('status')).toContainText('Черновик сохранён');
  const server = await context.request.get('/api/v1/registration/draft');
  expect(server.status()).toBe(200);
  const draft = await server.json();
  expect(draft.answers.firstName).toBe('Мария');
  expect(draft.answers.lastName).toBe('Проверочная');
  await page.reload();
  await expect(firstName).toHaveValue('Мария');
  await expect(page.locator('#application-lastName')).toHaveValue('Проверочная');
});

test('network failure shows recovery and does not claim a saved draft', async ({page}) => {
  await page.goto('/apply');
  await expect(page.locator('#application-firstName')).toBeVisible();
  await page.route('**/api/v1/registration/draft', async route => {
    if (route.request().method() === 'PUT') await route.abort('failed');
    else await route.continue();
  });
  await page.locator('#application-firstName').fill('Сохраняемая');
  await expect(page.getByRole('alert')).toBeVisible();
  await expect(page.getByRole('status')).toContainText('несохранённые');
  await expect(page.locator('#application-firstName')).toHaveValue('Сохраняемая');
  await page.unroute('**/api/v1/registration/draft');
  await page.getByRole('button', {name: 'Повторить сохранение'}).click();
  await expect(page.getByRole('status')).toContainText('Черновик сохранён');
});

for (const width of [390, 768, 1050, 1440]) {
  test(`application has no horizontal overflow at ${width}px`, async ({page}) => {
    await page.setViewportSize({width, height: 900});
    await page.goto('/apply');
    await expect(page.locator('#application-firstName')).toBeVisible();
    const sizes = await page.evaluate(() => ({scroll: document.documentElement.scrollWidth, viewport: innerWidth}));
    expect(sizes.scroll).toBeLessThanOrEqual(sizes.viewport + 1);
    await expect(page.locator('nav[aria-label="Боковая навигация"]')).toHaveCount(0);
  });
}
