import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import HomeView from '../HomeView.vue'

vi.mock('@/services/api', () => ({
  fetchRecommendations: vi.fn().mockResolvedValue({
    message: 'ok',
    explanation_system: {
      welcome_narrative: '已根据你的需求生成推荐。',
      structured_context: {
        intent_mode: 'Scene B',
        core_tags: ['川菜'],
      },
    },
    recommendations: [
      {
        restaurant_id: 'R001',
        restaurant_name: '川香小馆',
        explanation: {
          summary: '口味匹配度高',
          reasoning_logic: {
            primary_factor: '川菜偏好命中',
            secondary_factor: '距离适中',
          },
          dimension_details: [
            {
              dimension: '口味',
              detail: '符合川菜偏好',
              score_impact: 'high',
            },
          ],
        },
      },
    ],
  }),
}))

vi.mock('@/services/auth', () => ({
  authState: {
    currentUser: {
      id: 'u001',
      username: 'xiaoyu',
      nickname: '小宇',
      preference_json: ['川菜', '火锅'],
      distance_preference: 1800,
    },
  },
  logoutUser: vi.fn(),
}))

vi.mock('@/services/personalization', () => ({
  getPersonalizedRecommendations: () => [
    {
      id: 'r001',
      name: '渝味火锅城',
      category: '火锅',
      sharedTags: ['火锅'],
      avgPrice: 58,
      rating: 4.7,
      reason: '麻辣风味稳定，适合朋友一起吃。',
    },
  ],
}))

describe('HomeView', () => {
  it('renders consumer recommendations after submit', async () => {
    const wrapper = mount(HomeView, {
      global: {
        stubs: ['RouterLink'],
      },
    })

    await wrapper.get('form').trigger('submit.prevent')
    await flushPromises()

    expect(wrapper.text()).toContain('今晚吃什么')
    expect(wrapper.text()).toContain('川香小馆')
    expect(wrapper.text()).toContain('渝味火锅城')
    expect(wrapper.text()).toContain('已根据你的需求生成推荐。')
  })
})
