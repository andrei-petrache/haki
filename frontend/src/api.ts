import { tActive } from './i18n/i18n'

const API_BASE = '/api'

export type User = {
  id: number
  email: string
  daily_calorie_target: number | null
  created_at: string
  // The account's language; null (or missing, from an older server): no choice
  language?: string | null
  // Phase 3: how the daily target is set, and the weekly goal (kg, signed)
  target_mode?: TargetMode
  goal_kg_per_week?: number | null
}

export type TargetMode = 'manual' | 'adaptive'

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

export type Food = FoodInput & {
  id: number
  // The catalog food this one was copied from; null when typed in by hand
  catalog_food_id?: number | null
  // Marked by the user; such foods come first on Today
  favourite?: boolean
  // How the user last logged it, for one-tap logging; null if never
  last_logged?: LastLogged | null
  // The catalog's names of the food it was copied from (null: typed by hand)
  catalog_name?: string | null
  catalog_name_ro?: string | null
}

export type LastLogged = { grams: number; meal_type: MealType; eaten_on: string }

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

export type MealEntry = Nutrients & {
  id: number
  eaten_on: string
  meal_type: MealType
  // Null for a quick entry: it has its own nutrients, no food and no grams
  food_id: number | null
  grams: number | null
  food_name: string
  // Quick entries live apart from food entries: their ids can be equal
  quick?: boolean
  // The catalog's names of the entry's food, as on Food (null: none)
  catalog_name?: string | null
  catalog_name_ro?: string | null
}

/** A one-off entry without a food: calories, and optionally a name and macros. */
export type QuickEntryInput = {
  eaten_on: string
  meal_type: MealType
  calories: number
  name?: string
  protein?: number
  carbs?: number
  fat?: number
}

/** A key unique across food and quick entries, for lists and "busy" state. */
export function entryKey(entry: Pick<MealEntry, 'id' | 'quick'>): string {
  return `${entry.quick ? 'quick' : 'food'}-${entry.id}`
}

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
  // The catalog exercise this one was copied from; null when typed in by hand
  catalog_exercise_id?: number | null
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
  // The program day it was started from; null when logged by hand, or when
  // that day was deleted or replaced since
  program_id?: number | null
  program_day_id?: number | null
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
  // The server's stable code (e.g. consent_required), when it sent one
  code?: string

  constructor(status: number, message: string, code?: string) {
    super(message)
    this.status = status
    this.code = code
  }
}

/** The stable error code in the server's body, if any. */
function errorCode(body: unknown): string | undefined {
  const code = body && typeof body === 'object' && 'code' in body ? (body as { code: unknown }).code : undefined
  return typeof code === 'string' ? code : undefined
}

/** Turn FastAPI's error body into a readable message. */
function errorMessage(body: unknown): string {
  if (body && typeof body === 'object' && 'detail' in body) {
    const detail = (body as { detail: unknown }).detail
    if (typeof detail === 'string') return detail
    // Validation errors (422) come as a list of problems; name the field
    if (Array.isArray(detail) && detail.length > 0) {
      const message = String(detail[0]?.msg ?? tActive('api.invalidInput'))
      const field = Array.isArray(detail[0]?.loc) ? detail[0].loc.at(-1) : null
      return typeof field === 'string' ? `${field}: ${message}` : message
    }
  }
  return tActive('api.unknown')
}

/** A message to show the user for any error thrown by the functions below. */
export function describeError(err: unknown): string {
  return err instanceof ApiError ? err.message : tActive('app.cannotReach')
}

let onUnauthorized: ((rejected: string) => void) | null = null

/** Register what to do when the server rejects a token (e.g. it expired); it gets that token. */
export function setUnauthorizedHandler(handler: ((rejected: string) => void) | null): void {
  onUnauthorized = handler
}

