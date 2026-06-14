import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import HomeView from '../HomeView.vue'

// ── Mock AMap（避免测试中实际加载 JS SDK）────────────────
const AMapMock = {
  Map: vi.fn(() => ({ add: vi.fn(), remove: vi.fn(), setCenter: vi.fn(), destroy: vi.fn() })),
  Marker: vi.fn(() => ({ on: vi.fn(), setMap: vi.fn(), getPosition: vi.fn(() => [114.36, 30.53]) })),
  InfoWindow: vi.fn(() => ({ setContent: vi.fn(), open: vi.fn(), close: vi.fn() })),
  Pixel: vi.fn((x, y) => ({ x, y })),
}
vi.stubGlobal('AMap', AMapMock)

vi.mock('@/services/api', () => ({
  fetchRecommendations: vi.fn().mockResolvedValue({
    message: 'ok',
    result_id: null,
    explanation_system: {
      hello_voice: '好嘞！给你找了几家口碑不错的。',
      welcome_narrative: '今晚可以优先看看这几家。',
      structured_context: {
        intent_mode: 'Scene B',
        core_tags: ['川菜'],
      },
    },
    recommendations: [
      {
        restaurant_id: 'R001',
        restaurant_name: '川香小馆',
        latitude: 30.531,
        longitude: 114.361,
        rating: 4.5,
        avg_price: 45,
        distance_m: 350,
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
  fetchSpeeches: vi.fn().mockResolvedValue({
    code: 1,
    message: '尚未就绪',
    speeches: [],
  }),
  fetchPresetRecommendations: vi.fn().mockResolvedValue({
    code: 0,
    recommendations: [
      {
        id: 'r001',
        name: '渝味火锅城',
        category: '火锅',
        tags: ['火锅', '中餐', '辣'],
        avg_price: 58,
        rating: 4.7,
        reason: '麻辣风味稳定，适合朋友一起吃。',
        shared_tags: ['火锅'],
        score: 0.95,
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
  it('renders user-facing homepage sections after submit', async () => {
    const wrapper = mount(HomeView, {
      global: {
        stubs: ['RouterLink'],
      },
    })

    await wrapper.get('form').trigger('submit.prevent')
    await flushPromises()

    expect(wrapper.text()).toContain('今天吃什么')
    expect(wrapper.text()).toContain('渝味火锅城')
    expect(wrapper.text()).toContain('川香小馆')
    expect(wrapper.text()).not.toContain('ok')
  })

  it('提交后显示地图组件（MapView）', async () => {
    const wrapper = mount(HomeView, {
      global: { stubs: ['RouterLink'] },
    })

    // 提交前不显示地图
    expect(wrapper.find('[data-testid="map-view"]').exists()).toBe(false)

    await wrapper.get('form').trigger('submit.prevent')
    await flushPromises()

    // 提交后有推荐结果，地图应出现
    expect(wrapper.find('[data-testid="map-view"]').exists()).toBe(true)
  })

  it('卡片 mouseenter 设置 highlightedId，mouseleave 清除', async () => {
    const wrapper = mount(HomeView, {
      global: { stubs: ['RouterLink'] },
    })

    await wrapper.get('form').trigger('submit.prevent')
    await flushPromises()

    const card = wrapper.find('.consumer-result-card')
    expect(card.exists()).toBe(true)

    await card.trigger('mouseenter')
    expect(card.attributes('data-highlighted')).toBe('true')

    await card.trigger('mouseleave')
    expect(card.attributes('data-highlighted')).toBe('false')
  })

  it('地图标注点击事件（restaurant-click）高亮对应卡片', async () => {
    const wrapper = mount(HomeView, {
      global: { stubs: ['RouterLink'] },
    })

    await wrapper.get('form').trigger('submit.prevent')
    await flushPromises()

    // 模拟地图组件发出 restaurant-click 事件
    const mapView = wrapper.findComponent({ name: 'MapView' })
    expect(mapView.exists()).toBe(true)

    await mapView.vm.$emit('restaurant-click', 'R001')
    await flushPromises()

    const card = wrapper.find('.consumer-result-card[data-highlighted="true"]')
    expect(card.exists()).toBe(true)
  })
})
