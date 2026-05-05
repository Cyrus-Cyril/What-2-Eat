import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import ProfileView from '../ProfileView.vue'

const push = vi.fn()

vi.mock('vue-router', () => ({
  RouterLink: {
    template: '<a><slot /></a>',
  },
  useRouter: () => ({
    push,
  }),
}))

vi.mock('@/services/auth', () => ({
  authState: {
    currentUser: {
      nickname: '小宇',
      gender: '男',
      age: 22,
      preference_json: ['川菜'],
      budget_preference_min: 20,
      budget_preference_max: 60,
      distance_preference: 1800,
      spicy_preference: 0.8,
      sweet_preference: 0.3,
      healthy_preference: 0.4,
    },
  },
  updateCurrentUserProfile: vi.fn(),
}))

describe('ProfileView', () => {
  it('renders profile editor fields', () => {
    const wrapper = mount(ProfileView)

    expect(wrapper.text()).toContain('调整你的当前偏好')
    expect(wrapper.text()).toContain('偏好标签')
    expect(wrapper.text()).toContain('保存当前偏好')
  })
})