/** request(), but with the status too: for calls where 200 and 201 mean different things. */
async function send<T>(
  path: string,
  options: RequestInit = {},
  token?: string,
): Promise<{ status: number; body: T }> {
  const headers = new Headers(options.headers)
  headers.set('Content-Type', 'application/json')
  if (token) headers.set('Authorization', `Bearer ${token}`)

  const response = await fetch(`${API_BASE}${path}`, { ...options, headers })
  const body: unknown = await response.json().catch(() => null)

  if (!response.ok) {
    // Only for authenticated calls: a 401 from /auth/login means wrong password
    if (response.status === 401 && token) onUnauthorized?.(token)
    // Our own text for both: they come from Nginx too, as HTML, not our JSON.
    // 429: this client sent too many login/signup attempts (Nginx rate limit)
    if (response.status === 429) {
      throw new ApiError(429, tActive('api.tooManyAttempts'))
    }
    if (response.status === 503) {
      throw new ApiError(503, tActive('api.unavailable'))
    }
    throw new ApiError(response.status, errorMessage(body), errorCode(body))
  }
  return { status: response.status, body: body as T }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  token?: string,
): Promise<T> {
  return (await send<T>(path, options, token)).body
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

/**
 * Replace the password, given the current one. Answers with a new token:
 * every token from before, this one included, is refused from then on.
 * A wrong current password is 403, not 401: the session is fine, so it
 * must not log the user out.
 */
export function changePassword(
  token: string,
  currentPassword: string,
  newPassword: string,
): Promise<TokenResponse> {
  return request<TokenResponse>(
    '/auth/me/password',
    json('PUT', { current_password: currentPassword, new_password: newPassword }),
    token,
  )
}

/**
 * Delete the account and everything in it, at once and for good. Needs
 * the password: a wrong one is 403 and deletes nothing. Afterwards the
 * token gets 401 and the email can sign up again.
 */
export function deleteAccount(token: string, password: string): Promise<void> {
  // A JSON body on DELETE: request() always sends Content-Type: application/json
  return request<void>('/auth/me', json('DELETE', { password }), token)
}

/** Keep a language with the account, or none (null: follow the browser). */
export function setAccountLanguage(token: string, language: 'en' | 'ro' | null): Promise<User> {
  return request<User>('/auth/me', json('PUT', { language }), token)
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

/** Mark or unmark one of the user's foods as a favourite. Both are idempotent. */
export function setFavourite(token: string, id: number, favourite: boolean): Promise<void> {
  return request<void>(`/foods/${id}/favourite`, { method: favourite ? 'PUT' : 'DELETE' }, token)
}

/** How many recent foods Today offers as one-tap picks. */
export const RECENT_FOODS_LIMIT = 6

/**
 * The user's foods by when they were last logged, newest first, each once.
 * Foods never logged are left out, so a new user gets an empty list.
 */
export function fetchRecentFoods(token: string, limit = RECENT_FOODS_LIMIT): Promise<Food[]> {
  return request<Food[]>(`/foods/recent?limit=${limit}`, {}, token)
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

/**
 * The same DELETE, sent so it outlives the page (fetch keepalive): for a
 * deletion still waiting on its Undo when the tab closes, reloads or the
 * user leaves Foods. Nobody reads the answer: if the food got logged
 * meanwhile (409), it simply stays.
 */
export function deleteFoodOnLeave(token: string, id: number): void {
  fetch(`${API_BASE}/foods/${id}`, {
    method: 'DELETE',
    keepalive: true,
    headers: { Authorization: `Bearer ${token}` },
  }).catch(() => {})
}

export function fetchEntries(token: string, day: string): Promise<MealEntry[]> {
  const query = new URLSearchParams({ date: day })
  return request<MealEntry[]>(`/entries?${query}`, {}, token)
}

/**
 * The Idempotency-Key for a meal entry: the server makes the entry once per
 * key and returns that same entry for a resend (offline logging, outbox.ts).
 */
function withKey(init: RequestInit, key?: string): RequestInit {
  return key ? { ...init, headers: { ...Object.fromEntries(new Headers(init.headers)), 'Idempotency-Key': key } } : init
}

export function createEntry(token: string, entry: MealEntryInput, key?: string): Promise<MealEntry> {
  return request<MealEntry>('/entries', withKey(json('POST', entry), key), token)
}

export type MealCopy = { from_day: string; from_meal: MealType; to_day: string; to_meal: MealType }

/**
 * Copy every entry of one meal to another meal or day, in one request.
 * Returns the new entries: none when the meal was empty. Copying onto the
 * same meal and day is refused (422).
 */
export function copyMeal(token: string, copy: MealCopy): Promise<MealEntry[]> {
  return request<MealEntry[]>('/entries/copy', json('POST', copy), token)
}

export function createQuickEntry(token: string, entry: QuickEntryInput, key?: string): Promise<MealEntry> {
  return request<MealEntry>('/entries/quick', withKey(json('POST', entry), key), token)
}

/** Delete a food entry or a quick one: each kind has its own path. */
export function deleteMealEntry(token: string, entry: Pick<MealEntry, 'id' | 'quick'>): Promise<void> {
  const path = entry.quick ? `/entries/quick/${entry.id}` : `/entries/${entry.id}`
  return request<void>(path, { method: 'DELETE' }, token)
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

/** An exercise's sets in the latest earlier workout with it. */
export type LastSession = { workout_id: number; performed_on: string; sets: WorkoutSet[] }

/** The best set of an exercise, and the workout where it was first done. */
export type BestSet = WorkoutSet & { workout_id: number; performed_on: string }

function beforeQuery(before: number | null): string {
  return before === null ? '' : `?${new URLSearchParams({ before_workout: String(before) })}`
}

/**
 * The sets of an exercise last time: in the latest workout before
 * `before` (any workout when null). null when never done before.
 */
export function fetchLastSession(
  token: string,
  exerciseId: number,
  before: number | null = null,
): Promise<LastSession | null> {
  return request<LastSession | null>(`/exercises/${exerciseId}/last${beforeQuery(before)}`, {}, token)
}

/** The best set of an exercise before `before` (ever, when null), or null. */
export function fetchBestSet(
  token: string,
  exerciseId: number,
  before: number | null = null,
): Promise<BestSet | null> {
  return request<BestSet | null>(`/exercises/${exerciseId}/best${beforeQuery(before)}`, {}, token)
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

/** One planned exercise of a program day: `sets` sets of `reps` at `weight_kg`. */
export type PlannedExerciseInput = {
  exercise_id: number
  sets: number
  reps: number
  weight_kg: number // 0 for bodyweight exercises
}

export type PlannedExercise = PlannedExerciseInput & { exercise_name: string }

export type ProgramDayInput = {
  // PUT only: a saved day's id keeps that day (and workouts' link to it);
  // without one the day is new. POST ignores it.
  id?: number
  position: number // the day's place in the plan, 1 to 7
  name: string
  exercises: PlannedExerciseInput[]
}

export type ProgramDay = {
  id: number
  position: number
  name: string
  exercises: PlannedExercise[]
}

/** A whole program as the client sends it: POST creates all of it or nothing. */
export type ProgramInput = {
  name: string
  days: ProgramDayInput[]
}

export type Program = {
  id: number
  name: string
  days: ProgramDay[]
}

/** One row of the program list: a count instead of the days. */
export type ProgramSummary = {
  id: number
  name: string
  day_count: number
}

/** The API's default page size: a full page means there may be more. */
export const PROGRAMS_PAGE_SIZE = 20

/** One page of programs, by name. */
export function fetchPrograms(
  token: string,
  limit: number = PROGRAMS_PAGE_SIZE,
  offset: number = 0,
): Promise<ProgramSummary[]> {
  const query = new URLSearchParams({ limit: String(limit), offset: String(offset) })
  return request<ProgramSummary[]>(`/programs?${query}`, {}, token)
}

export function fetchProgram(token: string, id: number): Promise<Program> {
  return request<Program>(`/programs/${id}`, {}, token)
}

export function createProgram(token: string, program: ProgramInput): Promise<Program> {
  return request<Program>('/programs', json('POST', program), token)
}

/**
 * Replace a program with this one, whole: name and days. A day sent with
 * its id is changed in place; one without is new, one left out is deleted.
 * New days get new ids, so read them from the answer.
 */
export function updateProgram(token: string, id: number, program: ProgramInput): Promise<Program> {
  return request<Program>(`/programs/${id}`, json('PUT', program), token)
}

export function deleteProgram(token: string, id: number): Promise<void> {
  return request<void>(`/programs/${id}`, { method: 'DELETE' }, token)
}

/**
 * Start a workout from one day of a program, on the given day (YYYY-MM-DD).
 *
 * The result is an ordinary workout, a copy of the day's plan with no link
 * back to it: changing or deleting the program never touches it.
 */
export function startWorkout(
  token: string,
  programId: number,
  dayId: number,
  performedOn: string,
): Promise<Workout> {
  return request<Workout>(
    `/programs/${programId}/days/${dayId}/workouts`,
    json('POST', { performed_on: performedOn }),
    token,
  )
}

/** The catalog's languages: English names always, Romanian ones for most items. */
export type CatalogLanguage = 'en' | 'ro'

/** Where catalog items come from, and how to credit them. */
export type CatalogSource = {
  key: string
  name: string
  url: string
  license: string
  attribution: string
  attribution_required: boolean // credit on screen required by the licence
  share_alike: boolean
  version: string
}

export type CatalogFood = {
  id: number
  name: string
  name_ro: string | null
  calories_per_100g: number
  protein_per_100g: number
  carbs_per_100g: number
  fat_per_100g: number
  source: CatalogSource
}

export type CatalogExercise = {
  id: number
  name: string
  name_ro: string | null
  category: string | null
  equipment: string | null
  level: string | null
  force: string | null
  mechanic: string | null
  primary_muscles: string[]
  secondary_muscles: string[]
  source: CatalogSource
}

/** The API's default page size for catalog searches. */
export const CATALOG_PAGE_SIZE = 20

function catalogQuery(q: string, language: CatalogLanguage, limit: number, offset: number): string {
  return new URLSearchParams({
    q,
    language,
    limit: String(limit),
    offset: String(offset),
  }).toString()
}

/**
 * Catalog foods matching every word of q in either name, ignoring case and
 * diacritics ("branza" finds "Brânză feta"); all of them for an empty q.
 * Ordered by the name in `language`.
 */
export function searchCatalogFoods(
  token: string,
  q: string,
  language: CatalogLanguage,
  limit: number = CATALOG_PAGE_SIZE,
  offset: number = 0,
): Promise<CatalogFood[]> {
  return request<CatalogFood[]>(`/catalog/foods?${catalogQuery(q, language, limit, offset)}`, {}, token)
}

export function searchCatalogExercises(
  token: string,
  q: string,
  language: CatalogLanguage,
  limit: number = CATALOG_PAGE_SIZE,
  offset: number = 0,
): Promise<CatalogExercise[]> {
  return request<CatalogExercise[]>(
    `/catalog/exercises?${catalogQuery(q, language, limit, offset)}`,
    {},
    token,
  )
}

type Per100g = Pick<FoodInput, 'calories_per_100g' | 'protein_per_100g' | 'carbs_per_100g' | 'fat_per_100g'>

/** One result of GET /foods/search: the user's own food, or a catalog food. */
export type FoodSearchResult =
  | (Per100g & {
      origin: 'own'
      id: number
      name: string
      favourite: boolean
      last_logged: LastLogged | null
      catalog_food_id: number | null
      catalog_name?: string | null
      catalog_name_ro?: string | null
    })
  | (Per100g & {
      origin: 'catalog'
      // The catalog food's id: copy it with copyCatalogFood before logging
      id: number
      // Already in the language asked for
      name: string
      source_key: string
    })

/**
 * The user's foods and the catalog in one list, own ones first (by last
 * use), each word matched in either name, ignoring case and diacritics.
 * At most `limit` of each origin.
 */
export function searchFoods(
  token: string,
  q: string,
  language: CatalogLanguage,
  limit = 20,
): Promise<FoodSearchResult[]> {
  const query = new URLSearchParams({ q, language, limit: String(limit) })
  return request<FoodSearchResult[]>(`/foods/search?${query}`, {}, token)
}

export function fetchCatalogSources(token: string): Promise<CatalogSource[]> {
  return request<CatalogSource[]>('/catalog/sources', {}, token)
}

/** A catalog item copied into the user's own list: new (201), or the copy they had (200). */
export type CatalogCopy<T> = { item: T; created: boolean }

/** Add a catalog food to the user's foods, named in `language`; 409 when a food of theirs has that name. */
export async function copyCatalogFood(
  token: string,
  catalogFoodId: number,
  language: CatalogLanguage,
): Promise<CatalogCopy<Food>> {
  const { status, body } = await send<Food>(
    '/foods/from-catalog',
    json('POST', { catalog_food_id: catalogFoodId, language }),
    token,
  )
  return { item: body, created: status === 201 }
}

export async function copyCatalogExercise(
  token: string,
  catalogExerciseId: number,
  language: CatalogLanguage,
): Promise<CatalogCopy<Exercise>> {
  const { status, body } = await send<Exercise>(
    '/exercises/from-catalog',
    json('POST', { catalog_exercise_id: catalogExerciseId, language }),
    token,
  )
  return { item: body, created: status === 201 }
}

// Body weight (phase 3, backend/app/body.py). Behind a server flag: while
// it is off every one of these answers 404, and the app shows nothing of it.

/** One weigh-in, with the trend line at that day; outlier: far (2%) from the trend. */
export type WeightPoint = {
  measured_on: string
  weight_kg: number
  trend_kg: number
  outlier: boolean
}

export type Weight = { measured_on: string; weight_kg: number }

/** Weigh-ins from `from` to `to` (both days included), oldest first. */
export function fetchWeights(token: string, from: string, to: string): Promise<WeightPoint[]> {
  const query = new URLSearchParams({ from, to })
  return request<WeightPoint[]>(`/weights?${query}`, {}, token)
}

/** The day's weigh-in, new or replacing that day's (one per day). */
export function putWeight(token: string, day: string, weightKg: number): Promise<Weight> {
  return request<Weight>(`/weights/${day}`, json('PUT', { weight_kg: weightKg }), token)
}

export function deleteWeight(token: string, day: string): Promise<void> {
  return request<void>(`/weights/${day}`, { method: 'DELETE' }, token)
}

/** Why the adaptive target still waits for data (GET /targets/current). */
export type TargetReason =
  | 'few_days'
  | 'few_weigh_ins'
  | 'few_logged_days'
  | 'no_weigh_ins_at_start'
  | 'no_weigh_ins_at_end'

/**
 * The target for one day and how it was reached. "manual": the user's own
 * daily_calorie_target; "collecting": the same while the estimate waits
 * (reasons says what is missing); "adaptive": the estimated energy use
 * plus the goal. target_kcal is null with no target of the user's own.
 */
export type CurrentTarget = {
  target_mode: TargetMode
  status: 'manual' | 'collecting' | 'adaptive'
  target_kcal: number | null
  tdee_kcal: number | null
  week_start: string | null
  weigh_ins: number | null
  logged_days: number | null
  reasons: string[]
  trend_kg_per_week: number | null
  goal_kg_per_week: number | null
  // The floor (1200 kcal, or 1000 under the energy use) set it, not the goal
  floor_applied: boolean
}

/** The target for `day`, the client's local today (the server allows ±1 day). */
export function fetchCurrentTarget(token: string, day: string): Promise<CurrentTarget> {
  return request<CurrentTarget>(`/targets/current?${new URLSearchParams({ date: day })}`, {}, token)
}

/** How the target is set, and the goal in kg a week (null: none). Both always sent. */
export function setGoal(token: string, mode: TargetMode, goalKgPerWeek: number | null): Promise<User> {
  return request<User>('/auth/me/goal', json('PUT', { target_mode: mode, goal_kg_per_week: goalKgPerWeek }), token)
}

// Trust (phase 4): password reset and data export (backend's
// feat/reset-and-export). The reset answers 404 while the server has it
// switched off (PASSWORD_RESET_ENABLED).

/** Ask for a reset link. Always 202 with the same body, whether the e-mail has an account or not. */
export function requestPasswordReset(email: string): Promise<void> {
  return request<void>('/auth/password-reset', json('POST', { email }))
}

/** Set a new password with the link's token; signs out every other session. 400 invalid_reset_token. */
export function confirmPasswordReset(token: string, newPassword: string): Promise<{ access_token: string }> {
  return request<{ access_token: string }>(
    '/auth/password-reset/confirm',
    json('POST', { token, new_password: newPassword }),
  )
}

/** The export's file name from Content-Disposition, else the server's own pattern. */
export function exportFileName(disposition: string | null, today: string): string {
  const match = disposition?.match(/filename="?([^";]+)"?/)
  // Only a plain name (letters, digits, dot, dash, underscore): never a path
  const name = match?.[1]
  return name && /^[\w.-]+$/.test(name) ? name : `haki-export-${today}.json`
}

/**
 * Whether an export's text is whole: the server ends a complete file with
 * "complete": true, so a stream cut short by an error lacks it.
 */
export function exportIsComplete(text: string): boolean {
  try {
    const data: unknown = JSON.parse(text)
    return typeof data === 'object' && data !== null && (data as { complete?: unknown }).complete === true
  } catch {
    return false
  }
}

/**
 * Everything the account holds, as a JSON file: fetched with the token in
 * the Authorization header (never in a URL) and checked for completeness
 * before it is offered. 403 wrong_password.
 */
export async function exportAccount(token: string, password: string, today: string): Promise<{ blob: Blob; name: string }> {
  const response = await fetch(`${API_BASE}/auth/me/export`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ password }),
  })
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null)
    if (response.status === 401) onUnauthorized?.(token)
    if (response.status === 429) throw new ApiError(429, tActive('api.tooManyAttempts'))
    if (response.status === 503) throw new ApiError(503, tActive('api.unavailable'))
    throw new ApiError(response.status, errorMessage(body), errorCode(body))
  }
  const text = await response.text()
  if (!exportIsComplete(text)) throw new ApiError(500, tActive('export.incomplete'))
  return {
    blob: new Blob([text], { type: 'application/json' }),
    name: exportFileName(response.headers.get('Content-Disposition'), today),
  }
}

