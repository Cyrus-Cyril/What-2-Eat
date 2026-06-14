<script setup>
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { fetchRecommendations, fetchSpeeches, submitFeedback, fetchParseIntent } from '@/services/api'
import { authState, logoutUser } from '@/services/auth'
import { getPersonalizedRecommendations } from '@/services/personalization'
import MapView from '@/views/MapView.vue'

const quickIdeas = [
  '想吃热乎一点的',
  '想吃便宜又快的午饭',
  '今天想吃辣的',
  '适合两个人一起吃',
]

const tasteOptions = ['火锅', '烧烤', '日料', '韩餐', '西餐', '快餐', '面食', '东南亚', '咖啡', '奶茶', '饮品']
const budgetOptions = [
  { label: '随意', value: 'any' },
  { label: '30 元内', value: '30' },
  { label: '30-60 元', value: '60' },
  { label: '60 元以上', value: '80+' },
]
const partyOptions = [1, 2, 3, 4, 6]

const form = reactive({
  query: '',
  taste: '',
  budget: 'any',
  people_count: 1,
})

const isSubmitting = ref(false)
const errorMessage = ref('')
const responseMessage = ref('')
const explanationSystem = ref(null)
const recommendations = ref([])
const carouselIndex = ref(0)
const expandedCards = reactive(new Set())
const fastMode = ref(false)
const showPreferences = ref(false)
const resultId = ref(null)
const speechesLoading = ref(false)
const feedbackState = reactive({})
const feedbackPending = reactive(new Set())
const highlightedId = ref(null)
let _speechPollTimer = null

// 解析动画状态
const isParsing = ref(false)
const parsePhase = ref(0)
const parsedIntent = ref(null)
const parseProgress = ref(0)

// narrative map fixed state
const narrativeMapWrapper = ref(null)
const isMapFixed = ref(false)
const mapFixedStyle = ref(null)
let _resizeObserver = null

// 用户位置（从 buildPayload 中提取，地图中心点）
const userPosition = ref(null)

function toggleMatchDetails(restaurantId) {
  if (expandedCards.has(restaurantId)) {
    expandedCards.delete(restaurantId)
  } else {
    expandedCards.add(restaurantId)
  }
}

const currentUser = computed(() => authState.currentUser)
const hasResults = computed(() => recommendations.value.length > 0)
const highlightedTaste = computed(() => form.taste || '不限口味')
const personalizedCards = ref([])
const personalizedLoading = ref(false)
const activePersonalizedCard = computed(
  () => personalizedCards.value[carouselIndex.value % Math.max(personalizedCards.value.length, 1)],
)
const currentUserTags = computed(() => {
  const allTags = currentUser.value?.preference_json || []
  // 过滤掉已删除的无效标签（只保留当前tasteOptions中的有效标签）
  return allTags.filter(tag => tasteOptions.includes(tag))
})
const visibleResponseMessage = computed(() => {
  if (!responseMessage.value || responseMessage.value === 'ok') {
    return ''
  }
  return responseMessage.value
})
const mealTitle = computed(() => {
  const hour = new Date().getHours()

  if (hour >= 5 && hour < 10) {
    return '早上吃什么'
  }

  if (hour >= 10 && hour < 14) {
    return '中午吃什么'
  }

  if (hour >= 14 && hour < 21) {
    return '今晚吃什么'
  }

  return '夜宵吃什么'
})
const mealSubtitle = computed(() => {
  const hour = new Date().getHours()

  if (hour >= 5 && hour < 10) {
    return '选好今天早上的口味和预算，看看附近有什么合适的早餐选择。'
  }

  if (hour >= 10 && hour < 14) {
    return '选好中午想吃的口味和预算，马上看看这顿午饭去哪里更合适。'
  }

  if (hour >= 14 && hour < 21) {
    return '把想吃的口味、预算和人数选好，马上看看今天更适合去哪一家。'
  }

  return '挑好夜宵想吃的口味和预算，看看现在还有哪些店值得去。'
})
const mealEyebrow = computed(() => {
  const hour = new Date().getHours()

  if (hour >= 5 && hour < 10) {
    return '早餐时间'
  }

  if (hour >= 10 && hour < 14) {
    return '午饭时间'
  }

  if (hour >= 14 && hour < 21) {
    return '晚饭时间'
  }

  return '夜宵时间'
})

