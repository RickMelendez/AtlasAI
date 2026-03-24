/**
 * OrbCanvas — Atlas AI Iridescent Chrome Glass Orb
 *
 * Renders a floating glass-like blob with liquid chrome iridescence:
 *  • Organic morphing blob — multi-frequency sine-wave deformation
 *  • Glass-like interior — nearly transparent with faint chromatic tint
 *  • Full-spectrum caustic light patterns — rainbow chrome refractions
 *  • Iridescent expanding ripple rings — color-shifting surface waves
 *  • Bright specular hotspot — drifting white highlight
 *  • Rainbow Fresnel edge shimmer — vivid oil-slick halo at boundary
 *  • Chromatic outer glow — slowly shifting rainbow ambient bloom
 *  • All state changes crossfade smoothly (0.5s)
 *  • Entrance animation: blob expands from 0 → target size over 400ms
 *
 * Reference: Liquid chrome / glass sphere aesthetic.
 * Slow, hypnotic, premium. Never chaotic or fast.
 */

import React, { useEffect, useRef } from 'react'
import './OrbCanvas.css'

// ── Props ─────────────────────────────────────────────────────────────────────

export interface OrbProps {
  state: 'inactive' | 'active' | 'listening' | 'thinking' | 'speaking' | 'paused'
  onClick?: () => void
  /** 0-1 mic/audio level — makes blob deform more, caustics brighter */
  audioLevel?: number
}

// ── Constants ─────────────────────────────────────────────────────────────────

const CANVAS_SIZE = 180
const CX          = CANVAS_SIZE / 2   // 90
const CY          = CANVAS_SIZE / 2   // 90
const BLOB_R      = 60                // nominal blob radius (px)
const N_BLOB_PTS  = 120               // polygon points for smooth blob
const CROSSFADE   = 0.5               // seconds for state crossfade

// ── Caustic light definitions ──────────────────────────────────────────────────
// Full-spectrum chrome refractions — rainbow iridescence inside the glass blob

const CAUSTICS = [
  { hue: 320, orbitR: 22, speed: 0.48, px: 0.40, py: 0.90, sz: 32 },  // hot pink
  { hue:  90, orbitR: 16, speed: 0.65, px: 1.90, py: 0.30, sz: 26 },  // lime green
  { hue: 185, orbitR: 24, speed: 0.42, px: 3.10, py: 1.60, sz: 36 },  // cyan
  { hue:  40, orbitR: 12, speed: 0.85, px: 0.70, py: 2.40, sz: 20 },  // gold/amber
  { hue: 260, orbitR: 18, speed: 0.58, px: 2.50, py: 0.80, sz: 24 },  // violet
  { hue: 160, orbitR: 13, speed: 0.35, px: 1.20, py: 3.10, sz: 28 },  // teal
] as const

// ── State configuration ────────────────────────────────────────────────────────

interface LiquidConfig {
  deformAmp:     number  // max deformation amplitude (px)
  deformSpeed:   number  // rad/s for blob deformation
  glowAlpha:     number  // opacity of outer ice-blue glow
  causticAlpha:  number  // opacity of interior caustic light patterns
  specularAlpha: number  // opacity of specular hotspot
  edgeWidth:     number  // stroke width of iridescent Fresnel edge
  pulseFreq:     number  // Hz for scale breathing (0 = none)
  pulseAmp:      number  // scale oscillation amplitude
}

