import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { routes } from '@/app/routes'
import { transcribeVacancy } from '@/api/ai'
import { BackButton } from '@/components/BackButton'
import { MicIcon } from '@/components/icons'
import { useParseVacancy } from '@/features/vacancyCreate/useParseVacancy'
import { useVacancyDraft } from '@/features/vacancyCreate/useVacancyDraft'
import { toWav } from '@/lib/wav'
import './VacancyVoicePage.css'

type Phase = 'starting' | 'recording' | 'transcribing' | 'done' | 'error'

/**
 * Высоты полос «волны» из макета (px при 390pt), от центра к краям.
 * Во время записи каждая полоса масштабируется громкостью голоса.
 */
const LEFT_BARS = [18, 43, 50, 96, 155, 121, 41, 32, 59, 41, 23, 4, 4, 4]
const RIGHT_BARS = [18, 41, 59, 50, 121, 155, 123, 82, 50, 25, 18, 18, 4, 4]

/**
 * SpeechKit распознаёт короткое аудио синхронно (до ~30 с / 1 МБ WAV) —
 * запись останавливается сама, чтобы не упереться в этот предел.
 */
const MAX_SECONDS = 30

const UNSUPPORTED_TEXT = 'В этом приложении запись голоса недоступна. Опишите вакансию текстом.'

function canRecord(): boolean {
  return Boolean(navigator.mediaDevices?.getUserMedia) && typeof MediaRecorder !== 'undefined'
}

/**
 * E13 «Голосовое создание вакансии» (P1, функция 17). Запись →
 * `POST /ai/transcribe-vacancy` → транскрипт → тот же разбор, что у текста
 * (E12). Ошибка микрофона или распознавания — предложение ввести текстом.
 */