function applyQuickIdea(text) {
  form.query = text
}

function moveCarousel(direction) {
  if (!personalizedCards.value.length) {
    return
  }

  const length = personalizedCards.value.length
  carouselIndex.value = (carouselIndex.value + direction + length) % length
}

async function loadPersonalizedCards() {
  if (!currentUser.value) {
    personalizedCards.value = []
    return
  }
  personalizedLoading.value = true
  try {
    personalizedCards.value = await getPersonalizedRecommendations(currentUser.value)
  } finally {
    personalizedLoading.value = false
  }
}

let _presetLoadingToken = 0

async function loadPersonalizedCardsSafe() {
  _presetLoadingToken += 1
  const token = _presetLoadingToken
  await loadPersonalizedCards()
  if (token !== _presetLoadingToken) {
    return
  }
}

watch(
  () => authState.currentUser,
  (newUser, oldUser) => {
    if (newUser !== oldUser) {
      carouselIndex.value = 0
    }
    loadPersonalizedCardsSafe()
  },
  { immediate: true, deep: true },
)

function buildBudgetRange(budget) {
  if (budget === '30') {
    return { budget_min: 0, budget_max: 30 }
  }

  if (budget === '60') {
    return { budget_min: 30, budget_max: 60 }
  }

  if (budget === '80+') {
    return { budget_min: 60, budget_max: 120 }
  }

  return {}
}

function buildPayload() {
  return {
    user_id: currentUser.value?.id || undefined,
    query: form.query || undefined,
    longitude: 114.35968,
    latitude: 30.52878,
    radius: currentUser.value?.distance_preference || 1200,
    max_count: 6,
    taste: form.taste || currentUser.value?.preference_json?.[0] || undefined,
    people_count: Number(form.people_count),
    fast_mode: fastMode.value,
    ...buildBudgetRange(form.budget),
  }
}

function _stopSpeechPoll() {
  if (_speechPollTimer) {
    clearInterval(_speechPollTimer)
    _speechPollTimer = null
  }
}

function _startSpeechPoll(rid) {
  _stopSpeechPoll()
  speechesLoading.value = true
  let attempts = 0
  // 每次轮询间隔 1500ms，最多 60 次 = 90s
  // LLM 单次超时 10s，批量处理多个餐馆最坏约 60-70s，留足余量
  const MAX_ATTEMPTS = 60
  _speechPollTimer = setInterval(async () => {
    attempts++
    try {
      const data = await fetchSpeeches(rid)
      if (data?.code === 0 && Array.isArray(data.speeches)) {
        const hasAnySpeech = data.speeches.some(s => s !== null && s !== undefined && s !== '')
        if (hasAnySpeech) {
          data.speeches.forEach((speech, i) => {
            const item = recommendations.value[i]
            if (item && !item.explanation) {
              item.explanation = {}
            }
            if (item?.explanation && speech) {
              item.explanation.ai_speech = speech
            }
          })
          _stopSpeechPoll()
          speechesLoading.value = false
          return
        }
        // speeches 全为 null：说明 Redis 已写入但所有条目均生成失败
        // 只在接近超时时才放弃（留足时间给规则降级写入）
        if (data.speeches.length > 0 && attempts >= MAX_ATTEMPTS - 2) {
          _stopSpeechPoll()
          speechesLoading.value = false
          return
        }
      }
    } catch (_) {
      // 忽略轮询错误
    }
    if (attempts >= MAX_ATTEMPTS) {
      _stopSpeechPoll()
      speechesLoading.value = false
    }
  }, 1500)
}

onUnmounted(_stopSpeechPoll)

async function handleFeedback(restaurantId, action) {
  if (!currentUser.value || feedbackPending.has(restaurantId)) return
  feedbackPending.add(restaurantId)
  try {
    await submitFeedback({
      user_id: currentUser.value.id,
      restaurant_id: restaurantId,
      recommendation_id: resultId.value ?? undefined,
      action_type: action,
      rating: action === 'LIKE' ? 5 : 1,
      chosen: action === 'LIKE',
    })
    feedbackState[restaurantId] = action
  } catch (_) {
    // 忽略反馈提交失败，不影响主流程
  } finally {
    feedbackPending.delete(restaurantId)
  }
}

