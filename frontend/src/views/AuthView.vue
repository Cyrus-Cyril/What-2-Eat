<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { loginUser, registerUser } from '@/services/auth'

const router = useRouter()
const authMode = ref('login')
const errorMessage = ref('')

const registerForm = reactive({
  username: '',
  password: '',
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

const loginForm = reactive({
  username: '',
  password: '',
})

const tasteOptions = ['川菜', '火锅', '烧烤', '轻食', '健康饮食', '夜宵', '性价比', '聚餐']

function togglePreference(tag) {
  if (registerForm.preference_json.includes(tag)) {
    registerForm.preference_json = registerForm.preference_json.filter((item) => item !== tag)
    return
  }

  registerForm.preference_json = [...registerForm.preference_json, tag]
}

function submitLogin() {
  errorMessage.value = ''
  try {
    loginUser(loginForm)
    router.push('/')
  } catch (error) {
    errorMessage.value = error.message
  }
}

function submitRegister() {
  errorMessage.value = ''
  try {
    registerUser(registerForm)
    router.push('/')
  } catch (error) {
    errorMessage.value = error.message
  }
}
</script>

<template>
  <main class="auth-shell">
    <section class="auth-panel">
      <div class="auth-copy">
        <p class="eyebrow">Account</p>
        <h1>登录后记住你的口味</h1>
        <p>
          这一版前端页面已经对齐数据库文档里的用户字段，先用本地会话模拟注册登录，后面接后端接口时可以直接替换。
        </p>
      </div>

      <div class="auth-card">
        <div class="auth-tabs">
          <button class="auth-tab" type="button" :data-active="authMode === 'login'" @click="authMode = 'login'">
            登录
          </button>
          <button class="auth-tab" type="button" :data-active="authMode === 'register'" @click="authMode = 'register'">
            注册
          </button>
        </div>

        <p v-if="errorMessage" class="feedback-block feedback-error">
          {{ errorMessage }}
        </p>

        <form v-if="authMode === 'login'" class="auth-form" @submit.prevent="submitLogin">
          <label class="field">
            <span>用户名</span>
            <input v-model.trim="loginForm.username" type="text" placeholder="例如 xiaoyu" />
          </label>

          <label class="field">
            <span>密码</span>
            <input v-model="loginForm.password" type="password" placeholder="默认演示密码 123456" />
          </label>

          <button class="primary-button auth-submit" type="submit">登录并返回首页</button>
        </form>

        <form v-else class="auth-form" @submit.prevent="submitRegister">
          <div class="auth-grid">
            <label class="field">
              <span>用户名</span>
              <input v-model.trim="registerForm.username" type="text" />
            </label>

            <label class="field">
              <span>昵称</span>
              <input v-model.trim="registerForm.nickname" type="text" />
            </label>

            <label class="field">
              <span>密码</span>
              <input v-model="registerForm.password" type="password" />
            </label>

            <label class="field">
              <span>性别</span>
              <select v-model="registerForm.gender">
                <option value="未设置">未设置</option>
                <option value="女">女</option>
                <option value="男">男</option>
              </select>
            </label>

            <label class="field">
              <span>年龄</span>
              <input v-model="registerForm.age" type="number" min="12" max="80" />
            </label>

            <label class="field">
              <span>可接受距离（米）</span>
              <input v-model="registerForm.distance_preference" type="number" min="500" step="100" />
            </label>

            <label class="field">
              <span>最低预算</span>
              <input v-model="registerForm.budget_preference_min" type="number" min="0" />
            </label>

            <label class="field">
              <span>最高预算</span>
              <input v-model="registerForm.budget_preference_max" type="number" min="0" />
            </label>
          </div>

          <section class="pref-block">
            <p class="pref-title">偏好标签（对应 `preference_json`）</p>
            <div class="pill-row">
              <button
                v-for="tag in tasteOptions"
                :key="tag"
                class="option-pill"
                type="button"
                :data-active="registerForm.preference_json.includes(tag)"
                @click="togglePreference(tag)"
              >
                {{ tag }}
              </button>
            </div>
          </section>

          <div class="slider-grid">
            <label class="field">
              <span>辣度偏好 {{ registerForm.spicy_preference }}</span>
              <input v-model="registerForm.spicy_preference" type="range" min="0" max="1" step="0.1" />
            </label>

            <label class="field">
              <span>甜口偏好 {{ registerForm.sweet_preference }}</span>
              <input v-model="registerForm.sweet_preference" type="range" min="0" max="1" step="0.1" />
            </label>

            <label class="field">
              <span>健康倾向 {{ registerForm.healthy_preference }}</span>
              <input v-model="registerForm.healthy_preference" type="range" min="0" max="1" step="0.1" />
            </label>
          </div>

          <button class="primary-button auth-submit" type="submit">注册并生成我的首页</button>
        </form>
      </div>
    </section>
  </main>
</template>