const LIQUID_CONFIGS: Record<string, LiquidConfig> = {
  inactive:  { deformAmp: 4,  deformSpeed: 0.35, glowAlpha: 0.15, causticAlpha: 0.50, specularAlpha: 0.55, edgeWidth: 2.5, pulseFreq: 0.25, pulseAmp: 0.012 },
  active:    { deformAmp: 7,  deformSpeed: 0.55, glowAlpha: 0.25, causticAlpha: 0.65, specularAlpha: 0.72, edgeWidth: 3.0, pulseFreq: 0.40, pulseAmp: 0.020 },
  listening: { deformAmp: 12, deformSpeed: 0.90, glowAlpha: 0.40, causticAlpha: 0.82, specularAlpha: 0.88, edgeWidth: 3.5, pulseFreq: 1.2,  pulseAmp: 0.040 },
  thinking:  { deformAmp: 10, deformSpeed: 1.30, glowAlpha: 0.35, causticAlpha: 0.75, specularAlpha: 0.80, edgeWidth: 3.5, pulseFreq: 2.0,  pulseAmp: 0.045 },
  speaking:  { deformAmp: 16, deformSpeed: 1.80, glowAlpha: 0.50, causticAlpha: 0.90, specularAlpha: 0.95, edgeWidth: 4.5, pulseFreq: 3.0,  pulseAmp: 0.065 },
  paused:    { deformAmp: 3,  deformSpeed: 0.20, glowAlpha: 0.08, causticAlpha: 0.35, specularAlpha: 0.38, edgeWidth: 2.0, pulseFreq: 0.15, pulseAmp: 0.008 },
}

// ── Interpolation helpers ──────────────────────────────────────────────────────

function lerp(a: number, b: number, t: number): number { return a + (b - a) * t }

function smoothstep(t: number): number {
  t = Math.max(0, Math.min(1, t))
  return t * t * (3 - 2 * t)
}

function lerpConfig(a: LiquidConfig, b: LiquidConfig, rawT: number): LiquidConfig {
  const t = smoothstep(rawT)
  return {
    deformAmp:     lerp(a.deformAmp,     b.deformAmp,     t),
    deformSpeed:   lerp(a.deformSpeed,   b.deformSpeed,   t),
    glowAlpha:     lerp(a.glowAlpha,     b.glowAlpha,     t),
    causticAlpha:  lerp(a.causticAlpha,  b.causticAlpha,  t),
    specularAlpha: lerp(a.specularAlpha, b.specularAlpha, t),
    edgeWidth:     lerp(a.edgeWidth,     b.edgeWidth,     t),
    pulseFreq:     lerp(a.pulseFreq,     b.pulseFreq,     t),
    pulseAmp:      lerp(a.pulseAmp,      b.pulseAmp,      t),
  }
}

// ── Blob helpers ───────────────────────────────────────────────────────────────

/**
 * Generate N polygon points by deforming a circle with overlapping sine waves.
 * 6 prime-frequency components create a never-repeating organic shape.
 */
function getBlobPoints(
  t: number,
  cfg: LiquidConfig,
  scale: number,
  audioLevel: number,
): [number, number][] {
  const amp = (cfg.deformAmp + audioLevel * 10) * scale
  const spd = cfg.deformSpeed
  const pts: [number, number][] = []
  for (let i = 0; i < N_BLOB_PTS; i++) {
    const angle = (i / N_BLOB_PTS) * Math.PI * 2
    let r = BLOB_R * scale
    r += amp * 0.35 * Math.sin(2  * angle + t * spd * 1.00)
    r += amp * 0.25 * Math.sin(3  * angle - t * spd * 1.30)
    r += amp * 0.20 * Math.sin(5  * angle + t * spd * 0.70)
    r += amp * 0.12 * Math.sin(7  * angle - t * spd * 1.70)
    r += amp * 0.05 * Math.sin(11 * angle + t * spd * 2.10)
    r += amp * 0.03 * Math.sin(13 * angle - t * spd * 0.90)
    pts.push([CX + r * Math.cos(angle), CY + r * Math.sin(angle)])
  }
  return pts
}

/** Trace the blob polygon as a closed path on ctx (no fill/stroke). */
function traceBlobPath(ctx: CanvasRenderingContext2D, pts: [number, number][]): void {
  ctx.beginPath()
  ctx.moveTo(pts[0][0], pts[0][1])
  for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i][0], pts[i][1])
  ctx.closePath()
}

// ── Draw functions ─────────────────────────────────────────────────────────────

