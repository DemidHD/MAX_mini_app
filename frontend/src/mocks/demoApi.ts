import { ApiError } from '@/api/client'
import type {
  ApplicationSummary,
  CandidateApplication,
  CriterionType,
  EmployerCandidate,
  Interview,
  InterviewSlot,
  Match,
  ScreeningAnswer,
  ScreeningQuestion,
  ScreeningResult,
  ScreeningState,
  Vacancy,
} from '@/api/hiring'
import { criterionLabel, formatDayMonth } from '@/lib/format'

/**
 * ВРЕМЕННЫЙ источник данных для экранов P0, пока они не подключены к backend.
 *
 * Каждая функция повторяет эндпоинт тех-доки (раздел 27) и форму ответа из
 * `docs/api-contracts.md`, поэтому подключение экрана = замена импорта на
 * настоящий клиент из `api/`. Данные живут в памяти вкладки и сбрасываются
 * перезагрузкой. Решения о статусах (hard filters, бронирование) здесь только
 * имитируют ответ backend — сам frontend статусы не вычисляет.
 */

const LATENCY_MS = 250

function respond<T>(value: T, signal?: AbortSignal): Promise<T> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => resolve(structuredClone(value)), LATENCY_MS)
    signal?.addEventListener('abort', () => {
      clearTimeout(timer)
      reject(new DOMException('Aborted', 'AbortError'))
    })
  })
}

function notFound(code: string): never {
  throw new ApiError(404, { code, message: 'Не найдено' })
}

function atDay(offsetDays: number, hours = 0, minutes = 0): Date {
  const date = new Date()
  date.setHours(hours, minutes, 0, 0)
  date.setDate(date.getDate() + offsetDays)
  return date
}

