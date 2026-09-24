import { useState } from 'react'

/**
 * Фото вакансии (`image_url` — случайное фото по теме, backend подбирает его
 * сам). Лежит под содержимым своего `.photoSlot`; если ссылки нет или она не
 * открылась, остаётся заглушка слота — карточка не ломается.
 */
export function CoverImage({ url }: { url: string | null | undefined }) {
  const [failedUrl, setFailedUrl] = useState<string | null>(null)
  if (!url || failedUrl === url) return null
  return (
    <img
      className="photoSlot__cover"
      src={url}
      alt=""
      aria-hidden="true"
      loading="lazy"
      decoding="async"
      referrerPolicy="no-referrer"
      onError={() => setFailedUrl(url)}
    />
  )
}
