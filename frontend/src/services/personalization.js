import { fetchPresetRecommendations } from '@/services/api'

function buildPresetPayload(user) {
  if (!user) {
    return null
  }

  return {
    user_id: user.id,
    longitude: 114.35968,
    latitude: 30.52878,
    preference_tags: user.preference_json || [],
    budget_min: user.budget_preference_min || 0,
    budget_max: user.budget_preference_max || 100,
    distance_preference: user.distance_preference || 2000,
    spicy_preference: user.spicy_preference ?? 0.5,
    sweet_preference: user.sweet_preference ?? 0.5,
    healthy_preference: user.healthy_preference ?? 0.5,
    favorites: user.favorites || [],
    max_count: 6,
  }
}

function mapCard(backendCard) {
  return {
    id: backendCard.id,
    name: backendCard.name,
    category: backendCard.category,
    tags: backendCard.tags,
    avgPrice: backendCard.avg_price,
    rating: backendCard.rating,
    reason: backendCard.reason,
    sharedTags: backendCard.shared_tags,
    score: backendCard.score,
  }
}

function buildFallbackCards(user) {
  if (!user || !user.preference_json?.length) {
    return []
  }

  const tags = user.preference_json.slice(0, 3).join('、')
  return [
    {
      id: 'fallback-1',
      name: '正在加载中...',
      category: '偏好推荐',
      tags: user.preference_json,
      avgPrice: (user.budget_preference_min + user.budget_preference_max) / 2,
      rating: 4.5,
      reason: `根据你对 ${tags} 的偏好，正在搜索附近合适的餐厅。`,
      sharedTags: [],
      score: 0,
    },
  ]
}

export async function getPersonalizedRecommendations(user) {
  if (!user) {
    return []
  }

  const payload = buildPresetPayload(user)
  if (!payload) {
    return []
  }

  try {
    const result = await fetchPresetRecommendations(payload)
    if (result.code !== 0 || !result.recommendations?.length) {
      return []
    }
    const seen = new Set()
    const deduped = []
    for (const card of result.recommendations) {
      if (seen.has(card.id)) {
        continue
      }
      seen.add(card.id)
      deduped.push(mapCard(card))
    }
    return deduped
  } catch {
    return buildFallbackCards(user)
  }
}