/** Which optional features the server has switched on; no account needed, cached a minute. */
export type Features = { password_reset: boolean; body_weight: boolean; export: boolean }

export function fetchFeatures(): Promise<Features> {
  return request<Features>('/features')
}

// Consent for health data (phase 4; backend's feat/consent). Behind the
// body weight switch: off, every one of these answers 404.

/** The consent's exact text, in a language, with its version. */
export type ConsentText = { purpose: string; version: string; locale: string; text: string; sha256: string }

/** Whether the account's consent is valid for the current version. */
export type ConsentStatus = {
  purpose: string
  required_version: string
  valid: boolean
  given_version: string | null
  given_at: string | null
  withdrawn_at: string | null
}

export function fetchConsentText(token: string, locale: string): Promise<ConsentText> {
  return request<ConsentText>(`/auth/me/consents/health_data/text?${new URLSearchParams({ locale })}`, {}, token)
}

export function fetchConsent(token: string): Promise<ConsentStatus> {
  return request<ConsentStatus>('/auth/me/consents/health_data', {}, token)
}

/** Agree to the text of `version` as shown in `locale`. 409 consent_version_outdated: reload the text. */
export function giveConsent(token: string, version: string, locale: string): Promise<ConsentStatus> {
  return request<ConsentStatus>('/auth/me/consents/health_data', json('PUT', { version, locale }), token)
}

