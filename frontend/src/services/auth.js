import { reactive } from 'vue'

const STORAGE_KEY = 'what2eat-auth-state'

function demoHash(input) {
  let hash = 0
  for (let index = 0; index < input.length; index += 1) {
    hash = (hash * 31 + input.charCodeAt(index)) >>> 0
  }
  return `demo-${hash.toString(16)}`
}

function createSeedUsers() {
  return [
    {
      id: 'u001',
      username: 'xiaoyu',
      passwordHash: demoHash('123456'),
      nickname: '小宇',
      gender: '男',
      age: 22,
      preference_json: ['川菜', '火锅', '夜宵', '性价比'],
      budget_preference_min: 20,
      budget_preference_max: 55,
      distance_preference: 1800,
      spicy_preference: 0.85,
      sweet_preference: 0.25,
      healthy_preference: 0.35,
      favorites: ['渝味火锅城', '川湘小馆', '老街烧烤铺'],
      history_keywords: ['麻辣', '热乎', '朋友聚餐'],
      register_time: '2026-05-01 19:20:00',
      last_active_time: '2026-05-05 18:40:00',
      status: 1,
    },
    {
      id: 'u002',
      username: 'linlin',
      passwordHash: demoHash('123456'),
      nickname: '琳琳',
      gender: '女',
      age: 21,
      preference_json: ['轻食', '沙拉', '低脂', '健康饮食'],
      budget_preference_min: 25,
      budget_preference_max: 70,
      distance_preference: 2500,
      spicy_preference: 0.2,
      sweet_preference: 0.55,
      healthy_preference: 0.92,
      favorites: ['森氧轻食碗', '谷物厨房', '清爽沙拉屋'],
      history_keywords: ['低脂', '工作日午餐', '一人食'],
      register_time: '2026-05-02 11:10:00',
      last_active_time: '2026-05-05 12:15:00',
      status: 1,
    },
  ]
}

function readStorage() {
  if (typeof window === 'undefined') {
    return {
      users: createSeedUsers(),
      currentUserId: 'u001',
    }
  }

  const raw = window.localStorage.getItem(STORAGE_KEY)
  if (!raw) {
    return {
      users: createSeedUsers(),
      currentUserId: 'u001',
    }
  }

  try {
    const parsed = JSON.parse(raw)
    return {
      users: parsed.users?.length ? parsed.users : createSeedUsers(),
      currentUserId: parsed.currentUserId || 'u001',
    }
  } catch {
    return {
      users: createSeedUsers(),
      currentUserId: 'u001',
    }
  }
}

function persistState() {
  if (typeof window === 'undefined') {
    return
  }

  window.localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify({
      users: authState.users,
      currentUserId: authState.currentUser?.id || null,
    }),
  )
}

const initialState = readStorage()

export const authState = reactive({
  users: initialState.users,
  currentUser: initialState.users.find((user) => user.id === initialState.currentUserId) || null,
})

persistState()

export function loginUser({ username, password }) {
  const user = authState.users.find((item) => item.username === username.trim())
  if (!user || user.passwordHash !== demoHash(password)) {
    throw new Error('用户名或密码不正确')
  }

  user.last_active_time = new Date().toISOString()
  authState.currentUser = user
  persistState()
  return user
}

export function registerUser(payload) {
  const username = payload.username.trim()
  if (!username) {
    throw new Error('用户名不能为空')
  }

  if (authState.users.some((item) => item.username === username)) {
    throw new Error('该用户名已存在')
  }

  const now = new Date().toISOString()
  const user = {
    id: `u${Date.now()}`,
    username,
    passwordHash: demoHash(payload.password),
    nickname: payload.nickname.trim() || username,
    gender: payload.gender || '未设置',
    age: Number(payload.age) || 18,
    preference_json: payload.preference_json,
    budget_preference_min: Number(payload.budget_preference_min) || 0,
    budget_preference_max: Number(payload.budget_preference_max) || 100,
    distance_preference: Number(payload.distance_preference) || 3000,
    spicy_preference: Number(payload.spicy_preference) || 0.5,
    sweet_preference: Number(payload.sweet_preference) || 0.5,
    healthy_preference: Number(payload.healthy_preference) || 0.5,
    favorites: [],
    history_keywords: payload.preference_json.slice(0, 3),
    register_time: now,
    last_active_time: now,
    status: 1,
  }

  authState.users = [...authState.users, user]
  authState.currentUser = user
  persistState()
  return user
}

export function logoutUser() {
  authState.currentUser = null
  persistState()
}

export function updateCurrentUserProfile(payload) {
  if (!authState.currentUser) {
    throw new Error('当前没有已登录用户')
  }

  const updatedUser = {
    ...authState.currentUser,
    ...payload,
    nickname: payload.nickname?.trim() || authState.currentUser.nickname,
    username: payload.username?.trim() || authState.currentUser.username,
    age: Number(payload.age) || authState.currentUser.age,
    budget_preference_min: Number(payload.budget_preference_min),
    budget_preference_max: Number(payload.budget_preference_max),
    distance_preference: Number(payload.distance_preference),
    spicy_preference: Number(payload.spicy_preference),
    sweet_preference: Number(payload.sweet_preference),
    healthy_preference: Number(payload.healthy_preference),
    last_active_time: new Date().toISOString(),
  }

  authState.users = authState.users.map((user) => (user.id === updatedUser.id ? updatedUser : user))
  authState.currentUser = updatedUser
  persistState()
  return updatedUser
}
