import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import TestView from '../TestView.vue'

vi.mock('@/services/api', () => ({
  getApiBaseUrl: () => 'http://localhost:8000',
  fetchHealth: vi.fn().mockResolvedValue({
    status: 'ok',
    version: '0.2.0',
  }),
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
          ai_speech: '这家更符合你的口味偏好。',
        },
      },
    ],
  }),
}))

describe('TestView', () => {
  it('renders test workspace and fetched results', async () => {
    const wrapper = mount(TestView, {
      global: {
        stubs: ['RouterLink'],
      },
    })

    await flushPromises()
    await wrapper.get('form').trigger('submit.prevent')
    await flushPromises()

    expect(wrapper.text()).toContain('前后端联调工作台')
    expect(wrapper.text()).toContain('川香小馆')
    expect(wrapper.text()).toContain('已根据你的需求生成推荐。')
  })
})