/**
 * Chromatic rainbow glow behind the blob.
 * Hue drifts through full spectrum slowly (~20s cycle) for chrome effect.
 */
function drawOuterGlow(
  ctx: CanvasRenderingContext2D,
  cfg: LiquidConfig,
  t: number,
  audioLevel: number,
): void {
  const hue   = (t * 18) % 360  // full spectrum drift
  const r     = BLOB_R * 1.60
  const alpha = Math.min(1, cfg.glowAlpha * (1 + audioLevel * 0.5))
  const grad  = ctx.createRadialGradient(CX, CY, BLOB_R * 0.4, CX, CY, r)
  grad.addColorStop(0,   `hsla(${hue},80%,75%,${alpha.toFixed(2)})`)
  grad.addColorStop(0.4, `hsla(${(hue + 30) % 360},70%,70%,${(alpha * 0.30).toFixed(2)})`)
  grad.addColorStop(1,   `hsla(${(hue + 60) % 360},60%,65%,0)`)
  ctx.fillStyle = grad
  ctx.beginPath()
  ctx.arc(CX, CY, r, 0, Math.PI * 2)
  ctx.fill()
}

/**
 * Iridescent expanding ripple rings — each ring a different hue.
 * 3 rings in phase, period 2s each, fade as they expand.
 */
function drawRipples(
  ctx: CanvasRenderingContext2D,
  t: number,
  scale: number,
  cfg: LiquidConfig,
): void {
  const baseAlpha = cfg.glowAlpha * 0.9
  ctx.save()
  for (let i = 0; i < 3; i++) {
    const phase    = (t + i * 0.67) % 2.0   // 2s period, staggered 0.67s apart
    const progress = phase / 2.0             // 0→1
    const r        = BLOB_R * scale * (0.18 + progress * 0.90)
    const a        = baseAlpha * (1 - progress) * 0.45
    if (a < 0.01 || r < 2) continue
    const hue = ((t * 18) + i * 120 + progress * 60) % 360
    ctx.beginPath()
    ctx.arc(CX, CY, r, 0, Math.PI * 2)
    ctx.strokeStyle = `hsla(${hue},70%,80%,${a.toFixed(2)})`
    ctx.lineWidth   = Math.max(0.5, 1.8 * (1 - progress))
    ctx.stroke()
  }
  ctx.restore()
}

/**
 * Glass interior — nearly transparent with faint warm→cool chromatic shift.
 * The desktop shows through this layer like light through chrome glass.
 */
function drawBlobBase(
  ctx: CanvasRenderingContext2D,
  pts: [number, number][],
): void {
  ctx.save()
  traceBlobPath(ctx, pts)
  ctx.clip()
  // Off-center highlight for refractive depth illusion
  const grad = ctx.createRadialGradient(CX - 12, CY - 18, 0, CX, CY, BLOB_R * 1.2)
  grad.addColorStop(0,    'rgba(255, 250, 245, 0.10)')  // warm white center
  grad.addColorStop(0.35, 'rgba(240, 235, 255, 0.06)')  // faint violet mid
  grad.addColorStop(0.70, 'rgba(230, 248, 255, 0.08)')  // cool blue toward edge
  grad.addColorStop(1,    'rgba(220, 240, 255, 0.14)')  // slightly denser edge
  ctx.fillStyle = grad
  ctx.fill()
  ctx.restore()
}

/**
 * Bright caustic light patterns — light refracting through water glass.
 * Fast-moving bright spots on screen composite: they add light, never darken.
 */
