/**
 * Перекодирование записи микрофона в WAV (16 кГц, моно, PCM16).
 *
 * Браузеры пишут голос в разные контейнеры (Chrome — WebM/Opus, Safari —
 * MP4/AAC), а `POST /ai/transcribe-vacancy` понимает OGG/MP3/WAV. WAV —
 * единственный из них, который браузер умеет собрать сам без кодеков.
 */
const SAMPLE_RATE = 16_000

export async function toWav(recording: Blob): Promise<Blob> {
  const context = new AudioContext()
  try {
    const decoded = await context.decodeAudioData(await recording.arrayBuffer())
    const length = Math.max(1, Math.ceil(decoded.duration * SAMPLE_RATE))
    const offline = new OfflineAudioContext(1, length, SAMPLE_RATE)
    const source = offline.createBufferSource()
    source.buffer = decoded
    source.connect(offline.destination)
    source.start()
    const rendered = await offline.startRendering()
    return encodeWav(rendered.getChannelData(0))
  } finally {
    void context.close()
  }
}

function encodeWav(samples: Float32Array): Blob {
  const buffer = new ArrayBuffer(44 + samples.length * 2)
  const view = new DataView(buffer)
  const writeText = (offset: number, text: string) => {
    for (let index = 0; index < text.length; index += 1) view.setUint8(offset + index, text.charCodeAt(index))
  }

  writeText(0, 'RIFF')
  view.setUint32(4, 36 + samples.length * 2, true)
  writeText(8, 'WAVE')
  writeText(12, 'fmt ')
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true) // PCM
  view.setUint16(22, 1, true) // моно
  view.setUint32(24, SAMPLE_RATE, true)
  view.setUint32(28, SAMPLE_RATE * 2, true)
  view.setUint16(32, 2, true)
  view.setUint16(34, 16, true)
  writeText(36, 'data')
  view.setUint32(40, samples.length * 2, true)

  let offset = 44
  for (const sample of samples) {
    const clamped = Math.max(-1, Math.min(1, sample))
    view.setInt16(offset, clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff, true)
    offset += 2
  }
  return new Blob([buffer], { type: 'audio/wav' })
}