/** Withdraw: the server deletes every weigh-in and estimate at once, and the target goes back to manual. */
export function withdrawConsent(token: string): Promise<void> {
  return request<void>('/auth/me/consents/health_data', { method: 'DELETE' }, token)
}

// The weekly dashboard (phase 6; backend's GET /dashboard/week)

export type WeekDay = {
  date: string
  kcal: number
  protein: number
  carbs: number
  fat: number
  target_kcal: number | null
  // Anything logged that day, food or quick entry
  logged: boolean
  workouts: number
  sets: number
  reps: number
  volume_kg: number
}

export type WeekTotals = {
  kcal: number
  protein: number
  carbs: number
  fat: number
  days_logged: number
  // Over the logged days; null with none
  avg_kcal: number | null
  workouts: number
  sets: number
  reps: number
  volume_kg: number
}

export type Week = {
  week_start: string
  days: WeekDay[]
  totals: WeekTotals & { volume_by_muscle: Record<string, number> }
  previous_week: WeekTotals
  // Only with body weight on and its consent given
  body_weight: { weigh_ins: number; start_trend_kg: number | null; end_trend_kg: number | null; change_kg: number | null } | null
}

/** The week holding `day` (the server takes its Monday). */
export function fetchWeek(token: string, day: string): Promise<Week> {
  return request<Week>(`/dashboard/week?${new URLSearchParams({ start: day })}`, {}, token)
}
