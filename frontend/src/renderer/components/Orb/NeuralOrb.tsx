/**
 * NeuralOrb — JARVIS-style Flowing Constellation Orb
 *
 * 180 glowing atom-nodes on a sphere, connected by luminous energy threads.
 * State transitions are fluid — nodes drift between shapes organically,
 * never "exploding" outward. The orb breathes, pulses, and morphs
 * like a living neural field.
 *
 *   inactive  → dim deep-blue sphere, slow drift, sparse connections
 *   active    → cyan sphere, gentle breathe, medium glow
 *   listening → nodes spread into open lattice, audio-reactive ripple
 *   thinking  → nodes warp to torus, fast chaotic micro-motion
 *   speaking  → radial wave pulses propagate through nodes
 *   paused    → amber dense sphere, near-static
 */

import React, { useEffect, useRef } from 'react'
import * as THREE from 'three'
import './OrbCanvas.css'

export interface NeuralOrbProps {
  state: 'inactive' | 'active' | 'listening' | 'thinking' | 'speaking' | 'paused'
  onClick?: () => void
  audioLevel?: number
}

// ── State configs ──────────────────────────────────────────────────────────────

interface StateConfig {
  nodeColor:   string
  lineColor:   string
  glowColor:   string
  nodeSize:    number   // base point size multiplier
  lineOpacity: number
  rotSpeed:    number   // rad/s
  pulseHz:     number   // breathing frequency
  pulseAmp:    number   // breathing amplitude
  morphSpeed:  number   // how fast nodes flow toward target shape (0-1 per sec)
  radius:      number   // sphere radius of target shape
}

const STATES: Record<string, StateConfig> = {
  inactive: {
    nodeColor:'#1a4a8a', lineColor:'#0e2d5a', glowColor:'#0a1f4a',
    nodeSize:0.55, lineOpacity:0.04, rotSpeed:0.08, pulseHz:0.18,
    pulseAmp:0.015, morphSpeed:0.8, radius:1.4,
  },
  active: {
    nodeColor:'#00C4E8', lineColor:'#00A8CC', glowColor:'#00D9FF',
    nodeSize:0.75, lineOpacity:0.10, rotSpeed:0.30, pulseHz:0.30,
    pulseAmp:0.022, morphSpeed:1.2, radius:1.4,
  },
  listening: {
    nodeColor:'#7FFFFF', lineColor:'#00FFEE', glowColor:'#00FFFF',
    nodeSize:0.90, lineOpacity:0.16, rotSpeed:0.55, pulseHz:1.0,
    pulseAmp:0.04, morphSpeed:1.5, radius:1.65,
  },
  thinking: {
    nodeColor:'#AA6FFF', lineColor:'#7B2FFF', glowColor:'#9B4FFF',
    nodeSize:0.80, lineOpacity:0.09, rotSpeed:1.4, pulseHz:0,
    pulseAmp:0, morphSpeed:1.0, radius:1.4,
  },
  speaking: {
    nodeColor:'#CCFFFF', lineColor:'#00D9FF', glowColor:'#00EEFF',
    nodeSize:0.95, lineOpacity:0.14, rotSpeed:0.70, pulseHz:2.5,
    pulseAmp:0.055, morphSpeed:1.8, radius:1.5,
  },
  paused: {
    nodeColor:'#CC7700', lineColor:'#994400', glowColor:'#FF8800',
    nodeSize:0.60, lineOpacity:0.05, rotSpeed:0.05, pulseHz:0.12,
    pulseAmp:0.012, morphSpeed:0.6, radius:1.1,
  },
}

// ── Math helpers ───────────────────────────────────────────────────────────────

function lerp(a: number, b: number, t: number) { return a + (b - a) * t }

// Fibonacci sphere — evenly distributed points
function fibSphere(n: number, r: number): THREE.Vector3[] {
  const pts: THREE.Vector3[] = []
  const phi = Math.PI * (3 - Math.sqrt(5))
  for (let i = 0; i < n; i++) {
    const y = 1 - (i / (n - 1)) * 2
    const radius = Math.sqrt(Math.max(0, 1 - y * y))
    const theta = phi * i
    pts.push(new THREE.Vector3(
      Math.cos(theta) * radius * r,
      y * r,
      Math.sin(theta) * radius * r,
    ))
  }
  return pts
}

// Torus surface distribution
function torusPositions(n: number, R = 1.2, r = 0.5): THREE.Vector3[] {
  const pts: THREE.Vector3[] = []
  for (let i = 0; i < n; i++) {
    const u = (i / n) * Math.PI * 2
    const v = (i * 7 / n) * Math.PI * 2
    pts.push(new THREE.Vector3(
      (R + r * Math.cos(v)) * Math.cos(u),
      r * Math.sin(v),
      (R + r * Math.cos(v)) * Math.sin(u),
    ))
  }
  return pts
}