function isoDate(offsetDays: number): string {
  const date = atDay(offsetDays)
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

// ---------------------------------------------------------------- вакансии

const vacancies: Vacancy[] = [
  {
    id: 12,
    title: 'Бариста',
    company_name: 'Кофейня Mokka',
    location: 'м. Белорусская',
    salary_min: '80000.00',
    salary_max: '95000.00',
    schedule: '2/2',
    status: 'published',
    description: 'Ищем бариста в кофейню рядом с метро.\nОпыт приветствуется, всему остальному научим.',
    criteria: [
      { type: 'schedule', required: true, value: { schedule: '2/2' } },
      { type: 'available_from', required: true, value: { date: isoDate(3) } },
      { type: 'location', required: true, value: { city: 'Москва' } },
      { type: 'experience', required: false, value: { min_months: 6 } },
      { type: 'certificate', required: false, value: { name: 'Медкнижка' } },
    ],
  },
  {
    id: 15,
    title: 'Официант',
    company_name: 'Ресторан Forma',
    location: 'м. Маяковская',
    salary_min: '70000.00',
    salary_max: '90000.00',
    schedule: '5/2',
    status: 'published',
    description: 'Ресторан авторской кухни. Обучение и питание за счёт заведения.',
    criteria: [
      { type: 'schedule', required: true, value: { schedule: '5/2' } },
      { type: 'location', required: true, value: { city: 'Москва' } },
      { type: 'salary', required: false, value: { max: 90000 } },
    ],
  },
  {
    id: 16,
    title: 'Администратор',
    company_name: 'Studio 21',
    location: 'м. Курская',
    salary_min: '75000.00',
    salary_max: '100000.00',
    schedule: 'full_time',
    status: 'published',
    description: 'Встреча гостей, запись, работа с кассой.',
    criteria: [
      { type: 'schedule', required: true, value: { schedule: 'full_time' } },
      { type: 'experience', required: true, value: { min_months: 12 } },
      { type: 'available_from', required: false, value: { date: isoDate(7) } },
    ],
  },
  {
    id: 17,
    title: 'Бариста',
    company_name: 'Кофейня Mokka',
    location: 'м. Пушкинская',
    salary_min: '80000.00',
    salary_max: '95000.00',
    schedule: '2/2',
    status: 'published',
    criteria: [{ type: 'schedule', required: true, value: { schedule: '2/2' } }],
  },
  {
    id: 18,
    title: 'Кассир',
    company_name: 'Пекарня «Хлеб»',
    location: 'м. Китай-город',
    salary_min: '60000.00',
    salary_max: '70000.00',
    schedule: '2/2',
    status: 'published',
    criteria: [{ type: 'schedule', required: true, value: { schedule: '2/2' } }],
  },
  {
    id: 19,
    title: 'Бариста',
    company_name: 'Кофейня Mokka',
    location: 'м. Белорусская',
    salary_min: '80000.00',
    salary_max: '95000.00',
    schedule: '2/2',
    status: 'published',
    criteria: [{ type: 'schedule', required: true, value: { schedule: '2/2' } }],
  },
]

function findVacancy(id: number): Vacancy {
  return vacancies.find((vacancy) => vacancy.id === id) ?? notFound('vacancy_not_found')
}

// ------------------------------------------------------- отклики кандидата

interface DemoApplication extends ApplicationSummary {
  failed_criteria: CriterionType[]
  answers: ScreeningAnswer[]
}

const candidateApplications: DemoApplication[] = [
  { id: 7, vacancy_id: 17, status: 'passed', created_at: atDay(-1, 10).toISOString(), failed_criteria: [], answers: [] },
  {
    id: 8,
    vacancy_id: 18,
    status: 'hard_filter_failed',
    created_at: atDay(-2, 12).toISOString(),
    failed_criteria: ['schedule'],
    answers: [],
  },
  { id: 9, vacancy_id: 19, status: 'mutual_interest', created_at: atDay(-3, 9).toISOString(), failed_criteria: [], answers: [] },
]

let nextApplicationId = 100

/** Вопросы первичного отбора строятся по условиям вакансии (3–4 в P0, раздел 18). */
interface DemoQuestion extends ScreeningQuestion {
  /** Какое условие проверяет вопрос — знает только backend (`must_equal`). */
  criterion: CriterionType | null
}

function questionsFor(vacancy: Vacancy): DemoQuestion[] {
  const questions: DemoQuestion[] = []
  const push = (question: string, required: boolean, criterion: CriterionType | null) =>
    questions.push({
      id: vacancy.id * 10 + questions.length + 1,
      question,
      type: 'boolean',
      required,
      sort_order: questions.length + 1,
      rules: {},
      criterion,
    })

  for (const criterion of vacancy.criteria) {
    if (criterion.type === 'schedule') {
      push(`Сможете работать по графику ${String(criterion.value.schedule)}?`, criterion.required, 'schedule')
    } else if (criterion.type === 'available_from') {
      push(`Готовы выйти на работу до ${formatDayMonth(String(criterion.value.date))}?`, criterion.required, 'available_from')
    } else if (criterion.type === 'certificate') {
      push(`Есть ли у вас ${String(criterion.value.name).toLowerCase()}?`, criterion.required, 'certificate')
    } else if (criterion.type === 'experience') {
      push(`У вас есть ${criterionLabel(criterion).toLowerCase()}?`, criterion.required, 'experience')
    }
  }
  push('Удобно выходить на смену с 08:00?', false, null)
  return questions.slice(0, 4)
}

function publicQuestion({ criterion: _criterion, ...question }: DemoQuestion): ScreeningQuestion {
  return question
}

function toCandidateApplication(application: DemoApplication): CandidateApplication {
  const { answers: _answers, ...rest } = application
  const match = matches.find((item) => item.application_id === application.id)
  return {
    ...rest,
    vacancy: findVacancy(application.vacancy_id),
    match_id: match?.id ?? null,
    interview_id: interviews.find((item) => item.application_id === application.id)?.id ?? null,
  }
}

function findCandidateApplication(id: number): DemoApplication {
  return candidateApplications.find((item) => item.id === id) ?? notFound('application_not_found')
}

/** `GET /api/vacancies/feed` — без вакансий, на которые уже есть отклик. */
export async function getFeed(signal?: AbortSignal): Promise<Vacancy[]> {
  const applied = new Set(candidateApplications.map((item) => item.vacancy_id))
  return respond(
    vacancies.filter((vacancy) => [12, 15, 16].includes(vacancy.id) && !applied.has(vacancy.id)),
    signal,
  )
}

/** `GET /api/vacancies/{id}`. */
export async function getVacancy(id: number, signal?: AbortSignal): Promise<Vacancy> {
  return respond(findVacancy(id), signal)
}

/** `POST /api/vacancies/{id}/apply` — повтор возвращает существующий отклик. */
export async function applyToVacancy(vacancyId: number, signal?: AbortSignal): Promise<ApplicationSummary> {
  const vacancy = findVacancy(vacancyId)
  if (vacancy.status !== 'published') {
    throw new ApiError(409, { code: 'vacancy_not_published', message: 'Вакансия закрыта' })
  }
  let application = candidateApplications.find((item) => item.vacancy_id === vacancyId)
  if (!application) {
    application = {
      id: nextApplicationId++,
      vacancy_id: vacancyId,
      status: 'screening',
      created_at: new Date().toISOString(),
      failed_criteria: [],
      answers: [],
    }
    candidateApplications.push(application)
  }
  const { id, vacancy_id, status, created_at } = application
  return respond({ id, vacancy_id, status, created_at }, signal)
}

/** Статус отклика для экранов C06/C07. */
export async function getCandidateApplication(id: number, signal?: AbortSignal): Promise<CandidateApplication> {
  return respond(toCandidateApplication(findCandidateApplication(id)), signal)
}

/** `GET /api/applications/{id}/screening`. */
export async function getScreening(applicationId: number, signal?: AbortSignal): Promise<ScreeningState> {
  const application = findCandidateApplication(applicationId)
  const vacancy = findVacancy(application.vacancy_id)
  return respond(
    {
      application_id: application.id,
      vacancy_id: vacancy.id,
      status: application.status,
      can_submit: application.status === 'screening',
      questions: questionsFor(vacancy).map(publicQuestion),
      answers: application.answers,
    },
    signal,
  )
}

/** `POST /api/applications/{id}/screening` — отбор отправляется целиком. */
export async function submitScreening(
  applicationId: number,
  answers: ScreeningAnswer[],
  signal?: AbortSignal,
): Promise<ScreeningResult> {
  const application = findCandidateApplication(applicationId)
  if (application.status !== 'screening') {
    throw new ApiError(409, { code: 'screening_already_completed', message: 'Отбор уже пройден' })
  }
  const questions = questionsFor(findVacancy(application.vacancy_id))
  const failed = questions.filter(
    (question) =>
      question.required &&
      question.criterion !== null &&
      answers.find((answer) => answer.question_id === question.id)?.value === false,
  )
  application.answers = answers
  application.status = failed.length > 0 ? 'hard_filter_failed' : 'passed'
  application.failed_criteria = failed.map((question) => question.criterion as CriterionType)
  return respond(
    {
      application_id: application.id,
      status: application.status as ScreeningResult['status'],
      failed_criteria: application.failed_criteria,
      failed_questions: failed.map((question) => question.id),
    },
    signal,
  )
}

// ------------------------------------------------------- match и интервью

const matches = [{ id: 3, application_id: 9, created_at: atDay(0, 9).toISOString() }]

function slotsSeed(vacancyId: number, firstId: number, days: number[], times: [number, number][]): InterviewSlot[] {
  const slots: InterviewSlot[] = []
  for (const day of days) {
    for (const [hours, minutes] of times) {
      const starts = atDay(day, hours, minutes)
      slots.push({
        id: firstId + slots.length,
        vacancy_id: vacancyId,
        starts_at: starts.toISOString(),
        ends_at: new Date(starts.getTime() + 30 * 60_000).toISOString(),
        status: 'available',
      })
    }
  }
  return slots
}

let slots: InterviewSlot[] = [
  ...slotsSeed(12, 500, [1], [
    [13, 0],
    [14, 0],
    [16, 30],
  ]),
  ...slotsSeed(19, 600, [1, 2, 3], [
    [13, 0],
    [14, 0],
    [16, 30],
    [18, 0],
  ]),
]
// Один слот вакансии 19 уже заняли — экран C09 его не показывает.
slots.find((slot) => slot.id === 605)!.status = 'booked'

const interviews: Interview[] = []
let nextSlotId = 1000
let nextInterviewId = 5

function pushInterview(matchId: number, applicationId: number, slot: InterviewSlot, notificationSent: boolean): Interview {
  slot.status = 'booked'
  const interview: Interview = {
    id: nextInterviewId++,
    match_id: matchId,
    slot_id: slot.id,
    status: 'scheduled',
    starts_at: slot.starts_at,
    ends_at: slot.ends_at,
    vacancy: findVacancy(slot.vacancy_id),
    application_id: applicationId,
    notification_sent: notificationSent,
  }
  interviews.push(interview)
  return interview
}

/** Match по отклику кандидата (раздел 21). */
export async function getMatch(id: number, signal?: AbortSignal): Promise<Match> {
  const match = matches.find((item) => item.id === id) ?? notFound('match_not_found')
  const application = findCandidateApplication(match.application_id)
  return respond({ ...match, vacancy: findVacancy(application.vacancy_id) }, signal)
}

/** `GET /api/vacancies/{id}/slots`. */
export async function getSlots(vacancyId: number, signal?: AbortSignal): Promise<InterviewSlot[]> {
  return respond(
    slots.filter((slot) => slot.vacancy_id === vacancyId && slot.status !== 'cancelled'),
    signal,
  )
}

/** `POST /api/vacancies/{id}/slots` — сохраняет набор свободных интервалов. */
export async function saveSlots(
  vacancyId: number,
  wanted: { starts_at: string; ends_at: string }[],
  signal?: AbortSignal,
): Promise<InterviewSlot[]> {
  const booked = slots.filter((slot) => slot.vacancy_id === vacancyId && slot.status === 'booked')
  const others = slots.filter((slot) => slot.vacancy_id !== vacancyId)
  const kept = wanted
    .filter((item) => !booked.some((slot) => slot.starts_at === item.starts_at))
    .map<InterviewSlot>((item) => ({ id: nextSlotId++, vacancy_id: vacancyId, status: 'available', ...item }))
  slots = [...others, ...booked, ...kept]
  return getSlots(vacancyId, signal)
}

/** `POST /api/matches/{id}/book` — занятый слот даёт `409 Conflict` (раздел 37). */
export async function bookSlot(matchId: number, slotId: number, signal?: AbortSignal): Promise<Interview> {
  const match = matches.find((item) => item.id === matchId) ?? notFound('match_not_found')
  const existing = interviews.find((item) => item.match_id === matchId)
  if (existing) return respond(existing, signal)
  const slot = slots.find((item) => item.id === slotId) ?? notFound('slot_not_found')
  if (slot.status !== 'available') {
    throw new ApiError(409, { code: 'slot_occupied', message: 'Этот интервал уже заняли' })
  }
  const interview = pushInterview(match.id, match.application_id, slot, true)
  const application = findCandidateApplication(match.application_id)
  application.status = 'interview_scheduled'
  return respond(interview, signal)
}

export async function getInterview(id: number, signal?: AbortSignal): Promise<Interview> {
  return respond(interviews.find((item) => item.id === id) ?? notFound('interview_not_found'), signal)
}

// ------------------------------------------------ сторона работодателя

const employerCandidates: EmployerCandidate[] = [
  {
    application_id: 21,
    status: 'passed',
    applied_at: atDay(0, 9, 40).toISOString(),
    desired_role: 'Бариста',
    city: 'Москва',
    salary: '85000.00',
    schedule: '2/2',
    experience_months: 16,
    available_from: isoDate(1),
    screening_answers: [
      { question_id: 121, question: 'Работа с кофемашиной', type: 'boolean', value: true },
      { question_id: 122, question: 'Смена с 08:00', type: 'boolean', value: true },
    ],
    hard_filters: [
      { type: 'schedule', required: true, passed: true },
      { type: 'location', required: true, passed: true },
      { type: 'available_from', required: true, passed: true },
    ],
  },
  {
    application_id: 22,
    status: 'passed',
    applied_at: atDay(0, 8, 15).toISOString(),
    desired_role: 'Бариста',
    city: 'Москва',
    salary: '75000.00',
    schedule: '2/2',
    experience_months: 8,
    available_from: isoDate(3),
    screening_answers: [
      { question_id: 121, question: 'Работа с кофемашиной', type: 'boolean', value: true },
      { question_id: 122, question: 'Смена с 08:00', type: 'boolean', value: false },
    ],
    hard_filters: [
      { type: 'schedule', required: true, passed: true },
      { type: 'location', required: true, passed: true },
      { type: 'available_from', required: true, passed: true },
    ],
  },
  {
    application_id: 23,
    status: 'passed',
    applied_at: atDay(-1, 19, 5).toISOString(),
    desired_role: 'Бариста',
    city: 'Москва',
    salary: '90000.00',
    schedule: '2/2',
    experience_months: 30,
    available_from: isoDate(0),
    screening_answers: [
      { question_id: 121, question: 'Работа с кофемашиной', type: 'boolean', value: true },
      { question_id: 122, question: 'Смена с 08:00', type: 'boolean', value: true },
    ],
    hard_filters: [
      { type: 'schedule', required: true, passed: true },
      { type: 'location', required: true, passed: true },
      { type: 'available_from', required: true, passed: null },
    ],
  },
  {
    application_id: 24,
    status: 'interview_scheduled',
    applied_at: atDay(-2, 11).toISOString(),
    desired_role: 'Бариста',
    city: 'Москва',
    salary: '80000.00',
    schedule: '2/2',
    experience_months: 12,
    available_from: isoDate(2),
    screening_answers: [{ question_id: 121, question: 'Работа с кофемашиной', type: 'boolean', value: true }],
    hard_filters: [
      { type: 'schedule', required: true, passed: true },
      { type: 'location', required: true, passed: true },
      { type: 'available_from', required: true, passed: true },
    ],
  },
  {
    application_id: 25,
    status: 'rejected',
    applied_at: atDay(-3, 15).toISOString(),
    desired_role: 'Бариста',
    city: 'Москва',
    salary: '110000.00',
    schedule: '2/2',
    experience_months: 4,
    available_from: isoDate(10),
    screening_answers: [],
    hard_filters: [
      { type: 'schedule', required: true, passed: true },
      { type: 'location', required: true, passed: true },
      { type: 'available_from', required: true, passed: true },
    ],
  },
]

// Интервью по отклику 24 уже назначено (слот вакансии 12 послезавтра в 11:00).
const seededSlot: InterviewSlot = {
  id: 499,
  vacancy_id: 12,
  starts_at: atDay(2, 11).toISOString(),
  ends_at: atDay(2, 11, 30).toISOString(),
  status: 'available',
}
slots.push(seededSlot)
pushInterview(2, 24, seededSlot, true)

/** Работодатель в демо один, его вакансия — 12. */
export const DEMO_EMPLOYER_VACANCY_ID = 12

/** «Кандидат 01» — порядковый номер отклика: имени в карточке P0 нет (api-contracts). */
export function candidateLabel(applicationId: number): string {
  const ordered = [...employerCandidates].sort((a, b) => a.applied_at.localeCompare(b.applied_at))
  const index = ordered.findIndex((item) => item.application_id === applicationId)
  return `Кандидат ${String(index + 1).padStart(2, '0')}`
}

/** `GET /api/employer/vacancies/{id}/candidates` — от новых к старым. */
export async function getVacancyCandidates(
  vacancyId: number,
  signal?: AbortSignal,
): Promise<{ vacancy: Vacancy; items: EmployerCandidate[] }> {
  const vacancy = findVacancy(vacancyId)
  const items = vacancyId === DEMO_EMPLOYER_VACANCY_ID ? employerCandidates : []
  return respond({ vacancy, items: [...items].sort((a, b) => b.applied_at.localeCompare(a.applied_at)) }, signal)
}

export interface EmployerApplicationView {
  vacancy: Vacancy
  candidate: EmployerCandidate
  /** Новые кандидаты очереди — для «1 из 3» и перехода к следующему. */
  queue: number[]
  interviewId: number | null
}

export async function getEmployerApplication(applicationId: number, signal?: AbortSignal): Promise<EmployerApplicationView> {
  const candidate = employerCandidates.find((item) => item.application_id === applicationId) ?? notFound('application_not_found')
  const queue = [...employerCandidates]
    .sort((a, b) => b.applied_at.localeCompare(a.applied_at))
    .filter((item) => item.status === 'passed' || item.application_id === applicationId)
    .map((item) => item.application_id)
  return respond(
    {
      vacancy: findVacancy(DEMO_EMPLOYER_VACANCY_ID),
      candidate,
      queue,
      interviewId: interviews.find((item) => item.application_id === applicationId)?.id ?? null,
    },
    signal,
  )
}

/** `POST /api/applications/{id}/decision` — решение принимается один раз. */
export async function decide(
  applicationId: number,
  action: 'invited' | 'rejected',
  signal?: AbortSignal,
): Promise<{ application_id: number; status: 'invited' | 'rejected' }> {
  const candidate = employerCandidates.find((item) => item.application_id === applicationId) ?? notFound('application_not_found')
  if (candidate.status !== 'passed') {
    throw new ApiError(409, { code: 'invalid_state_transition', message: 'Решение по кандидату уже принято' })
  }
  candidate.status = action
  return respond({ application_id: applicationId, status: action }, signal)
}

// ------------------------------------------------------ профиль кандидата

/** Форма `GET/PATCH /api/candidate/profile` (api-contracts). */
export interface CandidateProfileData {
  desired_role: string
  city: string | null
  salary: string | null
  schedule: string | null
  experience_months: number | null
  available_from: string | null
}

let candidateProfile: CandidateProfileData = {
  desired_role: 'Бариста',
  city: 'Москва',
  salary: '80000.00',
  schedule: '2/2',
  experience_months: 12,
  available_from: isoDate(1),
}

export async function getCandidateProfile(signal?: AbortSignal): Promise<CandidateProfileData> {
  return respond(candidateProfile, signal)
}

export async function saveCandidateProfile(
  profile: CandidateProfileData,
  signal?: AbortSignal,
): Promise<CandidateProfileData> {
  if (!profile.desired_role.trim()) {
    throw new ApiError(422, { code: 'desired_role_required', message: 'Укажите желаемую должность' })
  }
  candidateProfile = { ...profile, desired_role: profile.desired_role.trim() }
  return respond(candidateProfile, signal)
}
