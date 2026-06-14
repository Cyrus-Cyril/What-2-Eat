<script setup>
/**
 * MapView.vue
 * 高德地图组件：展示用户位置 + 推荐餐厅标注
 *
 * Props:
 *   userPosition  { lng, lat }            用户坐标（GCJ-02）
 *   restaurants   RecommendationItem[]    推荐餐厅列表（含 latitude/longitude）
 *   highlightedId string | null           当前高亮的餐厅 restaurant_id
 *
 * Emits:
 *   restaurant-click(restaurantId)        点击地图标注时触发
 */
import { onMounted, onUnmounted, ref, watch } from 'vue'

const props = defineProps({
  userPosition: { type: Object, default: null },   // { lng, lat }
  restaurants:  { type: Array,  default: () => [] },
  highlightedId: { type: String, default: null },
})

const emit = defineEmits(['restaurant-click'])

const mapContainer = ref(null)
const mapReady = ref(false)
const loadError = ref(false)

let _map = null
let _infoWindow = null
let _userMarker = null
let _markers = {}   // restaurant_id → AMap.Marker

// ── AMap 异步加载（全局单例 Promise）──────────────────────
let _loadPromise = null

function _loadAMapScript() {
  if (_loadPromise) return _loadPromise
  if (window.AMap) {
    _loadPromise = Promise.resolve(window.AMap)
    return _loadPromise
  }
  _loadPromise = new Promise((resolve, reject) => {
    const key = import.meta.env.VITE_AMAP_KEY
    if (!key) {
      reject(new Error('VITE_AMAP_KEY 未配置'))
      return
    }
    const callbackName = '__amapOnLoad__'
    window[callbackName] = () => {
      delete window[callbackName]
      resolve(window.AMap)
    }
    const script = document.createElement('script')
    script.src = `https://webapi.amap.com/maps?v=2.0&key=${key}&callback=${callbackName}`
    script.async = true
    script.onerror = () => {
      delete window[callbackName]
      _loadPromise = null
      reject(new Error('高德地图脚本加载失败'))
    }
    document.head.appendChild(script)
  })
  return _loadPromise
}

// ── 计算初始中心点 ─────────────────────────────────────
function _centerCoord() {
  if (props.userPosition) {
    return [props.userPosition.lng, props.userPosition.lat]
  }
  return [114.35968, 30.52878]
}

// ── 初始化地图 ─────────────────────────────────────────
async function _initMap() {
  try {
    const AMap = await _loadAMapScript()
    if (!mapContainer.value) return

    _map = new AMap.Map(mapContainer.value, {
      zoom: 15,
      center: _centerCoord(),
      mapStyle: 'amap://styles/light',
      viewMode: '2D',
    })

    _infoWindow = new AMap.InfoWindow({
      isCustom: true,
      offset: new AMap.Pixel(0, -38),
    })

    _renderUserMarker(AMap)
    _renderAllMarkers(AMap)
    mapReady.value = true
  } catch (e) {
    console.error('[MapView]', e)
    loadError.value = true
  }
}

// ── 用户位置标注 ───────────────────────────────────────
function _renderUserMarker(AMap) {
  if (!_map || !props.userPosition) return
  if (_userMarker) _map.remove(_userMarker)

  _userMarker = new AMap.Marker({
    position: [props.userPosition.lng, props.userPosition.lat],
    content: '<div class="mv-user-dot"><div class="mv-user-pulse"></div></div>',
    offset: new AMap.Pixel(-12, -12),
    zIndex: 300,
    title: '我的位置',
  })
  _map.add(_userMarker)
}

// ── 餐厅标注（全量重绘） ───────────────────────────────
function _renderAllMarkers(AMap) {
  if (!_map) return
  // 清除旧标注
  Object.values(_markers).forEach(m => _map.remove(m))
  _markers = {}

  props.restaurants.forEach((r, idx) => {
    if (!r.latitude || !r.longitude) return
    const isHL = r.restaurant_id === props.highlightedId
    const marker = _createMarker(AMap, r, idx, isHL)
    _map.add(marker)
    _markers[r.restaurant_id] = marker
  })
}

// ── 创建单个餐厅标注 ───────────────────────────────────
function _createMarker(AMap, r, idx, highlighted) {
  const cls = highlighted ? 'mv-dot mv-dot--hl' : 'mv-dot'
  const label = r.restaurant_name.length > 6
    ? r.restaurant_name.slice(0, 5) + '…'
    : r.restaurant_name

  const marker = new AMap.Marker({
    position: [r.longitude, r.latitude],
    content: `<div class="${cls}">
      <span class="mv-dot-num">${idx + 1}</span>
      <div class="mv-dot-label">${label}</div>
    </div>`,
    offset: new AMap.Pixel(-14, -14),
    zIndex: highlighted ? 200 : 100,
  })

  marker.on('click', () => {
    emit('restaurant-click', r.restaurant_id)
    _openInfoWindow(r, marker)
  })
  return marker
}

// ── 信息气泡 ───────────────────────────────────────────
function _openInfoWindow(r, marker) {
  if (!_map || !_infoWindow) return
  const summary = r.explanation?.summary || r.explanation?.ai_speech || ''
  const rating  = r.rating != null ? `⭐ ${r.rating.toFixed(1)}` : ''
  const price   = r.avg_price != null ? `¥${Math.round(r.avg_price)}/人` : ''
  const dist    = r.distance_m != null ? `📍 ${r.distance_m}m` : ''

  _infoWindow.setContent(`
    <div class="mv-popup">
      <button class="mv-popup-close" onclick="this.parentElement.parentElement.style.display='none'">×</button>
      <div class="mv-popup-name">${r.restaurant_name}</div>
      <div class="mv-popup-meta">${[rating, price, dist].filter(Boolean).join('  ·  ')}</div>
      ${summary ? `<div class="mv-popup-summary">${summary}</div>` : ''}
    </div>
  `)
  _infoWindow.open(_map, marker.getPosition())
}

