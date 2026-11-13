import { useEffect, useRef, useState } from 'react'
import { ApiError, describeError, lookupBarcode } from './api'
import type { BarcodeProduct, BarcodeSource } from './api'
import { formatDecimal } from './format'
import { useI18n } from './i18n/context'

/** What a found product fills the new food form with; the source goes along, shown with it. */
export type BarcodePrefill = {
  name: string
  calories_per_100g: number | null
  protein_per_100g: number | null
  carbs_per_100g: number | null
  fat_per_100g: number | null
  source: BarcodeSource
}

/**
 * The ODbL attribution, wherever an Open Food Facts product shows: the
 * lookup's result and the form it fills (Andrei's condition).
 */
export function SourceCredit({ source }: { source: BarcodeSource }) {
  const { t } = useI18n()
  return (
    <p className="muted small source-credit">
      {t('barcode.credit', { who: source.attribution, license: source.license })}{' '}
      <a href={source.url} target="_blank" rel="noopener noreferrer">
        {t('barcode.creditLink')}
      </a>
    </p>
  )
}

type Detector = { detect: (source: HTMLVideoElement) => Promise<{ rawValue: string }[]> }
type DetectorClass = new (options: { formats: string[] }) => Detector

/** BarcodeDetector where the browser has one (Chrome on Android); null elsewhere (Safari). */
function detectorClass(): DetectorClass | null {
  const candidate = (window as unknown as { BarcodeDetector?: DetectorClass }).BarcodeDetector
  const camera = 'mediaDevices' in navigator && typeof navigator.mediaDevices.getUserMedia === 'function'
  return candidate && camera ? candidate : null
}

/**
 * The back camera, read until a barcode shows; the camera stops as soon as
 * one is found, the step closes, or the page goes.
 */
function Scanner({ onCode, onClose }: { onCode: (code: string) => void; onClose: () => void }) {
  const { t } = useI18n()
  const video = useRef<HTMLVideoElement>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const Detector = detectorClass()
    if (!Detector) return
    let stream: MediaStream | null = null
    let timer = 0
    let stopped = false
    const detector = new Detector({ formats: ['ean_13', 'ean_8', 'upc_a', 'upc_e'] })
    navigator.mediaDevices
      .getUserMedia({ video: { facingMode: 'environment' }, audio: false })
      .then(async (media) => {
        if (stopped) return media.getTracks().forEach((track) => track.stop())
        stream = media
        const element = video.current
        if (!element) return
        element.srcObject = media
        await element.play()
        const scan = async () => {
          if (stopped) return
          const found = await detector.detect(element).catch(() => [])
          if (found.length > 0) return onCode(found[0].rawValue)
          timer = window.setTimeout(() => void scan(), 250)
        }
        void scan()
      })
      .catch(() => setError(t('barcode.noCamera')))
    return () => {
      stopped = true
      window.clearTimeout(timer)
      stream?.getTracks().forEach((track) => track.stop())
    }
  }, [onCode, t])

  return (
    <div className="scanner">
      {error ? <p className="error">{error}</p> : <video ref={video} muted playsInline aria-label={t('barcode.camera')} />}
      <button type="button" className="link" onClick={onClose}>
        {t('barcode.stopCamera')}
      </button>
    </div>
  )
}

/**
 * Find a product by its barcode, from the camera or typed, and show what
 * Open Food Facts knows of it, credited. "Use these values" hands it to
 * the new food form; nothing is saved here.
 */
export function BarcodeLookup({ token, onUse }: { token: string; onUse: (prefill: BarcodePrefill) => void }) {
  const { t, locale } = useI18n()
  const [code, setCode] = useState('')
  const [scanning, setScanning] = useState(false)
  const [product, setProduct] = useState<BarcodeProduct | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const canScan = detectorClass() !== null

  async function lookUp(value: string) {
    const digits = value.replace(/\s/g, '')
    setCode(digits)
    setError(null)
    setProduct(null)
    setBusy(true)
    try {
      setProduct(await lookupBarcode(token, digits))
    } catch (err) {
      setError(err instanceof ApiError && err.code === 'product_not_found' ? t('barcode.notFound') : describeError(err))
    } finally {
      setBusy(false)
    }
  }

  const name = product ? (locale === 'ro' && product.name_ro) || product.name || product.barcode : ''
  const value = (v: number | null) => (v === null ? '—' : formatDecimal(v))

  return (
    <div className="panel barcode">
      <h3>{t('barcode.title')}</h3>
      {canScan && !scanning && (
        <button type="button" className="secondary" onClick={() => setScanning(true)}>
          {t('barcode.scan')}
        </button>
      )}
      {scanning && (
        <Scanner
          onCode={(found) => {
            setScanning(false)
            void lookUp(found)
          }}
          onClose={() => setScanning(false)}
        />
      )}
      {!canScan && <p className="muted small">{t('barcode.typeOnly')}</p>}
      <form
        className="barcode-form"
        onSubmit={(event) => {
          event.preventDefault()
          void lookUp(code)
        }}
      >
        <label>
          {t('barcode.code')}
          <input
            inputMode="numeric"
            autoComplete="off"
            pattern="[0-9 ]{8,16}"
            required
            value={code}
            onChange={(event) => setCode(event.target.value)}
          />
        </label>
        <button type="submit" disabled={busy}>
          {busy ? t('barcode.looking') : t('barcode.lookUp')}
        </button>
      </form>
      {error && <p className="error">{error}</p>}
      {product && (
        <div className="barcode-result" aria-live="polite">
          <p>
            <strong>{name}</strong>
            {(product.brand || product.quantity) && (
              <span className="muted"> · {[product.brand, product.quantity].filter(Boolean).join(' · ')}</span>
            )}
          </p>
          <p className="muted small">
            {t('barcode.per100', {
              kcal: value(product.calories_per_100g),
              protein: value(product.protein_per_100g),
              carbs: value(product.carbs_per_100g),
              fat: value(product.fat_per_100g),
            })}
          </p>
          {product.stale && <p className="notice small">{t('barcode.stale')}</p>}
          {!product.complete && <p className="muted small">{t('barcode.incomplete')}</p>}
          <SourceCredit source={product.source} />
          <button
            type="button"
            onClick={() =>
              onUse({
                name,
                calories_per_100g: product.calories_per_100g,
                protein_per_100g: product.protein_per_100g,
                carbs_per_100g: product.carbs_per_100g,
                fat_per_100g: product.fat_per_100g,
                source: product.source,
              })
            }
          >
            {t('barcode.use')}
          </button>
        </div>
      )}
    </div>
  )
}
