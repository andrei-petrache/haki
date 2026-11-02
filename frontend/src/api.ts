const API_BASE = '/api'

export type User = {
  id: number
  email: string
  daily_calorie_target: number | null
  created_at: string
}

export const MEAL_TYPES = ['breakfast', 'lunch', 'dinner', 'snack'] as const
export type MealType = (typeof MEAL_TYPES)[number]

/** Nutrients per 100 g, as the client sends them. */
export type FoodInput = {
  name: string
  calories_per_100g: number
  protein_per_100g: number
  carbs_per_100g: number
  fat_per_100g: number
}

export type Food = FoodInput & { id: number }

export type Nutrients = {
  calories: number
  protein: number
  carbs: number
  fat: number
}

export type MealEntryInput = {
  food_id: number
  eaten_on: string // YYYY-MM-DD, the user's local day
  meal_type: MealType
  grams: number
}

export type MealEntry = MealEntryInput & Nutrients & { id: number; food_name: string }

export type DailySummary = {
  eaten_on: string
  totals: Nutrients
  meals: Record<MealType, Nutrients>
  daily_calorie_target: number | null
  calories_remaining: number | null
}

export type Exercise = {
  id: number
  name: string
}

export type WorkoutSet = {
  reps: number
  weight_kg: number // 0 for bodyweight exercises
}

/** A whole workout as the client sends it: POST creates, PUT replaces all of it. */
export type WorkoutInput = {
  performed_on: string // YYYY-MM-DD, the user's local day
  note: string | null
  exercises: { exercise_id: number; sets: WorkoutSet[] }[]
}

export type Workout = {
  id: number
  performed_on: string
  note: string | null
  exercises: { exercise_id: number; exercise_name: string; sets: WorkoutSet[] }[]
}

/** One row of the workout list: counts instead of the full contents. */
export type WorkoutSummary = {
  id: number
  performed_on: string
  note: string | null
  exercise_count: number
  set_count: number
}

type TokenResponse = {
  access_token: string
  token_type: string
}

/** An error returned by the backend, with its HTTP status code. */
export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

/** Turn FastAPI's error body into a readable message. */
function errorMessage(body: unknown): string {
  if (body && typeof body === 'object' && 'detail' in body) {
    const detail = (body as { detail: unknown }).detail
    if (typeof detail === 'string') return detail
    // Validation errors (422) come as a list of problems; name the field
    if (Array.isArray(detail) && detail.length > 0) {
      const message = String(detail[0]?.msg ?? 'Invalid input')
      const field = Array.isArray(detail[0]?.loc) ? detail[0].loc.at(-1) : null
      return typeof field === 'string' ? `${field}: ${message}` : message
    }
  }
  return 'Something went wrong'
}

/** A message to show the user for any error thrown by the functions below. */
export function describeError(err: unknown): string {
  return err instanceof ApiError ? err.message : 'Cannot reach the server'
}

let onUnauthorized: (() => void) | null = null

/** Register what to do when the server rejects our token (e.g. it expired). */
export function setUnauthorizedHandler(handler: (() => void) | null): void {
  onUnauthorized = handler
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  token?: string,
): Promise<T> {
  const headers = new Headers(options.headers)
  headers.set('Content-Type', 'application/json')
  if (token) headers.set('Authorization', `Bearer ${token}`)

  const response = await fetch(`${API_BASE}${path}`, { ...options, headers })
  const body: unknown = await response.json().catch(() => null)

  if (!response.ok) {
    // Only for authenticated calls: a 401 from /auth/login means wrong password
    if (response.status === 401 && token) onUnauthorized?.()
    // Our own text for both: they come from Nginx too, as HTML, not our JSON.
    // 429: this client sent too many login/signup attempts (Nginx rate limit)
    if (response.status === 429) {
      throw new ApiError(429, 'Too many attempts. Wait a minute, then try again.')
    }
    if (response.status === 503) {
      throw new ApiError(503, 'Service temporarily unavailable, try again in a moment.')
    }
    throw new ApiError(response.status, errorMessage(body))
  }
  return body as T
}

function json(method: string, data: unknown): RequestInit {
  return { method, body: JSON.stringify(data) }
}

export function signup(email: string, password: string): Promise<User> {
  return request<User>('/auth/signup', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  })
}

export function login(email: string, password: string): Promise<TokenResponse> {
  return request<TokenResponse>('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  })
}

export function fetchMe(token: string): Promise<User> {
  return request<User>('/auth/me', {}, token)
}

export function setCalorieTarget(token: string, target: number | null): Promise<User> {
  return request<User>(
    '/auth/me/target',
    json('PUT', { daily_calorie_target: target }),
    token,
  )
}

export function fetchFoods(token: string): Promise<Food[]> {
  return request<Food[]>('/foods', {}, token)
}

export function createFood(token: string, food: FoodInput): Promise<Food> {
  return request<Food>('/foods', json('POST', food), token)
}

export function updateFood(token: string, id: number, food: FoodInput): Promise<Food> {
  return request<Food>(`/foods/${id}`, json('PUT', food), token)
}

export function deleteFood(token: string, id: number): Promise<void> {
  return request<void>(`/foods/${id}`, { method: 'DELETE' }, token)
}

export function fetchEntries(token: string, day: string): Promise<MealEntry[]> {
  const query = new URLSearchParams({ date: day })
  return request<MealEntry[]>(`/entries?${query}`, {}, token)
}

export function createEntry(token: string, entry: MealEntryInput): Promise<MealEntry> {
  return request<MealEntry>('/entries', json('POST', entry), token)
}

export function deleteEntry(token: string, id: number): Promise<void> {
  return request<void>(`/entries/${id}`, { method: 'DELETE' }, token)
}

export function fetchSummary(token: string, day: string): Promise<DailySummary> {
  const query = new URLSearchParams({ date: day })
  return request<DailySummary>(`/summary?${query}`, {}, token)
}

export function fetchExercises(token: string): Promise<Exercise[]> {
  return request<Exercise[]>('/exercises', {}, token)
}

export function createExercise(token: string, name: string): Promise<Exercise> {
  return request<Exercise>('/exercises', json('POST', { name }), token)
}

/** The API's default page size: a full page means there may be more. */
export const WORKOUTS_PAGE_SIZE = 20

/** One page of workouts, newest first. */
export function fetchWorkouts(
  token: string,
  limit: number = WORKOUTS_PAGE_SIZE,
  offset: number = 0,
): Promise<WorkoutSummary[]> {
  const query = new URLSearchParams({ limit: String(limit), offset: String(offset) })
  return request<WorkoutSummary[]>(`/workouts?${query}`, {}, token)
}

export function fetchWorkout(token: string, id: number): Promise<Workout> {
  return request<Workout>(`/workouts/${id}`, {}, token)
}

export function createWorkout(token: string, workout: WorkoutInput): Promise<Workout> {
  return request<Workout>('/workouts', json('POST', workout), token)
}

export function updateWorkout(
  token: string,
  id: number,
  workout: WorkoutInput,
): Promise<Workout> {
  return request<Workout>(`/workouts/${id}`, json('PUT', workout), token)
}

export function deleteWorkout(token: string, id: number): Promise<void> {
  return request<void>(`/workouts/${id}`, { method: 'DELETE' }, token)
}