async function submitRecommendation() {
  isSubmitting.value = true
  isParsing.value = true
  parsePhase.value = 1
  parsedIntent.value = null
  parseProgress.value = 0
  
  errorMessage.value = ''
  responseMessage.value = ''
  recommendations.value = []
  explanationSystem.value = null
  expandedCards.clear()
  Object.keys(feedbackState).forEach(k => delete feedbackState[k])
  _stopSpeechPoll()
  resultId.value = null
  speechesLoading.value = false
  highlightedId.value = null

  try {
    const payload = buildPayload()
    userPosition.value = { lng: payload.longitude, lat: payload.latitude }
    
    if (fastMode.value) {
      isParsing.value = false
      const result = await fetchRecommendations(payload)
      recommendations.value = result.recommendations ?? []
      explanationSystem.value = result.explanation_system ?? null
      responseMessage.value = result.message ?? ''
      if (result.result_id) {
        resultId.value = result.result_id
        _startSpeechPoll(result.result_id)
      }
    } else {
      // Phase 1: 调用后端真实 LLM 意图解析，动画显示 "正在理解用户输入..."
      const parseResult = await fetchParseIntent(payload)
      
      // Phase 2: 后端返回了真实的分析步骤，逐条动画展示
      parsePhase.value = 2
      parsedIntent.value = parseResult.parsed
      const steps = parseResult.parsed?.analysis_steps ?? []
      for (let i = 0; i < steps.length; i++) {
        parseProgress.value = i + 1
        await new Promise(resolve => setTimeout(resolve, 300))
      }
      
      // Phase 3: 调用后端推荐接口，动画显示 "正在匹配附近餐馆..."
      parsePhase.value = 3
      const result = await fetchRecommendations(payload)
      
      // Phase 4: 推荐计算完成
      parsePhase.value = 4
      await new Promise(resolve => setTimeout(resolve, 300))
      
      isParsing.value = false
      
      recommendations.value = result.recommendations ?? []
      explanationSystem.value = result.explanation_system ?? null
      responseMessage.value = result.message ?? ''
      if (result.result_id) {
        resultId.value = result.result_id
        _startSpeechPoll(result.result_id)
      }
    }
  } catch (error) {
    isParsing.value = false
    recommendations.value = []
    explanationSystem.value = null
    errorMessage.value = error.message
  } finally {
    isSubmitting.value = false
  }
}

function _updateMapFixedState() {
  const wrap = narrativeMapWrapper.value
  if (!wrap) return
  const rect = wrap.getBoundingClientRect()
  const viewportH = window.innerHeight || document.documentElement.clientHeight
  // only enable fixed when the component height is not taller than viewport
  if (rect.height <= viewportH && rect.top <= 0) {
    // compute fixed left/width to keep alignment
    isMapFixed.value = true
    mapFixedStyle.value = {
      position: 'fixed',
      top: '20px',
      left: `${rect.left}px`,
      width: `${rect.width}px`,
      zIndex: 1050,
    }
    // keep the wrapper height to avoid layout collapse
    wrap.style.height = `${rect.height}px`
  } else {
    isMapFixed.value = false
    mapFixedStyle.value = null
    wrap.style.height = ''
  }
}

onMounted(() => {
  // update on scroll/resize
  window.addEventListener('scroll', _updateMapFixedState, { passive: true })
  window.addEventListener('resize', _updateMapFixedState)
  // in case of layout shifts, observe size changes
  if (window.ResizeObserver) {
    _resizeObserver = new ResizeObserver(_updateMapFixedState)
    if (narrativeMapWrapper.value) _resizeObserver.observe(narrativeMapWrapper.value)
  }
})

onUnmounted(() => {
  window.removeEventListener('scroll', _updateMapFixedState)
  window.removeEventListener('resize', _updateMapFixedState)
  if (_resizeObserver && narrativeMapWrapper.value) {
    _resizeObserver.unobserve(narrativeMapWrapper.value)
    _resizeObserver = null
  }
})
</script>