// ── 高亮变化：只重绘受影响的标注 ─────────────────────
function _updateHighlight(AMap, newId, oldId) {
  if (!_map) return

  const rerender = (id) => {
    const r = props.restaurants.find(x => x.restaurant_id === id)
    if (!r || !r.latitude) return
    const idx  = props.restaurants.indexOf(r)
    const isHL = id === newId
    const old  = _markers[id]
    if (old) _map.remove(old)
    const marker = _createMarker(AMap, r, idx, isHL)
    _map.add(marker)
    _markers[id] = marker
    if (isHL) {
      _map.setCenter([r.longitude, r.latitude], true)
      _openInfoWindow(r, marker)
    }
  }

  if (oldId) rerender(oldId)
  if (newId && newId !== oldId) rerender(newId)
  if (!newId && _infoWindow) _infoWindow.close()
}

// ── 生命周期 ───────────────────────────────────────────
onMounted(_initMap)
onUnmounted(() => {
  if (_map) { _map.destroy(); _map = null }
})

// ── 响应式更新 ─────────────────────────────────────────
watch(
  () => props.restaurants,
  async () => {
    if (!mapReady.value) return
    const AMap = await _loadAMapScript()
    _renderAllMarkers(AMap)
    if (props.userPosition) {
      _map.setCenter(_centerCoord())
    }
  },
  { deep: true },
)

watch(
  () => props.highlightedId,
  async (newId, oldId) => {
    if (!mapReady.value) return
    const AMap = await _loadAMapScript()
    _updateHighlight(AMap, newId, oldId)
  },
)
</script>

<template>
  <div class="mv-wrapper">
    <div v-if="loadError" class="mv-error">
      地图加载失败，请检查网络连接
    </div>
    <div v-else ref="mapContainer" class="mv-container" data-testid="map-container"></div>
    <div v-if="!mapReady && !loadError" class="mv-loading">地图加载中…</div>
  </div>
</template>

<style scoped>
.mv-wrapper {
  position: relative;
  width: 100%;
  height: 360px;
  border-radius: 12px;
  overflow: hidden;
  margin-top: 16px;
  background: #f0f0f0;
}

.mv-container {
  width: 100%;
  height: 100%;
}

.mv-loading,
.mv-error {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.9rem;
  color: #888;
}
.mv-error { color: #c0392b; }
</style>

<!-- 地图标注样式（非 scoped，因为 AMap 动态注入 DOM） -->
<style>
/* ── 用户位置 ─────────────────────────── */
.mv-user-dot {
  width: 24px;
  height: 24px;
  background: #ff5722;
  border: 3px solid #fff;
  border-radius: 50%;
  box-shadow: 0 2px 6px rgba(0,0,0,.4);
  position: relative;
}
.mv-user-pulse {
  position: absolute;
  inset: -6px;
  border-radius: 50%;
  background: rgba(255,87,34,.25);
  animation: mv-pulse 1.8s infinite;
}
@keyframes mv-pulse {
  0%   { transform: scale(1);   opacity: .7; }
  100% { transform: scale(2.2); opacity: 0; }
}

/* ── 餐厅标注 ─────────────────────────── */
.mv-dot {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  background: #1976d2;
  border: 2.5px solid #fff;
  border-radius: 50%;
  box-shadow: 0 2px 6px rgba(0,0,0,.35);
  cursor: pointer;
  transition: transform .15s, background .15s;
}
.mv-dot:hover { transform: scale(1.2); }
.mv-dot--hl {
  background: #0d47a1;
  transform: scale(1.3);
  box-shadow: 0 3px 10px rgba(13,71,161,.55);
  z-index: 200;
}
.mv-dot-num {
  color: #fff;
  font-size: 11px;
  font-weight: 700;
  line-height: 1;
}
.mv-dot-label {
  position: absolute;
  top: 32px;
  left: 50%;
  transform: translateX(-50%);
  white-space: nowrap;
  background: rgba(25,118,210,.92);
  color: #fff;
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 4px;
  pointer-events: none;
  box-shadow: 0 1px 4px rgba(0,0,0,.2);
}
.mv-dot--hl .mv-dot-label {
  background: #0d47a1;
  font-weight: 600;
}

/* ── 信息气泡 ─────────────────────────── */
.mv-popup {
  position: relative;
  background: #fff;
  border-radius: 10px;
  padding: 12px 16px 10px;
  min-width: 180px;
  max-width: 260px;
  box-shadow: 0 4px 16px rgba(0,0,0,.2);
  font-family: inherit;
}
.mv-popup-close {
  position: absolute;
  top: 6px;
  right: 8px;
  background: none;
  border: none;
  cursor: pointer;
  font-size: 16px;
  color: #999;
  line-height: 1;
  padding: 0;
}
.mv-popup-close:hover { color: #333; }
.mv-popup-name {
  font-weight: 700;
  font-size: 15px;
  margin-bottom: 4px;
  color: #1a1a1a;
  padding-right: 16px;
}
.mv-popup-meta {
  font-size: 12px;
  color: #555;
  margin-bottom: 6px;
}
.mv-popup-summary {
  font-size: 12px;
  color: #444;
  line-height: 1.5;
  border-top: 1px solid #f0f0f0;
  padding-top: 6px;
}
</style>
