<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { fetchHealth, fetchRecommendations, getApiBaseUrl } from '@/services/api'

const apiBaseUrl = getApiBaseUrl()

const form = reactive({
  user_id: 'u001',
  query: '',
  longitude: 114.35968,
  latitude: 30.52878,
  radius: 1000,
  max_count: 10,
  budget_min: '',
  budget_max: '',
  taste: '',
  max_distance: '',
  people_count: '',
})

const health = ref({
  status: 'checking',
  version: '--',
})
const isCheckingHealth = ref(false)
const isSubmitting = ref(false)
const errorMessage = ref('')
const responseMessage = ref('')
const explanationSystem = ref(null)
const recommendations = ref([])

const hasResults = computed(() => recommendations.value.length > 0)

function normalizeOptionalNumber(value) {
  return value === '' || value === null ? undefined : Number(value)
}

function buildPayload() {
  return {
    user_id: form.user_id || undefined,
    query: form.query || undefined,
    longitude: Number(form.longitude),
    latitude: Number(form.latitude),
    radius: Number(form.radius),
    max_count: Number(form.max_count),
    budget_min: normalizeOptionalNumber(form.budget_min),
    budget_max: normalizeOptionalNumber(form.budget_max),
    taste: form.taste || undefined,
    max_distance: normalizeOptionalNumber(form.max_distance),
    people_count: normalizeOptionalNumber(form.people_count),
  }
}

async function loadHealth() {
  isCheckingHealth.value = true

  try {
    health.value = await fetchHealth()
  } catch (error) {
    health.value = {
      status: 'offline',
      version: '--',
    }
    errorMessage.value = error.message
  } finally {
    isCheckingHealth.value = false
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

onMounted(() => {
  loadHealth()
})
</script>

<template>
  <main class="page-shell">
    <section class="hero-panel">
      <div class="hero-copy">
        <p class="eyebrow">What-2-Eat Test</p>
        <h1>前后端联调工作台</h1>
        <p class="hero-text">
          这里保留完整测试参数、后端连通性检查和解释结构展示。普通用户主界面已经迁移到
          <RouterLink class="test-link" to="/">首页</RouterLink>。
        </p>
      </div>

      <div class="status-card">
        <p class="status-label">后端连接</p>
        <p class="status-value" :data-status="health.status">
          {{ isCheckingHealth ? '检查中...' : health.status }}
        </p>
        <p class="status-meta">API Base URL: {{ apiBaseUrl }}</p>
        <p class="status-meta">API Version: {{ health.version }}</p>
        <button class="ghost-button" type="button" @click="loadHealth" :disabled="isCheckingHealth">
          {{ isCheckingHealth ? '刷新中...' : '重新检测' }}
        </button>
      </div>
    </section>

    <section class="workspace-grid">
      <form class="control-panel" @submit.prevent="submitRecommendation">
        <div class="panel-heading">
          <h2>推荐参数</h2>
          <p>这里保留完整参数面板，方便你后续继续做接口联调和异常验证。</p>
        </div>

        <label class="field">
          <span>用户 ID</span>
          <input v-model.trim="form.user_id" type="text" placeholder="例如 u001" />
        </label>

        <label class="field field-wide">
          <span>自然语言需求</span>
          <textarea
            v-model.trim="form.query"
            rows="3"
            placeholder="例如：想吃 30 元左右的火锅，距离不要太远"
          />
        </label>

        <label class="field">
          <span>经度</span>
          <input v-model="form.longitude" type="number" step="0.00001" />
        </label>

        <label class="field">
          <span>纬度</span>
          <input v-model="form.latitude" type="number" step="0.00001" />
        </label>

        <label class="field">
          <span>搜索半径（米）</span>
          <input v-model="form.radius" type="number" min="50" />
        </label>

        <label class="field">
          <span>返回数量</span>
          <input v-model="form.max_count" type="number" min="1" max="50" />
        </label>

        <label class="field">
          <span>最低预算</span>
          <input v-model="form.budget_min" type="number" min="0" placeholder="可选" />
        </label>

        <label class="field">
          <span>最高预算</span>
          <input v-model="form.budget_max" type="number" min="0" placeholder="可选" />
        </label>

        <label class="field">
          <span>口味偏好</span>
          <input v-model.trim="form.taste" type="text" placeholder="例如 川菜 / 火锅" />
        </label>

        <label class="field">
          <span>最大可接受距离（米）</span>
          <input v-model="form.max_distance" type="number" min="50" placeholder="可选" />
        </label>

        <label class="field">
          <span>就餐人数</span>
          <input v-model="form.people_count" type="number" min="1" placeholder="可选" />
        </label>

        <div class="actions">
          <button class="primary-button" type="submit" :disabled="isSubmitting">
            {{ isSubmitting ? '推荐中...' : '获取推荐' }}
          </button>
        </div>
      </form>

      <section class="results-panel">
        <div class="panel-heading">
          <h2>推荐结果</h2>
          <p>当前版本按后端公开字段渲染，只依赖 `recommendations` 和 `explanation_system`。</p>
        </div>

        <div v-if="errorMessage" class="feedback-block feedback-error">
          {{ errorMessage }}
        </div>

        <div v-else-if="responseMessage" class="feedback-block feedback-info">
          {{ responseMessage }}
        </div>

        <article v-if="explanationSystem" class="system-card">
          <p class="card-label">全局解释</p>
          <h3>{{ explanationSystem.welcome_narrative }}</h3>
          <div class="system-meta">
            <span>模式：{{ explanationSystem.structured_context.intent_mode }}</span>
            <span>
              核心标签：
              {{ explanationSystem.structured_context.core_tags?.join(' / ') || '未提供' }}
            </span>
          </div>
        </article>

        <div v-if="hasResults" class="result-list">
          <article
            v-for="item in recommendations"
            :key="item.restaurant_id"
            class="result-card"
          >
            <div class="card-topline">
              <p class="card-label">餐馆 ID: {{ item.restaurant_id }}</p>
              <h3>{{ item.restaurant_name }}</h3>
            </div>

            <p class="summary">
              {{ item.explanation?.summary || '后端暂未提供摘要说明。' }}
            </p>

            <dl class="logic-grid" v-if="item.explanation?.reasoning_logic">
              <div>
                <dt>首要因素</dt>
                <dd>{{ item.explanation.reasoning_logic.primary_factor }}</dd>
              </div>
              <div>
                <dt>次要因素</dt>
                <dd>{{ item.explanation.reasoning_logic.secondary_factor || '未提供' }}</dd>
              </div>
            </dl>

            <ul
              v-if="item.explanation?.dimension_details?.length"
              class="dimension-list"
            >
              <li
                v-for="detail in item.explanation.dimension_details"
                :key="`${item.restaurant_id}-${detail.dimension}-${detail.detail}`"
              >
                <strong>{{ detail.dimension }}</strong>
                <span>{{ detail.detail }}</span>
                <em>{{ detail.score_impact }}</em>
              </li>
            </ul>

            <p v-if="item.explanation?.ai_speech" class="speech">
              {{ item.explanation.ai_speech }}
            </p>
          </article>
        </div>

        <div v-else class="empty-state">
          <h3>还没有推荐结果</h3>
          <p>填入左侧条件后点击“获取推荐”，这里会展示后端返回的推荐和解释内容。</p>
        </div>
      </section>
    </section>
  </main>
</template>