<template>
  <main class="consumer-shell">
    <section class="topbar">
      <div>
        <p class="eyebrow">What-2-Eat</p>
        <h2 class="topbar-title">今天吃什么</h2>
      </div>

      <div v-if="currentUser" class="session-card">
        <div>
          <p class="session-label">当前用户</p>
          <strong>{{ currentUser.nickname }}</strong>
          <span>@{{ currentUser.username }}</span>
        </div>
        <div class="session-actions">
          <RouterLink class="secondary-link" to="/profile">偏好设置</RouterLink>
          <button class="text-button" type="button" @click="logoutUser">退出登录</button>
        </div>
      </div>

      <RouterLink v-else class="primary-link" to="/auth">注册 / 登录</RouterLink>
    </section>

    <section class="consumer-hero">
      <div class="hero-stage">
        <p class="eyebrow">{{ mealEyebrow }}</p>
        <h1>{{ mealTitle }}</h1>
        <p class="hero-lead">{{ mealSubtitle }}</p>

        <form class="prompt-composer" @submit.prevent="submitRecommendation">
          <label class="prompt-field">
            <span>今天想吃点什么</span>
            <textarea
              v-model.trim="form.query"
              rows="4"
              placeholder="例如：想吃点热乎的，别太贵，适合两个人一起吃"
            />
          </label>

          <div class="quick-idea-row">
            <button
              v-for="idea in quickIdeas"
              :key="idea"
              class="chip-button"
              type="button"
              @click="applyQuickIdea(idea)"
            >
              {{ idea }}
            </button>
          </div>

          <button
            class="pref-toggle"
            type="button"
            @click="showPreferences = !showPreferences"
          >
            <span>{{ showPreferences ? '收起偏好设置 ▲' : '展开偏好设置 ▼' }}</span>
          </button>

          <div v-show="showPreferences" class="preference-grid">
            <section class="pref-card">
              <p class="pref-title">口味偏好</p>
              <div class="pill-row">
                <button
                  v-for="taste in tasteOptions"
                  :key="taste"
                  class="option-pill"
                  type="button"
                  :data-active="form.taste === taste"
                  @click="form.taste = form.taste === taste ? '' : taste"
                >
                  {{ taste }}
                </button>
              </div>
            </section>

            <section class="pref-card">
              <p class="pref-title">预算区间</p>
              <div class="pill-row">
                <button
                  v-for="option in budgetOptions"
                  :key="option.value"
                  class="option-pill"
                  type="button"
                  :data-active="form.budget === option.value"
                  @click="form.budget = option.value"
                >
                  {{ option.label }}
                </button>
              </div>
            </section>

            <section class="pref-card">
              <p class="pref-title">就餐人数</p>
              <div class="pill-row">
                <button
                  v-for="count in partyOptions"
                  :key="count"
                  class="option-pill"
                  type="button"
                  :data-active="form.people_count === count"
                  @click="form.people_count = count"
                >
                  {{ count }} 人
                </button>
              </div>
            </section>
          </div>

          <div class="composer-footer">
            <div class="smart-summary">
              <span>当前偏好</span>
              <strong>{{ highlightedTaste }}</strong>
              <span>{{ form.people_count }} 人</span>
            </div>

            <div class="composer-actions">
              <button
                class="fast-mode-toggle"
                type="button"
                :data-active="fastMode"
                :title="fastMode ? '极速模式开：跳过 AI 解析，< 1s 返回' : '标准模式：AI 意图解析 + 全景解释'"
                @click="fastMode = !fastMode"
              >
                <span>⚡</span>
                <span>{{ fastMode ? '极速' : '标准' }}</span>
              </button>

              <button class="primary-button" type="submit" :disabled="isSubmitting">
                {{ isSubmitting ? '推荐中...' : '帮我选吃的' }}
              </button>
            </div>
          </div>
        </form>
      </div>

      <aside class="hero-aside">
        <article class="carousel-card">
          <div class="carousel-header">
            <div>
              <p class="card-label">偏好推荐</p>
              <h2>{{ currentUser ? `${currentUser.nickname} 可能会喜欢` : '登录后查看专属推荐' }}</h2>
            </div>

            <div class="carousel-controls">
              <button class="carousel-button" type="button" @click="moveCarousel(-1)">‹</button>
              <button class="carousel-button" type="button" @click="moveCarousel(1)">›</button>
            </div>
          </div>

          <template v-if="personalizedLoading">
            <div class="carousel-body">
              <p class="carousel-kicker">加载中</p>
              <h3>正在搜索附近的餐厅...</h3>
              <p class="carousel-copy">根据你的口味偏好和预算偏好，正在从周边搜索最合适的推荐。</p>
            </div>
          </template>

          <template v-else-if="currentUser && activePersonalizedCard">
            <div class="carousel-body">
              <p class="carousel-kicker">{{ activePersonalizedCard.category }}</p>
              <h3>{{ activePersonalizedCard.name }}</h3>
              <p class="carousel-copy">{{ activePersonalizedCard.reason }}</p>

              <div class="stat-row">
                <span>人均 ¥{{ activePersonalizedCard.avgPrice }}</span>
                <span>评分 {{ activePersonalizedCard.rating }}</span>
              </div>

              <div class="match-chip-row">
                <span
                  v-for="tag in activePersonalizedCard.sharedTags"
                  :key="tag"
                  class="match-chip"
                >
                  {{ tag }}
                </span>
              </div>

              <div class="profile-brief">
                <p>常用偏好</p>
                <div class="match-chip-row">
                  <span
                    v-for="tag in currentUserTags.slice(0, 4)"
                    :key="tag"
                    class="profile-chip"
                  >
                    {{ tag }}
                  </span>
                </div>
              </div>
            </div>
          </template>

          <div v-else-if="!personalizedLoading && currentUser" class="carousel-empty">
            <p>附近暂未找到与你偏好匹配的餐厅，试试调整你的口味和预算偏好。</p>
            <RouterLink class="primary-link" to="/profile">调整偏好</RouterLink>
          </div>

          <div v-else class="carousel-empty">
            <p>登录后可根据你的常用口味、预算和偏好标签生成专属推荐。</p>
            <RouterLink class="primary-link" to="/auth">去登录</RouterLink>
          </div>
        </article>

      </aside>
    </section>

    <section class="results-stage">
      <div class="results-header">
        <div>
          <p class="eyebrow">Recommendations</p>
          <h2>现在适合你的选择</h2>
        </div>
      </div>

      <div v-if="errorMessage" class="feedback-block feedback-error">
        {{ errorMessage }}
      </div>

      <div v-else-if="visibleResponseMessage && !hasResults" class="feedback-block feedback-info">
        {{ visibleResponseMessage }}
      </div>

      <!-- 推荐结果主体：单栏布局（卡片 + 在推荐综述下方展示地图） -->
      <div class="results-body">
      <!-- 左侧：解释系统 + 餐厅卡片 -->
      <div class="results-main">

      <!-- AI 意图解析过程卡片 -->
      <article v-if="isParsing" class="narrative-banner parsing-process-card">
        <div class="parsing-header">
          <h3>🤖 AI正在分析你的需求</h3>
        </div>
        
        <div class="parsing-body">
          <p v-if="parsePhase === 1" class="parsing-step pulse">正在理解用户输入...</p>
          
          <div v-if="parsePhase >= 2 && parsedIntent?.analysis_steps" class="parsed-items">
            <p
              v-for="(step, idx) in parsedIntent.analysis_steps"
              :key="idx"
              v-show="parseProgress > idx"
              class="fade-in"
            >
              ✓ {{ step.label }}：{{ step.value }}
            </p>
          </div>
          
          <p v-if="parsePhase === 3" class="parsing-step pulse mt-4">正在匹配附近餐馆...</p>
          <p v-if="parsePhase === 4" class="parsing-step success-text mt-4">推荐计算完成</p>
        </div>
      </article>

      <article
        v-else-if="explanationSystem?.welcome_narrative || explanationSystem?.hello_voice"
        class="narrative-banner"
      >
        <p class="card-label">推荐综述</p>

        <div v-if="explanationSystem.hello_voice" class="hello-voice-row">
          <p class="hello-voice-text">{{ explanationSystem.hello_voice }}</p>
        </div>

        <h3 v-if="explanationSystem.welcome_narrative">{{ explanationSystem.welcome_narrative }}</h3>

        <div v-if="explanationSystem.structured_context" class="intent-context-row">
          <span class="intent-mode-badge">{{ explanationSystem.structured_context.intent_mode }}</span>
          <span
            v-for="tag in explanationSystem.structured_context.core_tags"
            :key="tag"
            class="match-chip"
          >{{ tag }}</span>
        </div>
        <!-- 将地图嵌入到推荐综述下方 -->
        <div v-if="hasResults" ref="narrativeMapWrapper" class="narrative-map">
          <div
            class="narrative-map-inner"
            :class="{ 'is-fixed': isMapFixed }"
            :style="mapFixedStyle"
          >
            <MapView
              :user-position="userPosition"
              :restaurants="recommendations"
              :highlighted-id="highlightedId"
              data-testid="map-view"
              @restaurant-click="highlightedId = $event"
            />
            <p class="map-legend">
              <span class="legend-user"></span>我的位置
              <span class="legend-rest"></span>推荐餐厅
            </p>
          </div>
        </div>
      </article>

      <!-- 骨架屏 / 卡片列表 -->
      <div v-if="isSubmitting && !isParsing" class="consumer-result-list">
        <article v-for="n in 6" :key="n" class="consumer-result-card skeleton-card" aria-hidden="true">
          <div class="skeleton-line skeleton-label"></div>
          <div class="skeleton-line skeleton-title"></div>
          <div class="skeleton-line skeleton-text"></div>
          <div class="skeleton-line skeleton-text short"></div>
          <div class="skeleton-actions">
            <div class="skeleton-line skeleton-btn"></div>
            <div class="skeleton-line skeleton-btn"></div>
          </div>
        </article>
      </div>

      <div v-else-if="hasResults" class="consumer-result-list">
        <article
          v-for="item in recommendations"
          :key="item.restaurant_id"
          class="consumer-result-card"
          :data-highlighted="item.restaurant_id === highlightedId"
          @mouseenter="highlightedId = item.restaurant_id"
          @mouseleave="highlightedId = null"
          @click="highlightedId = item.restaurant_id"
        >
          <div class="result-head">
            <p class="card-label">候选餐馆</p>
            <h3>{{ item.restaurant_name }}</h3>
          </div>

          <p class="consumer-summary">
            {{ item.explanation?.summary || '这家店已经加入本次推荐列表。' }}
          </p>

          <div v-if="item.explanation?.ai_speech" class="ai-speech-block">
            <p class="ai-speech-text">🤖 {{ item.explanation.ai_speech }}</p>
          </div>
          <div v-else-if="speechesLoading && resultId" class="ai-speech-loading">
            <span>💬 AI 点评生成中…</span>
          </div>

          <div v-if="item.explanation?.reasoning_logic" class="reason-pair">
            <div>
              <span>首要原因</span>
              <strong>{{ item.explanation.reasoning_logic.primary_factor }}</strong>
            </div>
            <div>
              <span>补充原因</span>
              <strong>{{ item.explanation.reasoning_logic.secondary_factor || '店铺信息已更新' }}</strong>
            </div>
          </div>

          <ul
            v-if="item.explanation?.dimension_details?.length"
            class="mini-detail-list"
          >
            <li
              v-for="detail in item.explanation.dimension_details"
              :key="`${item.restaurant_id}-${detail.dimension}-${detail.detail}`"
            >
              <strong>{{ detail.dimension }}</strong>
              <span>{{ detail.detail }}</span>
            </li>
          </ul>

          <div v-if="item.explanation?.match_details?.length" class="match-details-section">
            <button
              class="match-details-toggle"
              type="button"
              @click="toggleMatchDetails(item.restaurant_id)"
            >
              <span>查看评分维度详情</span>
              <span class="toggle-arrow" :data-open="expandedCards.has(item.restaurant_id)">›</span>
            </button>

            <ul v-if="expandedCards.has(item.restaurant_id)" class="match-details-list">
              <li
                v-for="detail in item.explanation.match_details"
                :key="`${item.restaurant_id}-md-${detail.dimension}`"
                class="match-detail-item"
                :data-impact="detail.score_impact"
              >
                <div class="match-detail-header">
                  <strong>{{ detail.dimension }}</strong>
                  <span class="impact-badge" :data-impact="detail.score_impact">
                    {{ detail.score_impact === 'high' ? '高影响' : detail.score_impact === 'low' ? '低影响' : '中等' }}
                  </span>
                </div>
                <span class="match-detail-text">{{ detail.detail }}</span>
              </li>
            </ul>
          </div>

          <div class="feedback-row">
            <span v-if="!currentUser" class="feedback-hint">登录后可以对推荐给出反馈</span>
            <template v-else>
              <button
                class="feedback-btn"
                type="button"
                title="这家不错"
                :data-active="feedbackState[item.restaurant_id] === 'LIKE'"
                :disabled="feedbackPending.has(item.restaurant_id)"
                @click="handleFeedback(item.restaurant_id, 'LIKE')"
              >
                <span>👍</span>
                <span>适合我</span>
              </button>
              <button
                class="feedback-btn"
                type="button"
                title="不太合适"
                :data-active="feedbackState[item.restaurant_id] === 'DISLIKE'"
                :disabled="feedbackPending.has(item.restaurant_id)"
                @click="handleFeedback(item.restaurant_id, 'DISLIKE')"
              >
                <span>👎</span>
                <span>不适合</span>
              </button>
            </template>
          </div>
        </article>
      </div>

      <div v-else class="consumer-empty">
        <h3>先选好今天的口味和预算</h3>
        <p>选好条件后就能开始查看今天更适合去吃的店。</p>
      </div>

      </div><!-- /results-main -->

      <!-- 右侧地图侧栏已移除，地图现在展示在推荐综述下方 -->

      </div><!-- /results-body -->
    </section>
  </main>
