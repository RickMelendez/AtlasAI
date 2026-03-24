---
name: atlas-orb-animator
description: >
  Animate and enhance the Atlas AI orb to make it more alive, expressive, and interactive.
  Use this skill when the user wants to improve the orb's visual appearance, add new animation
  states, make it react to audio levels or voice, add particle effects, glow effects, breathing
  animations, or any visual enhancement to OrbCanvas.tsx. Combines ui-ux-pro-max design
  intelligence with frontend-design aesthetics. Use when the user says "make the orb better",
  "animate", "more alive", "more reactive", or any orb visual improvement request.
---

# Atlas Orb Animator

You enhance the Atlas orb — a Canvas-based particle animation that is the face of the app. Make it breathtaking, alive, and deeply reactive.

## Current Orb Architecture

**File**: `frontend/src/renderer/components/Orb/OrbCanvas.tsx`
- Uses Canvas API with `requestAnimationFrame` (never `setInterval`)
- Receives `state` prop: `'inactive' | 'active' | 'listening' | 'thinking' | 'speaking' | 'paused'`
- Receives `audioLevel` prop (0–1, updated ~30Hz from mic RMS)
- Receives `onClick` prop

## Color Palette (CSS variables in App.css)
```css
--orb-cyan:    #00D9FF   /* listening state */
--orb-purple:  #7B2FFF   /* thinking state */
--orb-pink:    #FF006E   /* speaking state */
--accent-green:#00FFA3   /* active/ready */
--paused-amber:#FFA500   /* paused state */
--bg-primary:  #0D0D0D   /* near-black background */
```

## State → Visual Mapping
| State | Feel | Key Visual |
|-------|------|-----------|
| inactive | dormant, slow | low opacity 0.3, barely moving |
| active | ready, breathing | normal speed, cyan glow, gentle pulse |
| listening | urgent, reactive | fast particles, pulsing cyan, reacts to audioLevel |
| thinking | complex, spinning | multi-color rotation, layered rings |
| speaking | rhythmic, alive | synchronized pulses to "speech rhythm" |
| paused | frozen, amber | near-static, slow amber drift |

## Enhancement Approaches

### 1. Breathing (subtle life at rest)
Add a slow sinusoidal scale pulse when `state === 'active'`:
```typescript
const breathe = Math.sin(Date.now() * 0.001) * 0.05 + 1.0  // 0.95–1.05 scale
```

### 2. Audio Reactivity (listening state)
`audioLevel` (0–1) should directly influence:
- Particle speed multiplier
- Outer glow radius
- Core brightness
- Particle count burst on high levels

### 3. Particle Systems
Create layered particle systems with different speeds, sizes, and orbits:
```typescript
interface Particle {
  angle: number       // current orbit angle
  radius: number      // orbit distance from center
  speed: number       // angular velocity
  size: number        // point size
  opacity: number     // fade in/out
  color: string       // RGBA
  layer: 0 | 1 | 2   // inner core / mid / outer halo
}
```

### 4. Glow and Bloom
Use multiple `shadowBlur` passes with increasing radius and decreasing opacity to simulate bloom:
```typescript
// Bloom pass
[40, 60, 80].forEach((blur, i) => {
  ctx.shadowBlur = blur
  ctx.shadowColor = currentColor
  ctx.globalAlpha = 0.3 - i * 0.08
  // draw core circle
})
```

### 5. Thinking State — DNA Helix / Spinning Rings
For the thinking state, render overlapping elliptical orbits at different angles, creating depth. Use `ctx.save()` / `ctx.restore()` with rotation transforms.

### 6. Speaking State — Waveform Pulse
Instead of random particles, drive a radial waveform using a simulated audio waveform:
```typescript
const wave = Math.sin(angle * frequency + phase) * amplitude * audioLevel
const r = baseRadius + wave
```

## Implementation Guide

### Read the current OrbCanvas.tsx FIRST
Before making any changes, read the full current implementation to understand existing state machines and particle logic. Don't break existing behavior — enhance it.

### Use requestAnimationFrame correctly
```typescript
const animate = () => {
  // update state
  // clear canvas
  // draw
  rafRef.current = requestAnimationFrame(animate)
}
// start
rafRef.current = requestAnimationFrame(animate)
// cleanup in useEffect return:
return () => cancelAnimationFrame(rafRef.current)
```

### Performance rules
- Keep particle count under 200 for smooth 60fps
- Use `ctx.globalCompositeOperation = 'screen'` for additive light blending
- Pre-calculate trigonometry tables if doing heavy per-frame trig
- `offscreenCanvas` for complex pre-rendered shapes

## Design Principles (from ui-ux-pro-max + frontend-design)

This orb is the SOUL of the app. It must feel:
- **Organic** — not mechanical, never perfectly symmetric unless frozen
- **Responsive** — the user should feel it reacting to their presence
- **Mysterious** — complex enough to stare at, simple enough to be calming
- **Premium** — every frame should look like it belongs in a high-end product demo

Commit to one strong aesthetic direction before coding. Options:
- **Bioluminescent** — deep ocean, slow pulsing, cold light
- **Plasma** — hot, electric, crackling energy at the edges
- **Crystalline** — geometric, faceted, light refraction effects
- **Nebula** — wispy, flowing, cosmic dust clouds

Make it unforgettable. This is the first thing every user sees.
