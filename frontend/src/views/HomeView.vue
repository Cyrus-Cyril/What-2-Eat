<script setup>
import { computed, reactive, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { fetchRecommendations } from '@/services/api'
import { authState, logoutUser } from '@/services/auth'
import { getPersonalizedRecommendations } from '@/services/personalization'

const quickIdeas = [
  '想吃热乎一点的',
  '想吃便宜又快的午饭',
  '今天想吃辣的',
  '适合两个人一起吃',
]

const tasteOptions = ['川菜', '火锅', '烧烤', '轻食', '快餐', '面食']
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
  people_count: 2,
})

const isSubmitting = ref(false)
const errorMessage = ref('')
const responseMessage = ref('')
const explanationSystem = ref(null)
const recommendations = ref([])
const carouselIndex = ref(0)

const currentUser = computed(() => authState.currentUser)
const hasResults = computed(() => recommendations.value.length > 0)
const highlightedTaste = computed(() => form.taste || '不限口味')
const personalizedCards = computed(() => getPersonalizedRecommendations(currentUser.value))
const activePersonalizedCard = computed(
  () => personalizedCards.value[carouselIndex.value % Math.max(personalizedCards.value.length, 1)],
)
const currentUserTags = computed(() => currentUser.value?.preference_json || [])
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
    ...buildBudgetRange(form.budget),
  }
}

async function submitRecommendation() {
  isSubmitting.value = true
  errorMessage.value = ''
  responseMessage.value = ''

  try {
    const result = await fetchRecommendations(buildPayload())
    recommendations.value = result.recommendations ?? []
    explanationSystem.value = result.explanation_system ?? null
    responseMessage.value = result.message ?? ''
  } catch (error) {
    recommendations.value = []
    explanationSystem.value = null
    errorMessage.value = error.message
  } finally {
    isSubmitting.value = false
  }
}
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

          <div class="preference-grid">
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

            <button class="primary-button" type="submit" :disabled="isSubmitting">
              {{ isSubmitting ? '推荐中...' : '帮我选吃的' }}
            </button>
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

          <template v-if="currentUser && activePersonalizedCard">
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

      <article v-if="explanationSystem?.welcome_narrative" class="narrative-banner">
        <p class="card-label">推荐综述</p>
        <h3>{{ explanationSystem.welcome_narrative }}</h3>
      </article>

      <div v-if="hasResults" class="consumer-result-list">
        <article
          v-for="item in recommendations"
          :key="item.restaurant_id"
          class="consumer-result-card"
        >
          <div class="result-head">
            <p class="card-label">候选餐馆</p>
            <h3>{{ item.restaurant_name }}</h3>
          </div>

          <p class="consumer-summary">
            {{ item.explanation?.summary || '这家店已经加入本次推荐列表。' }}
          </p>

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
        </article>
      </div>

      <div v-else class="consumer-empty">
        <h3>先选好今天的口味和预算</h3>
        <p>选好条件后就能开始查看今天更适合去吃的店。</p>
      </div>
    </section>
  </main>
</template>
