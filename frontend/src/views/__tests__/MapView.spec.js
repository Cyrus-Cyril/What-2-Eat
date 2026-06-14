/**
 * MapView.spec.js
 * MapView.vue 单元测试 —— mock 高德 AMap，验证核心渲染与交互行为
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import MapView from '../MapView.vue'

// ── Mock AMap ──────────────────────────────────────────
const mockMarker = {
  _handlers: {},
  on(event, fn) { this._handlers[event] = fn },
  setMap: vi.fn(),
  getPosition: vi.fn(() => [114.36, 30.53]),
}
const mockInfoWindow = {
  setContent: vi.fn(),
  open: vi.fn(),
  close: vi.fn(),
}
const mockMap = {
  add: vi.fn(),
  remove: vi.fn(),
  setCenter: vi.fn(),
  destroy: vi.fn(),
}

const AMapMock = {
  Map: vi.fn(() => mockMap),
  Marker: vi.fn(() => ({ ...mockMarker, _handlers: {}, on: vi.fn(), setMap: vi.fn(), getPosition: vi.fn(() => [114.36, 30.53]) })),
  InfoWindow: vi.fn(() => mockInfoWindow),
  Pixel: vi.fn((x, y) => ({ x, y })),
}

// 在 window 注入 AMap，模拟脚本加载成功
beforeEach(() => {
  window.AMap = AMapMock
  vi.clearAllMocks()
})

afterEach(() => {
  delete window.AMap
})

const userPosition = { lng: 114.35968, lat: 30.52878 }

const restaurants = [
  {
    restaurant_id: 'R001',
    restaurant_name: '川香小馆',
    latitude: 30.531,
    longitude: 114.361,
    rating: 4.5,
    avg_price: 45,
    distance_m: 350,
    explanation: { summary: '口碑极佳，步行可达' },
  },
  {
    restaurant_id: 'R002',
    restaurant_name: '老北京涮肉',
    latitude: 30.527,
    longitude: 114.357,
    rating: 4.2,
    avg_price: 68,
    distance_m: 680,
    explanation: { summary: '人均适中，评分较高' },
  },
]

describe('MapView.vue', () => {
  it('挂载后渲染 map-container', async () => {
    const wrapper = mount(MapView, {
      props: { userPosition, restaurants, highlightedId: null },
    })
    await flushPromises()
    expect(wrapper.find('[data-testid="map-container"]').exists()).toBe(true)
  })

  it('初始化时创建 AMap.Map 实例', async () => {
    mount(MapView, {
      props: { userPosition, restaurants, highlightedId: null },
    })
    await flushPromises()
    expect(AMapMock.Map).toHaveBeenCalledTimes(1)
  })

  it('为每个有坐标的餐厅创建 Marker', async () => {
    mount(MapView, {
      props: { userPosition, restaurants, highlightedId: null },
    })
    await flushPromises()
    // +1 for user marker
    expect(AMapMock.Marker.mock.calls.length).toBeGreaterThanOrEqual(restaurants.length)
  })

  it('高亮餐厅变化时重新渲染对应标注', async () => {
    const wrapper = mount(MapView, {
      props: { userPosition, restaurants, highlightedId: null },
    })
    await flushPromises()

    const prevCalls = AMapMock.Marker.mock.calls.length
    await wrapper.setProps({ highlightedId: 'R001' })
    await flushPromises()
    // 应该新建了至少一个标注（高亮重绘）
    expect(AMapMock.Marker.mock.calls.length).toBeGreaterThan(prevCalls)
  })

  it('点击标注时 emit restaurant-click 事件', async () => {
    let clickHandler = null
    AMapMock.Marker = vi.fn(() => {
      const m = {
        _clickFn: null,
        on(evt, fn) { if (evt === 'click') m._clickFn = fn },
        setMap: vi.fn(),
        getPosition: vi.fn(() => [114.36, 30.53]),
      }
      if (!clickHandler) clickHandler = m
      return m
    })

    const wrapper = mount(MapView, {
      props: { userPosition, restaurants, highlightedId: null },
    })
    await flushPromises()

    // 触发第一个餐厅的点击
    if (clickHandler?._clickFn) clickHandler._clickFn()

    expect(wrapper.emitted('restaurant-click')).toBeTruthy()
  })

  it('没有坐标的餐厅不创建 Marker', async () => {
    const noCoordRestaurants = [
      { restaurant_id: 'RX', restaurant_name: '无坐标', latitude: null, longitude: null },
    ]
    AMapMock.Marker = vi.fn(() => ({
      on: vi.fn(), setMap: vi.fn(), getPosition: vi.fn(),
    }))

    mount(MapView, {
      props: { userPosition, restaurants: noCoordRestaurants, highlightedId: null },
    })
    await flushPromises()
    // 只有 user marker（1个）不会为无坐标餐厅创建
    expect(AMapMock.Marker.mock.calls.length).toBeLessThanOrEqual(1)
  })

  it('VITE_AMAP_KEY 未配置时显示加载错误（模拟脚本加载失败）', async () => {
    delete window.AMap
    // 注入一个会立刻失败的 script（onerror）
    const origCreate = document.createElement.bind(document)
    vi.spyOn(document, 'createElement').mockImplementation((tag) => {
      const el = origCreate(tag)
      if (tag === 'script') {
        // 在下一 tick 触发 onerror
        setTimeout(() => el.onerror?.(new Error('fail')), 0)
      }
      return el
    })

    const wrapper = mount(MapView, {
      props: { userPosition, restaurants, highlightedId: null },
    })
    await flushPromises()

    expect(wrapper.find('.mv-error').exists()).toBe(true)
    vi.restoreAllMocks()
  })
})
