import boardCandidate1 from '@/assets/board-candidate-1.webp'
import boardCandidate2 from '@/assets/board-candidate-2.webp'
import reserveCandidate1 from '@/assets/reserve-candidate-1.webp'
import reserveCandidate2 from '@/assets/reserve-candidate-2.webp'
import reserveCandidate3 from '@/assets/reserve-candidate-3.webp'

/**
 * Фотографии кандидатов из макетов P1 (E15, E16).
 *
 * Это оформление экрана, а не фото конкретного человека: карточка кандидата
 * работодателю (раздел 34) фото не содержит, а анонимная карточка P1
 * (раздел 63) скрывает его до взаимного интереса. Поэтому картинка
 * выбирается стабильно по id отклика, чтобы у одного кандидата она не
 * менялась между экранами. Когда backend начнёт отдавать разрешённое фото,
 * его нужно подставить вместо этой заглушки.
 */
const THUMBNAILS = [boardCandidate1, boardCandidate2]
const PORTRAITS = [reserveCandidate1, reserveCandidate2, reserveCandidate3]

/** Квадратное превью для строки доски найма (E15). */
export function candidateThumbnail(applicationId: number): string {
  return THUMBNAILS[applicationId % THUMBNAILS.length]
}

/** Вертикальный портрет для карточки резерва (E16). */
export function candidatePortrait(applicationId: number): string {
  return PORTRAITS[applicationId % PORTRAITS.length]
}