// Expanded lattice (listening) — nodes on slightly larger sphere with perturb
function latticePositions(n: number, r: number): THREE.Vector3[] {
  return fibSphere(n, r).map((v, i) => {
    const perturb = 0.12 * Math.sin(i * 1.618)
    return v.clone().multiplyScalar(1 + perturb)
  })
}

// ── Component ──────────────────────────────────────────────────────────────────

const NODE_COUNT = 180
const LINE_DIST_SQ = 0.38 * 0.38   // connect nodes within this distance²

export const NeuralOrb: React.FC<NeuralOrbProps> = ({ state, onClick, audioLevel = 0 }) => {
  const containerRef = useRef<HTMLDivElement>(null)

  // Keep mutable state in refs (avoids closure stale issues)
  const stateRef     = useRef(state)
  const audioRef     = useRef(audioLevel)

  useEffect(() => { stateRef.current = state  }, [state])
  useEffect(() => { audioRef.current = audioLevel }, [audioLevel])

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    // ── Renderer ────────────────────────────────────────────────────────────
    const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.setClearColor(0x000000, 0)
    const w = container.clientWidth  || 400
    const h = container.clientHeight || 400
    renderer.setSize(w, h)
    const canvas = renderer.domElement
    canvas.style.border     = 'none'
    canvas.style.outline    = 'none'
    canvas.style.background = 'transparent'
    container.appendChild(canvas)

    // ── Scene / Camera ──────────────────────────────────────────────────────
    const scene  = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(50, w / h, 0.1, 100)
    camera.position.z = 4.5

    const group = new THREE.Group()
    scene.add(group)

    // ── Build node positions ─────────────────────────────────────────────────
    const homeSphere = fibSphere(NODE_COUNT, 1.4)

    // current interpolated positions (live)
    const curPos = homeSphere.map(v => v.clone())

    // target positions (updated on state change)
    let targetPos = homeSphere.map(v => v.clone())

    // ── Points geometry ──────────────────────────────────────────────────────
    const posArr  = new Float32Array(NODE_COUNT * 3)
    const sizeArr = new Float32Array(NODE_COUNT)

    // Assign random size variation per node (persist for lifetime)
    const nodeSizeSeed = Float32Array.from({ length: NODE_COUNT }, () => 0.7 + Math.random() * 0.6)
    // Unique time offset per node for organic drift
    const nodePhase    = Float32Array.from({ length: NODE_COUNT }, () => Math.random() * Math.PI * 2)

    curPos.forEach((v, i) => {
      posArr[i*3] = v.x; posArr[i*3+1] = v.y; posArr[i*3+2] = v.z
      sizeArr[i] = nodeSizeSeed[i]
    })

    const pointGeo = new THREE.BufferGeometry()
    pointGeo.setAttribute('position', new THREE.BufferAttribute(posArr, 3))
    pointGeo.setAttribute('size',     new THREE.BufferAttribute(sizeArr, 1))

    const pointMat = new THREE.ShaderMaterial({
      uniforms: {
        uColor:    { value: new THREE.Color('#00C4E8') },
        uBaseSize: { value: 220.0 },
        uOpacity:  { value: 1.0 },
      },
      vertexShader: `
        attribute float size;
        uniform float uBaseSize;
        varying float vAlpha;
        void main() {
          vec4 mv = modelViewMatrix * vec4(position, 1.0);
          gl_PointSize = size * (uBaseSize / -mv.z);
          gl_Position  = projectionMatrix * mv;
          vAlpha = 0.5 + 0.5 * size;
        }
      `,
      fragmentShader: `
        uniform vec3  uColor;
        uniform float uOpacity;
        varying float vAlpha;
        void main() {
          float d = length(gl_PointCoord - vec2(0.5));
          if (d > 0.5) discard;
          // Bright core → soft halo falloff
          float core = 1.0 - smoothstep(0.0, 0.18, d);
          float halo = 1.0 - smoothstep(0.18, 0.5, d);
          float alpha = (core * 0.9 + halo * 0.35) * vAlpha * uOpacity;
          vec3  col   = uColor + vec3(0.5, 0.5, 0.5) * core;
          gl_FragColor = vec4(col, alpha);
        }
      `,
      transparent: true,
      depthWrite:  false,
      blending:    THREE.AdditiveBlending,
    })

    const points = new THREE.Points(pointGeo, pointMat)
    group.add(points)

    // ── Line segments geometry ───────────────────────────────────────────────
    // Pre-build a static adjacency graph on the home sphere (won't change topology)
    const buildLineBuffer = (positions: Float32Array): Float32Array => {
      const verts: number[] = []
      for (let i = 0; i < NODE_COUNT; i++) {
        for (let j = i + 1; j < NODE_COUNT; j++) {
          const dx = positions[j*3]   - positions[i*3]
          const dy = positions[j*3+1] - positions[i*3+1]
          const dz = positions[j*3+2] - positions[i*3+2]
          if (dx*dx + dy*dy + dz*dz < LINE_DIST_SQ) {
            verts.push(
              positions[i*3], positions[i*3+1], positions[i*3+2],
              positions[j*3], positions[j*3+1], positions[j*3+2],
            )
          }
        }
      }
      return new Float32Array(verts)
    }

    let lineVerts = buildLineBuffer(posArr)
    const lineGeo = new THREE.BufferGeometry()
    lineGeo.setAttribute('position', new THREE.BufferAttribute(lineVerts.slice(), 3))

    const lineMat = new THREE.LineBasicMaterial({
      color:       new THREE.Color('#00D9FF'),
      transparent: true,
      opacity:     0.10,
      blending:    THREE.AdditiveBlending,
      depthWrite:  false,
    })
    const lines = new THREE.LineSegments(lineGeo, lineMat)
    group.add(lines)

    // ── Smoothly interpolated render values ─────────────────────────────────
    let curNodeColor  = new THREE.Color('#00C4E8')
    let curLineColor  = new THREE.Color('#00A8CC')
    let curGlowColor  = '#00D9FF'
    let curNodeSize   = 0.75
    let curLineOpacity = 0.10
    let curRotSpeed   = 0.30
    let curPulseHz    = 0.30
    let curPulseAmp   = 0.022
    let curMorphSpeed = 1.2
    let curRadius     = 1.4

    // target smooth values
    let tgtNodeColor   = new THREE.Color('#00C4E8')
    let tgtLineColor   = new THREE.Color('#00A8CC')
    let tgtGlowColor   = '#00D9FF'
    let tgtNodeSize    = 0.75
    let tgtLineOpacity = 0.10
    let tgtRotSpeed    = 0.30
    let tgtPulseHz     = 0.30
    let tgtPulseAmp    = 0.022
    let tgtMorphSpeed  = 1.2
    let tgtRadius      = 1.4

    let prevState = stateRef.current
    let frameCount = 0
    let animId = 0
    let lastTs: number | null = null
    let globalTime = 0

    // ── Animation loop ───────────────────────────────────────────────────────
    const animate = (ts: number) => {
      animId = requestAnimationFrame(animate)
      const dt = Math.min((lastTs === null ? 16 : ts - lastTs) / 1000, 0.05)
      lastTs = ts
      globalTime += dt
      frameCount++

      const s  = stateRef.current
      const al = Math.min(audioRef.current, 1)

      // ── State transition detection ─────────────────────────────────────
      if (s !== prevState) {
        prevState = s
        const cfg = STATES[s] ?? STATES.active

        tgtNodeColor   = new THREE.Color(cfg.nodeColor)
        tgtLineColor   = new THREE.Color(cfg.lineColor)
        tgtGlowColor   = cfg.glowColor
        tgtNodeSize    = cfg.nodeSize
        tgtLineOpacity = cfg.lineOpacity
        tgtRotSpeed    = cfg.rotSpeed
        tgtPulseHz     = cfg.pulseHz
        tgtPulseAmp    = cfg.pulseAmp
        tgtMorphSpeed  = cfg.morphSpeed
        tgtRadius      = cfg.radius

        // Compute new target node positions
        switch (s) {
          case 'thinking':
            targetPos = torusPositions(NODE_COUNT)
            break
          case 'listening':
            targetPos = latticePositions(NODE_COUNT, cfg.radius)
            break
          default:
            targetPos = fibSphere(NODE_COUNT, cfg.radius)
        }
      }

      // ── Smooth lerp all render values ──────────────────────────────────
      const lf = dt * 1.8   // lerp factor for colors/opacity
      curNodeColor.lerp(tgtNodeColor, lf)
      curLineColor.lerp(tgtLineColor, lf)
      curGlowColor   = tgtGlowColor   // snap glow (CSS)
      curNodeSize    = lerp(curNodeSize,    tgtNodeSize,    lf)
      curLineOpacity = lerp(curLineOpacity, tgtLineOpacity, lf)
      curRotSpeed    = lerp(curRotSpeed,    tgtRotSpeed,    dt * 2.5)
      curPulseHz     = lerp(curPulseHz,     tgtPulseHz,     lf)
      curPulseAmp    = lerp(curPulseAmp,    tgtPulseAmp,    lf)
      curMorphSpeed  = lerp(curMorphSpeed,  tgtMorphSpeed,  lf)
      curRadius      = lerp(curRadius,      tgtRadius,      lf)

      // ── Global breathing scale ─────────────────────────────────────────
      const breathe = curPulseHz > 0
        ? 1 + Math.sin(globalTime * curPulseHz * Math.PI * 2) * curPulseAmp
        : 1.0
      const audioBoost = 1 + al * 0.12

      // ── Group rotation ─────────────────────────────────────────────────
      group.rotation.y += curRotSpeed * dt
      group.rotation.x += curRotSpeed * 0.15 * dt

      // ── Per-node position update ───────────────────────────────────────
      const posAttr = pointGeo.getAttribute('position') as THREE.BufferAttribute
      const posData = posAttr.array as Float32Array

      for (let i = 0; i < NODE_COUNT; i++) {
        const tgt = targetPos[i]
        const cur = curPos[i]
        const ph  = nodePhase[i]

        // Organic drift — each node gently oscillates around its target
        const driftScale = 0.018
        const dx = Math.sin(globalTime * 0.7 + ph) * driftScale
        const dy = Math.cos(globalTime * 0.5 + ph * 1.3) * driftScale
        const dz = Math.sin(globalTime * 0.9 + ph * 0.7) * driftScale

        // State-specific per-node motion layered on top
        let extraR = 0
        if (s === 'listening') {
          // Latitude-band ripple, audio reactive
          const lat = Math.abs(tgt.y / curRadius)
          extraR = Math.sin(globalTime * 1.8 + lat * 9 + ph) * 0.055 * (1 + al * 1.8)
        } else if (s === 'thinking') {
          // Individual micro-orbit around torus surface
          const phase = i * 0.137 + globalTime * 2.8
          extraR = Math.sin(phase) * 0.03
        } else if (s === 'speaking') {
          // Radial wave propagates top-to-bottom
          const lat = (tgt.y / curRadius + 1) * 0.5
          extraR = Math.sin(globalTime * 5.5 - lat * 12 + ph * 0.5) * 0.065 * (0.6 + al * 1.4)
        }

        // Move cur toward tgt fluidly (no scatter — pure smooth flow)
        const mspd = curMorphSpeed * dt
        cur.x = lerp(cur.x, (tgt.x + dx) * breathe * audioBoost, mspd)
        cur.y = lerp(cur.y, (tgt.y + dy) * breathe * audioBoost, mspd)
        cur.z = lerp(cur.z, (tgt.z + dz) * breathe * audioBoost, mspd)

        // Apply extra radial displacement
        if (extraR !== 0) {
          const len = Math.sqrt(cur.x*cur.x + cur.y*cur.y + cur.z*cur.z) || 1
          cur.x += (cur.x / len) * extraR
          cur.y += (cur.y / len) * extraR
          cur.z += (cur.z / len) * extraR
        }

        posData[i*3]   = cur.x
        posData[i*3+1] = cur.y
        posData[i*3+2] = cur.z
      }
      posAttr.needsUpdate = true

      // ── Rebuild lines every 4th frame (≈15fps at 60fps) ───────────────
      if (frameCount % 4 === 0) {
        const newVerts = buildLineBuffer(posData)
        if (newVerts.length !== lineVerts.length) {
          lineVerts = newVerts
          lineGeo.setAttribute('position', new THREE.BufferAttribute(lineVerts.slice(), 3))
        } else {
          const lb = lineGeo.getAttribute('position') as THREE.BufferAttribute
          ;(lb.array as Float32Array).set(newVerts)
          lb.needsUpdate = true
        }
      }

      // ── Material updates ───────────────────────────────────────────────
      const pm = points.material as THREE.ShaderMaterial
      pm.uniforms.uColor.value.copy(curNodeColor)
      pm.uniforms.uBaseSize.value = curNodeSize * 220

      lineMat.color.copy(curLineColor)
      lineMat.opacity = curLineOpacity

      // ── CSS glow ───────────────────────────────────────────────────────
      const glowPx = 22 + curNodeSize * 20 + al * 14
      container.style.filter = `drop-shadow(0 0 ${glowPx}px ${curGlowColor}) drop-shadow(0 0 ${glowPx * 0.5}px ${curGlowColor})`

      renderer.render(scene, camera)
    }

    animId = requestAnimationFrame(animate)

    // ── Resize observer ────────────────────────────────────────────────────
    const ro = new ResizeObserver(() => {
      const cw = container.clientWidth  || 400
      const ch = container.clientHeight || 400
      renderer.setSize(cw, ch)
      camera.aspect = cw / ch
      camera.updateProjectionMatrix()
    })
    ro.observe(container)

    return () => {
      cancelAnimationFrame(animId)
      ro.disconnect()
      renderer.dispose()
      if (container.contains(canvas)) {
        container.removeChild(canvas)
      }
    }
  }, []) // runs once — all state read via refs

  return (
    <div
      ref={containerRef}
      className="orb-canvas-container"
      onClick={onClick}
      style={{ width: '100%', height: '100%' }}
    />
  )
}