function drawCaustics(
  ctx: CanvasRenderingContext2D,
  pts: [number, number][],
  t: number,
  cfg: LiquidConfig,
  audioLevel: number,
): void {
  ctx.save()
  traceBlobPath(ctx, pts)
  ctx.clip()
  ctx.globalCompositeOperation = 'screen'
  for (const c of CAUSTICS) {
    const px  = CX + c.orbitR * Math.cos(t * c.speed + c.px)
    const py  = CY + c.orbitR * 0.65 * Math.sin(t * c.speed + c.py)
    const sz  = c.sz * (1 + audioLevel * 0.35)
    const a0  = (cfg.causticAlpha * 0.85).toFixed(2)
    const a1  = (cfg.causticAlpha * 0.30).toFixed(2)
    const grad = ctx.createRadialGradient(px, py, 0, px, py, sz)
    grad.addColorStop(0,    `hsla(${c.hue},100%,95%,${a0})`)  // bright white core
    grad.addColorStop(0.40, `hsla(${c.hue}, 90%,75%,${a1})`)  // strong tinted halo
    grad.addColorStop(1,    'hsla(0,0%,0%,0)')
    ctx.fillStyle = grad
    ctx.beginPath()
    ctx.ellipse(px, py, sz, sz * 0.72, t * c.speed * 0.25, 0, Math.PI * 2)
    ctx.fill()
  }
  ctx.globalCompositeOperation = 'source-over'
  ctx.restore()
}

/**
 * Single bright white specular highlight drifting across the surface.
 * Like a point of light reflected off the curved water surface.
 */
function drawSpecular(
  ctx: CanvasRenderingContext2D,
  pts: [number, number][],
  t: number,
  cfg: LiquidConfig,
  audioLevel: number,
): void {
  ctx.save()
  traceBlobPath(ctx, pts)
  ctx.clip()
  ctx.globalCompositeOperation = 'screen'
  const sx    = CX + 16 * Math.cos(t * 0.11) - 8
  const sy    = CY - 18 + 11 * Math.sin(t * 0.09)
  const alpha = Math.min(1, cfg.specularAlpha * (1 + audioLevel * 0.25))
  const grad  = ctx.createRadialGradient(sx, sy, 0, sx, sy, 26)
  grad.addColorStop(0,   `rgba(255,255,255,${alpha.toFixed(2)})`)
  grad.addColorStop(0.35,`rgba(220,245,255,${(alpha * 0.40).toFixed(2)})`)
  grad.addColorStop(1,   'rgba(0,0,0,0)')
  ctx.fillStyle = grad
  ctx.beginPath()
  ctx.ellipse(sx, sy, 26, 17, -0.4, 0, Math.PI * 2)
  ctx.fill()
  ctx.globalCompositeOperation = 'source-over'
  ctx.restore()
}

/**
 * Rainbow Fresnel edge shimmer — iridescent halo on the water droplet boundary.
 * Hue sweeps 0→360° around the perimeter and drifts slowly with time.
 */
function drawIridescentEdge(
  ctx: CanvasRenderingContext2D,
  pts: [number, number][],
  cfg: LiquidConfig,
  t: number,
): void {
  const hueOffset = (t * 35) % 360  // faster drift for chrome effect
  ctx.save()
  ctx.lineWidth  = cfg.edgeWidth
  ctx.shadowBlur = cfg.edgeWidth * 3.5
  for (let i = 0; i < N_BLOB_PTS; i++) {
    const hue = (hueOffset + (i / N_BLOB_PTS) * 360) % 360
    const [x1, y1] = pts[i]
    const [x2, y2] = pts[(i + 1) % N_BLOB_PTS]
    ctx.strokeStyle = `hsla(${hue},100%,88%,0.95)`  // brighter, more vivid
    ctx.shadowColor = `hsla(${hue},100%,75%,0.65)`  // stronger glow
    ctx.beginPath()
    ctx.moveTo(x1, y1)
    ctx.lineTo(x2, y2)
    ctx.stroke()
  }
  ctx.shadowBlur = 0
  ctx.restore()
}

// ── Component ──────────────────────────────────────────────────────────────────

