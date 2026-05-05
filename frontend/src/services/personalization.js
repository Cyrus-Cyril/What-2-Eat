const restaurantCatalog = [
  {
    id: 'r001',
    name: '渝味火锅城',
    category: '火锅',
    tags: ['火锅', '川菜', '麻辣', '聚餐', '夜宵'],
    avgPrice: 58,
    rating: 4.7,
    reason: '麻辣风味稳定，适合朋友一起吃。',
  },
  {
    id: 'r002',
    name: '森氧轻食碗',
    category: '轻食',
    tags: ['轻食', '低脂', '健康饮食', '工作日午餐'],
    avgPrice: 42,
    rating: 4.6,
    reason: '热量友好，适合想吃清爽一些的时候。',
  },
  {
    id: 'r003',
    name: '川湘小馆',
    category: '川菜',
    tags: ['川菜', '下饭', '热菜', '性价比'],
    avgPrice: 35,
    rating: 4.5,
    reason: '下饭菜多，人均压力不大。',
  },
  {
    id: 'r004',
    name: '谷物厨房',
    category: '简餐',
    tags: ['健康饮食', '轻食', '谷物', '一人食'],
    avgPrice: 39,
    rating: 4.4,
    reason: '适合工作日中午快速解决一餐。',
  },
  {
    id: 'r005',
    name: '老街烧烤铺',
    category: '烧烤',
    tags: ['烧烤', '夜宵', '聚餐', '重口味'],
    avgPrice: 64,
    rating: 4.3,
    reason: '适合晚上放松吃点重口味。',
  },
  {
    id: 'r006',
    name: '清爽沙拉屋',
    category: '沙拉',
    tags: ['轻食', '沙拉', '健康饮食', '低脂'],
    avgPrice: 33,
    rating: 4.5,
    reason: '清爽低负担，口味也不会太单调。',
  },
]

function scoreRestaurant(user, restaurant) {
  if (!user) {
    return restaurant.rating
  }

  let score = restaurant.rating * 10
  const preferences = user.preference_json || []
  const sharedTags = restaurant.tags.filter((tag) => preferences.includes(tag))
  score += sharedTags.length * 15

  if (restaurant.avgPrice >= user.budget_preference_min && restaurant.avgPrice <= user.budget_preference_max) {
    score += 12
  }

  if (user.healthy_preference > 0.7 && restaurant.tags.includes('健康饮食')) {
    score += 10
  }

  if (user.spicy_preference > 0.7 && restaurant.tags.some((tag) => ['川菜', '火锅', '麻辣'].includes(tag))) {
    score += 10
  }

  if (user.favorites?.includes(restaurant.name)) {
    score += 16
  }

  return score
}

export function getPersonalizedRecommendations(user) {
  return restaurantCatalog
    .map((restaurant) => ({
      ...restaurant,
      sharedTags: user ? restaurant.tags.filter((tag) => user.preference_json?.includes(tag)) : [],
      score: scoreRestaurant(user, restaurant),
    }))
    .sort((left, right) => right.score - left.score)
}

export function getNearbyNewShops() {
  return [
    {
      id: 'n001',
      name: '街角砂锅小馆',
      category: '砂锅',
      distanceText: '步行约 6 分钟',
      avgPrice: 32,
      openingLabel: '新开 5 天',
    },
    {
      id: 'n002',
      name: '青柠越南粉',
      category: '越南粉',
      distanceText: '步行约 9 分钟',
      avgPrice: 28,
      openingLabel: '新开 2 周',
    },
    {
      id: 'n003',
      name: '晚风居酒食堂',
      category: '居酒屋',
      distanceText: '骑行约 8 分钟',
      avgPrice: 68,
      openingLabel: '试营业',
    },
  ]
}
