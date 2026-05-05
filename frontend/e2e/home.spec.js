import { test, expect } from '@playwright/test'

test('renders the main consumer experience', async ({ page }) => {
  await page.goto('/')

  await expect(page.getByRole('heading', { name: '别再纠结午饭和晚饭了' })).toBeVisible()
  await expect(page.getByRole('button', { name: '帮我选吃的' })).toBeVisible()
  await expect(page.getByText('今天想吃点什么')).toBeVisible()
})

test('renders the test workspace on /test', async ({ page }) => {
  await page.goto('/test')

  await expect(page.getByRole('heading', { name: '前后端联调工作台' })).toBeVisible()
  await expect(page.getByRole('button', { name: '获取推荐' })).toBeVisible()
  await expect(page.getByText('推荐参数')).toBeVisible()
})