export const OrbCanvas: React.FC<OrbProps> = ({ state, onClick, audioLevel = 0 }) => {
  const canvasRef  = useRef<HTMLCanvasElement>(null)
  const animRef    = useRef<number>()
  const lastTsRef  = useRef<number | null>(null)
  const timeRef    = useRef(0)
  const introRef   = useRef(0)          // 0 → 1 entrance animation progress
  const audioRef   = useRef(audioLevel)

  // Crossfade between liquid configs
  const fromCfgRef = useRef<LiquidConfig>(LIQUID_CONFIGS.active)
  const toCfgRef   = useRef<LiquidConfig>(LIQUID_CONFIGS.active)
  const fadeRef    = useRef(1.0)

  // Update crossfade when state changes
  useEffect(() => {
    const next = LIQUID_CONFIGS[state] ?? LIQUID_CONFIGS.active
    if (next !== toCfgRef.current) {
      fromCfgRef.current = lerpConfig(fromCfgRef.current, toCfgRef.current, fadeRef.current)
      toCfgRef.current   = next
      fadeRef.current    = 0
    }
  }, [state])

  useEffect(() => { audioRef.current = audioLevel }, [audioLevel])

  // Single RAF animation loop — empty deps: runs once, reads everything from refs
  useEffect(() => {
    const animate = (ts: number) => {
      // Reschedule first so draw errors never kill the loop
      animRef.current = requestAnimationFrame(animate)

      if (lastTsRef.current === null) lastTsRef.current = ts
      const dt = Math.min(ts - lastTsRef.current, 50) / 1000   // seconds, max 50ms
      lastTsRef.current = ts

      const canvas = canvasRef.current
      if (!canvas) return
      const ctx = canvas.getContext('2d')
      if (!ctx) return

      try {
        // Entrance animation: 0→1 over 400ms
        introRef.current = Math.min(1, introRef.current + dt / 0.4)

        // Advance crossfade
        fadeRef.current = Math.min(1, fadeRef.current + dt / CROSSFADE)

        const cfg = lerpConfig(fromCfgRef.current, toCfgRef.current, fadeRef.current)
        const al  = audioRef.current

        timeRef.current += dt
        const t = timeRef.current

        // Effective scale: entrance ease × state breathing pulse
        const introEase = smoothstep(introRef.current)
        const pulse     = cfg.pulseFreq > 0
          ? 1 + Math.sin(t * cfg.pulseFreq * Math.PI * 2) * cfg.pulseAmp
          : 1
        const scale = introEase * pulse

        // ── Clear to transparent ─────────────────────────────────────────────
        // Electron window is transparent — desktop shows through empty pixels.
        ctx.clearRect(0, 0, CANVAS_SIZE, CANVAS_SIZE)

        if (scale < 0.05) return  // too small during intro

        // Pre-compute blob outline (all draw layers share it)
        const pts = getBlobPoints(t, cfg, scale, al)

        // ── 1. Ice-blue outer glow ───────────────────────────────────────────
        drawOuterGlow(ctx, cfg, t, al)

        // ── 2. Expanding ripple rings ────────────────────────────────────────
        drawRipples(ctx, t, scale, cfg)

        // ── 3. Crystal ice interior (clips to blob) ──────────────────────────
        drawBlobBase(ctx, pts)

        // ── 4. Caustic light patterns (screen composite, inside blob) ────────
        drawCaustics(ctx, pts, t, cfg, al)

        // ── 5. Specular hotspot (screen composite, inside blob) ──────────────
        drawSpecular(ctx, pts, t, cfg, al)

        // ── 6. Iridescent Fresnel edge shimmer ───────────────────────────────
        drawIridescentEdge(ctx, pts, cfg, t)

      } catch (_) { /* swallow canvas draw errors — RAF already rescheduled */ }
    }

    animRef.current = requestAnimationFrame(animate)
    return () => { if (animRef.current) cancelAnimationFrame(animRef.current) }
  }, [])  // ← intentionally empty: loop runs once and reads refs

  return (
    <div className="orb-canvas-container" onClick={onClick}>
      <canvas
        ref={canvasRef}
        width={CANVAS_SIZE}
        height={CANVAS_SIZE}
        className="orb-canvas"
      />
    </div>
  )
}
