<script setup>
import { computed, reactive, watch } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { authState, updateCurrentUserProfile } from '@/services/auth'

const router = useRouter()
const currentUser = computed(() => authState.currentUser)

const form = reactive({
  nickname: '',
  gender: '未设置',
  age: 20,
  preference_json: [],
  budget_preference_min: 20,
  budget_preference_max: 60,
  distance_preference: 2000,
  spicy_preference: 0.5,
  sweet_preference: 0.5,
  healthy_preference: 0.5,
})

const tasteOptions = ['川菜', '火锅', '烧烤', '轻食', '健康饮食', '夜宵', '性价比', '聚餐']

watch(
  currentUser,
  (user) => {
    if (!user) {
      router.push('/auth')
      return
    }

    form.nickname = user.nickname
    form.gender = user.gender
    form.age = user.age
    form.preference_json = [...(user.preference_json || [])]
    form.budget_preference_min = user.budget_preference_min
    form.budget_preference_max = user.budget_preference_max
    form.distance_preference = user.distance_preference
    form.spicy_preference = user.spicy_preference
    form.sweet_preference = user.sweet_preference
    form.healthy_preference = user.healthy_preference
  },
  { immediate: true },
)

function togglePreference(tag) {
  if (form.preference_json.includes(tag)) {
    form.preference_json = form.preference_json.filter((item) => item !== tag)
    return
  }

  form.preference_json = [...form.preference_json, tag]
}

function submitProfile() {
  updateCurrentUserProfile(form)
  router.push('/')
}
</script>

<template>
  <main class="auth-shell">
    <section class="auth-panel">
      <div class="auth-copy">
        <p class="eyebrow">Profile</p>
        <h1>调整你的当前偏好</h1>
        <p>这里可以直接修改当前账号的口味、预算、距离和饮食倾向。</p>
        <RouterLink class="secondary-link profile-back-link" to="/">返回首页</RouterLink>
      </div>

      <div class="auth-card">
        <form class="auth-form" @submit.prevent="submitProfile">
          <div class="auth-grid">
            <label class="field">
              <span>昵称</span>
              <input v-model.trim="form.nickname" type="text" />
            </label>

            <label class="field">
              <span>性别</span>
              <select v-model="form.gender">
                <option value="未设置">未设置</option>
                <option value="女">女</option>
                <option value="男">男</option>
              </select>
            </label>

            <label class="field">
              <span>年龄</span>
              <input v-model="form.age" type="number" min="12" max="80" />
            </label>

            <label class="field">
              <span>可接受距离（米）</span>
              <input v-model="form.distance_preference" type="number" min="500" step="100" />
            </label>

            <label class="field">
              <span>最低预算</span>
              <input v-model="form.budget_preference_min" type="number" min="0" />
            </label>

            <label class="field">
              <span>最高预算</span>
              <input v-model="form.budget_preference_max" type="number" min="0" />
            </label>
          </div>

          <section class="pref-block">
            <p class="pref-title">偏好标签</p>
            <div class="pill-row">
              <button
                v-for="tag in tasteOptions"
                :key="tag"
                class="option-pill"
                type="button"
                :data-active="form.preference_json.includes(tag)"
                @click="togglePreference(tag)"
              >
                {{ tag }}
              </button>
            </div>
          </section>

          <div class="slider-grid">
            <label class="field">
              <span>辣度偏好 {{ form.spicy_preference }}</span>
              <input v-model="form.spicy_preference" type="range" min="0" max="1" step="0.1" />
            </label>

            <label class="field">
              <span>甜口偏好 {{ form.sweet_preference }}</span>
              <input v-model="form.sweet_preference" type="range" min="0" max="1" step="0.1" />
            </label>

            <label class="field">
              <span>健康倾向 {{ form.healthy_preference }}</span>
              <input v-model="form.healthy_preference" type="range" min="0" max="1" step="0.1" />
            </label>
          </div>

          <button class="primary-button auth-submit" type="submit">保存当前偏好</button>
        </form>
      </div>
    </section>
  </main>
</template>