</template>

<style scoped>
/* ── 解析动画 ─────────────────────────────────────── */
.parsing-process-card {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 24px;
}
.parsing-header h3 {
  font-size: 18px;
  font-weight: 600;
  color: #1976d2;
  margin: 0;
}
.parsing-body {
  font-size: 15px;
  color: #333;
  line-height: 1.6;
}
.parsed-items {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  background: #f8f9fa;
  padding: 16px;
  border-radius: 8px;
}
.parsed-items p {
  margin: 0;
  color: #424242;
}
.mt-4 {
  margin-top: 16px;
}
.success-text {
  color: #2e7d32;
  font-weight: 600;
}

/* 动画效果 */
.pulse {
  animation: pulse 1.5s infinite ease-in-out;
}
@keyframes pulse {
  0% { opacity: 0.6; }
  50% { opacity: 1; }
  100% { opacity: 0.6; }
}
.fade-in {
  animation: fadeIn 0.3s ease-out forwards;
}
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(5px); }
  to { opacity: 1; transform: translateY(0); }
}

/* ── 双栏布局 ─────────────────────────────────────── */
.results-body {
  display: flex;
  flex-direction: column;
  gap: 24px;
}
.results-body--split {
  display: grid;
  grid-template-columns: 1fr 400px;
  gap: 24px;
  align-items: start;
}
.results-main {
  min-width: 0;
}

