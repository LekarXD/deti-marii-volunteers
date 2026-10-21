/** Ordinary UI editing and server persistence; full two-role browser proof is CUA. */
import {expect, test, type Page} from '@playwright/test';
import {execFileSync} from 'node:child_process';
import {randomUUID} from 'node:crypto';
import {resolve} from 'node:path';

/** Read only the locally issued proof; no inbox endpoint or synthetic session. */
function issuedRegistrationCode(email: string, challengeId: string): string {
  const apiDir=process.env.OPORA_G1_API_DIR || resolve(__dirname,'../../apps/api');
  const python=process.env.OPORA_G1_PYTHON || (process.env.VIRTUAL_ENV ? `${process.env.VIRTUAL_ENV}/bin/python` : 'python3');
  const inbox=JSON.parse(execFileSync(python,['-m','app.cli','dev-inbox','--email',email],{cwd:apiDir,encoding:'utf8',stdio:['ignore','pipe','pipe']}));
  const code=inbox.find((row:{challenge_id?:string})=>row.challenge_id===challengeId)?.code;
  if(typeof code!=='string'||!/^[0-9]{6}$/.test(code))throw new Error('The local inbox must contain the issued registration proof');
  return code;
}

async function verifyBeforeQuestionnaire(page: Page) {
  const email=`g1-browser-${randomUUID()}@example.test`;
  await page.goto('/apply');
  await expect(page).toHaveURL(/\/register$/);
  await expect(page.locator('#application-firstName')).toHaveCount(0);
  await page.getByLabel('Электронная почта',{exact:true}).fill(email);
  await page.getByLabel('Придумайте пароль',{exact:true}).fill(`G1-password-${randomUUID()}`);
  const registration=page.waitForResponse(response=>new URL(response.url()).pathname.endsWith('/api/v1/auth/register')&&response.request().method()==='POST');
  await page.getByRole('button',{name:'Продолжить',exact:true}).click();
  const response=await registration;
  expect(response.ok()).toBe(true);
  const challenge=await response.json();
  const demo=challenge.demo_code_allowed===true;
  const code=demo?'любой код':issuedRegistrationCode(email,challenge.challenge_id);
  await page.getByLabel(demo?'Код подтверждения':'Код из письма',{exact:true}).fill(code);
  await page.getByRole('button',{name:'Подтвердить почту',exact:true}).click();
  await expect(page).toHaveURL(/\/apply$/);
  await expect(page.locator('#application-firstName')).toBeVisible();
  await expect(page.locator('#application-email')).toHaveValue(email);
  await expect(page.locator('#application-email')).toHaveAttribute('readonly','');
  await expect(page.getByRole('button',{name:'Аккаунт',exact:true})).toBeVisible();
  const session=await (await page.context().request.get('/api/v1/auth/session')).json();
  expect(session.user_id).toBeTruthy();
  expect(session.verified_email).toBe(email);
  return email;
}

test('a fresh applicant edits the real form and reloads a server draft', async ({page, context}) => {
  const email=await verifyBeforeQuestionnaire(page);
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
  expect(draft.answers.email).toBe(email);
  await page.reload();
  await expect(firstName).toHaveValue('Мария');
  await expect(page.locator('#application-lastName')).toHaveValue('Проверочная');
  await expect(page.locator('#application-email')).toHaveValue(email);
  await expect(page.getByRole('button',{name:'Аккаунт',exact:true})).toBeVisible();
});

test('network failure shows recovery and does not claim a saved draft', async ({page}) => {
  await verifyBeforeQuestionnaire(page);
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
    await verifyBeforeQuestionnaire(page);
    await expect(page.locator('#application-firstName')).toBeVisible();
    const sizes = await page.evaluate(() => ({scroll: document.documentElement.scrollWidth, viewport: innerWidth}));
    expect(sizes.scroll).toBeLessThanOrEqual(sizes.viewport + 1);
    await expect(page.locator('nav[aria-label="Боковая навигация"]')).toHaveCount(0);
  });
}