export function VacancyVoicePage() {
  const navigate = useNavigate()
  const { updateDraft } = useVacancyDraft()
  const { parse, parsing, error: parseError } = useParseVacancy()
  const [phase, setPhase] = useState<Phase>(() => (canRecord() ? 'starting' : 'error'))
  const [seconds, setSeconds] = useState(0)
  const [transcript, setTranscript] = useState('')
  const [error, setError] = useState<string | null>(() => (canRecord() ? null : UNSUPPORTED_TEXT))

  const recorderRef = useRef<MediaRecorder | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const audioRef = useRef<AudioContext | null>(null)
  const frameRef = useRef(0)
  const barsRef = useRef<HTMLSpanElement[]>([])
  // Номер запуска записи: ответ getUserMedia от уже закрытого экрана
  // (или от первого прохода эффекта в StrictMode) не должен включать запись.
  const sessionRef = useRef(0)

  const releaseMic = useCallback(() => {
    cancelAnimationFrame(frameRef.current)
    streamRef.current?.getTracks().forEach((track) => track.stop())
    streamRef.current = null
    void audioRef.current?.close().catch(() => undefined)
    audioRef.current = null
    barsRef.current.forEach((bar) => bar && (bar.style.transform = ''))
  }, [])

  const transcribe = useCallback(async (recording: Blob) => {
    setPhase('transcribing')
    try {
      const result = await transcribeVacancy(await toWav(recording))
      if (!result.text.trim()) {
        setError('Не получилось распознать речь. Попробуйте еще раз или напишите текстом.')
        setPhase('error')
        return
      }
      setTranscript(result.text.trim())
      setPhase('done')
    } catch {
      setError('Не удалось отправить запись. Проверьте связь и попробуйте еще раз.')
      setPhase('error')
    }
  }, [])

  const animateBars = useCallback((stream: MediaStream) => {
    const context = new AudioContext()
    audioRef.current = context
    const analyser = context.createAnalyser()
    analyser.fftSize = 512
    context.createMediaStreamSource(stream).connect(analyser)
    const samples = new Uint8Array(analyser.fftSize)

    const tick = (time: number) => {
      analyser.getByteTimeDomainData(samples)
      let sum = 0
      for (const sample of samples) sum += ((sample - 128) / 128) ** 2
      const level = Math.min(1, Math.sqrt(sum / samples.length) * 5)
      barsRef.current.forEach((bar, index) => {
        if (!bar) return
        const wobble = 0.55 + 0.45 * Math.sin(time / 140 + index * 1.7)
        bar.style.transform = `scaleY(${(0.3 + 0.7 * level * wobble).toFixed(3)})`
      })
      frameRef.current = requestAnimationFrame(tick)
    }
    frameRef.current = requestAnimationFrame(tick)
  }, [])

  /** Включает микрофон и запись; состояние экрана сбрасывает вызывающий. */
  const start = useCallback(() => {
    if (!canRecord()) return
    const session = ++sessionRef.current
    navigator.mediaDevices.getUserMedia({ audio: true }).then(
      (stream) => {
        if (session !== sessionRef.current) {
          stream.getTracks().forEach((track) => track.stop())
          return
        }
        streamRef.current = stream
        let recorder: MediaRecorder
        try {
          recorder = new MediaRecorder(stream)
        } catch {
          releaseMic()
          setError(UNSUPPORTED_TEXT)
          setPhase('error')
          return
        }
        const chunks: Blob[] = []
        recorder.ondataavailable = (event) => event.data.size > 0 && chunks.push(event.data)
        recorder.onstop = () => {
          releaseMic()
          void transcribe(new Blob(chunks, { type: recorder.mimeType }))
        }
        recorderRef.current = recorder
        recorder.start()
        animateBars(stream)
        setPhase('recording')
      },
      () => {
        if (session !== sessionRef.current) return
        releaseMic()
        setError('Нет доступа к микрофону. Разрешите его в настройках или опишите вакансию текстом.')
        setPhase('error')
      },
    )
  }, [animateBars, releaseMic, transcribe])

  const stop = useCallback(() => {
    if (recorderRef.current?.state === 'recording') recorderRef.current.stop()
  }, [])

  // Запись начинается сразу: на экран попадают кнопкой микрофона на E11.
  useEffect(() => {
    start()
    return () => {
      sessionRef.current += 1
      const recorder = recorderRef.current
      if (recorder && recorder.state === 'recording') {
        recorder.onstop = null
        recorder.stop()
      }
      releaseMic()
    }
  }, [start, releaseMic])

  useEffect(() => {
    if (phase !== 'recording') return
    const timer = window.setInterval(() => setSeconds((value) => value + 1), 1000)
    return () => window.clearInterval(timer)
  }, [phase])

  useEffect(() => {
    if (phase === 'recording' && seconds >= MAX_SECONDS) stop()
  }, [phase, seconds, stop])

  function restart() {
    if (!canRecord()) return
    setError(null)
    setTranscript('')
    setSeconds(0)
    setPhase('starting')
    start()
  }

  function handleMic() {
    if (phase === 'recording') stop()
    else if (phase === 'done' || phase === 'error') restart()
  }

  function handleContinue() {
    if (phase === 'recording') {
      stop()
      return
    }
    if (phase === 'done') {
      updateDraft({ sourceText: transcript })
      void parse(transcript)
    }
  }

  const clock = `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`
  const statusLine =
    phase === 'recording'
      ? `Запись · ${clock}`
      : phase === 'transcribing'
        ? 'Распознаем…'
        : phase === 'done'
          ? `Готово · ${clock}`
          : phase === 'starting'
            ? 'Включаем микрофон…'
            : 'Запись остановлена'

  let barIndex = 0
  const renderBars = (heights: number[]) =>
    heights.map((height, index) => {
      const ref = barIndex++
      return (
        <span
          key={index}
          ref={(node) => {
            if (node) barsRef.current[ref] = node
          }}
          className={`voice__bar${height <= 4 ? ' voice__bar--dot' : ''}`}
          style={{ height }}
        />
      )
    })

  return (
    <div className="p1Screen voice">
      <div className="p1Top p1Top--centered voice__top">
        <BackButton variant="raised" onClick={() => navigate(routes.employerVacancyAi)} />
        <span className="p1Top__title">Голосом</span>
      </div>

      <h1 className="p1Title voice__title">
        Расскажите,
        <br />
        кто вам нужен
      </h1>
      <p className="p1Subtitle voice__subtitle">Говорите свободно</p>

      <div className="voice__stage">
        <span className="voice__status" aria-live="polite">
          {statusLine}
        </span>
        <div className={`voice__wave${phase === 'recording' ? ' voice__wave--live' : ''}`}>
          <div className="voice__bars voice__bars--left">{renderBars([...LEFT_BARS].reverse())}</div>
          <button
            type="button"
            className="voice__mic"
            aria-label={phase === 'recording' ? 'Остановить запись' : 'Записать заново'}
            disabled={phase === 'starting' || phase === 'transcribing'}
            onClick={handleMic}
          >
            <MicIcon size={44} strokeWidth={1.9} />
          </button>
          <div className="voice__bars">{renderBars(RIGHT_BARS)}</div>
        </div>
      </div>

      <section className="voice__sheet">
        <span className="voice__handle" aria-hidden="true" />
        <span className="voice__chip">
          {phase === 'done' ? 'Распознали' : phase === 'error' ? 'Не получилось' : phase === 'transcribing' ? 'Распознаем' : 'Слушаем'}
        </span>

        {phase === 'done' ? (
          <p className="voice__transcript">{transcript}</p>
        ) : phase === 'error' ? (
          <p className="voice__transcript voice__transcript--muted">{error}</p>
        ) : (
          <p className="voice__transcript voice__transcript--muted">
            Должность, место, график, зарплата и когда выйти
          </p>
        )}
        <p className="voice__hint">
          {phase === 'recording'
            ? 'Нажмите на микрофон, когда закончите'
            : phase === 'error'
              ? 'Можно записать заново'
              : 'Текст можно будет исправить'}
        </p>

        {parseError ? <p className="p1Error voice__error">{parseError}</p> : null}

        {phase === 'error' ? (
          <button type="button" className="p1Button voice__button" disabled={!canRecord()} onClick={restart}>
            Записать заново
          </button>
        ) : (
          <button
            type="button"
            className="p1Button voice__button"
            disabled={phase === 'starting' || phase === 'transcribing' || parsing}
            onClick={handleContinue}
          >
            {parsing ? 'Разбираем…' : 'Продолжить'}
          </button>
        )}
        <button type="button" className="p1Link voice__cancel" onClick={() => navigate(routes.employerVacancyAi)}>
          {phase === 'error' ? 'Написать текстом' : 'Отмена'}
        </button>
      </section>
    </div>
  )
}