.narrative-map {
  position: relative;
}
.narrative-map-inner.is-fixed {
  box-shadow: 0 6px 24px rgba(0,0,0,0.12);
  border-radius: 8px;
  background: #fff;
  padding: 8px;
}

/* ── 地图侧栏 sticky ──────────────────────────────── */
.results-map-aside {
  min-width: 0;
}
.results-map-sticky {
  position: sticky;
  top: 20px;
}
.map-legend {
  display: flex;
  align-items: center;
  gap: 16px;
  font-size: 12px;
  color: #666;
  margin-top: 8px;
  padding: 0 4px;
}
.legend-user {
  display: inline-block;
  width: 12px;
  height: 12px;
  background: #ff5722;
  border-radius: 50%;
  border: 2px solid #fff;
  box-shadow: 0 1px 3px rgba(0,0,0,.3);
}
.legend-rest {
  display: inline-block;
  width: 12px;
  height: 12px;
  background: #1976d2;
  border-radius: 50%;
  border: 2px solid #fff;
  box-shadow: 0 1px 3px rgba(0,0,0,.3);
}

/* ── 卡片高亮 ─────────────────────────────────────── */
.consumer-result-card[data-highlighted='true'] {
  outline: 2px solid #1976d2;
  outline-offset: -2px;
  box-shadow: 0 4px 20px rgba(25, 118, 210, 0.18);
}

/* ── 偏好折叠按钮 ─────────────────────────────────── */
.pref-toggle {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: none;
  border: 1px solid #e0e0e0;
  border-radius: 6px;
  padding: 6px 14px;
  font-size: 13px;
  color: #666;
  cursor: pointer;
  transition: border-color 0.2s, color 0.2s;
  margin-bottom: 4px;
  margin-top : 10px;
  margin-left:10px;
}
.pref-toggle:hover {
  border-color: #1976d2;
  color: #1976d2;
}

/* ── 响应式：小屏退化为单栏 ────────────────────────── */
@media (max-width: 900px) {
  .results-body--split {
    grid-template-columns: 1fr;
  }
  .results-map-sticky {
    position: static;
  }
}
</style>