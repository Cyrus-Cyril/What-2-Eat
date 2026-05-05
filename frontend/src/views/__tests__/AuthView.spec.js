import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import AuthView from '../AuthView.vue'

const push = vi.fn()

vi.mock('vue-router', () => ({
  useRouter: () => ({
    push,
  }),
}))

vi.mock('@/services/auth', () => ({
  loginUser: vi.fn(),
  registerUser: vi.fn(),
}))

describe('AuthView', () => {
  it('renders auth tabs and register action', async () => {
    const wrapper = mount(AuthView)

    expect(wrapper.text()).toContain('登录')
    expect(wrapper.text()).toContain('注册')

    await wrapper.get('button[data-active="false"]').trigger('click')
    expect(wrapper.text()).toContain('偏好标签')
  })
})
