/**
 * NeuralOrb — Particle Constellation Orb
 *
 * ~220 glowing nodes connected by faint energy lines, forming a sphere.
 * On state transitions nodes scatter outward then magnetically snap back.
 * Each state has a unique attractor shape the particles morph toward:
 *
 *   inactive  → dim sphere, slow drift
 *   active    → bright sphere, gentle breathe
 *   listening → nodes pull outward in rings, audio-reactive
 *   thinking  → nodes warp into a torus
 *   speaking  → nodes form radial spikes that pulse
 *   paused    → amber nodes collapse to a tight dense sphere
 */

import { useEffect, useRef, useCallback } from 'react'
import * as THREE from 'three'
import './OrbCanvas.css'

export interface NeuralOrbProps {
  state: 'inactive' | 'active' | 'listening' | 'thinking' | 'speaking' | 'paused'
  onClick?: () => void
  audioLevel?: number
}

// ── State config ───────────────────────────────────────────────────────────────

interface StateConfig {
  color:       string
  glowColor:   string
  emissive:    number
  rotSpeed:    number
  pulseHz:     number
  scatterForce:number  // 0 = no scatter, >0 = scatter on enter
  lineOpacity: number
}

const STATES: Record<string, StateConfig> = {
  inactive: { color:'#1a4a7a', glowColor:'#1a5296', emissive:0.15, rotSpeed:0.12, pulseHz:0,    scatterForce:0,   lineOpacity:0.06 },
  active:   { color:'#00C4E8', glowColor:'#00D9FF', emissive:0.6,  rotSpeed:0.35, pulseHz:0.3,  scatterForce:0,   lineOpacity:0.12 },
  listening:{ color:'#80FFFF', glowColor:'#00FFFF', emissive:1.0,  rotSpeed:0.6,  pulseHz:1.2,  scatterForce:0.4, lineOpacity:0.18 },
  thinking: { color:'#9B4FFF', glowColor:'#7B2FFF', emissive:0.85, rotSpeed:1.6,  pulseHz:0,    scatterForce:0.7, lineOpacity:0.09 },
  speaking: { color:'#AAFFFF', glowColor:'#00D9FF', emissive:1.1,  rotSpeed:0.8,  pulseHz:0,    scatterForce:0.5, lineOpacity:0.15 },
  paused:   { color:'#CC7A00', glowColor:'#FF8C00', emissive:0.3,  rotSpeed:0.06, pulseHz:0.12, scatterForce:0,   lineOpacity:0.05 },
}

// ── Helpers ────────────────────────────────────────────────────────────────────

function lerp(a: number, b: number, t: number) { return a + (b - a) * t }
function lerpColor(a: THREE.Color, b: THREE.Color, t: number) {
  return new THREE.Color(lerp(a.r,b.r,t), lerp(a.g,b.g,t), lerp(a.b,b.b,t))
}
function easeOutElastic(t: number) {
  if (t === 0 || t === 1) return t
  return Math.pow(2, -10*t) * Math.sin((t*10 - 0.75) * (2*Math.PI) / 3) + 1
}
// Fibonacci sphere — even distribution
function fibSphere(n: number, r: number): THREE.Vector3[] {
  const pts: THREE.Vector3[] = []
  const phi = Math.PI * (3 - Math.sqrt(5))
  for (let i = 0; i < n; i++) {
    const y = 1 - (i / (n - 1)) * 2
    const radius = Math.sqrt(1 - y * y)
    const theta = phi * i
    pts.push(new THREE.Vector3(Math.cos(theta) * radius * r, y * r, Math.sin(theta) * radius * r))
  }
  return pts
}

// Torus attractor
function torusPos(i: number, n: number, R = 1.3, r = 0.55): THREE.Vector3 {
  const u = (i / n) * Math.PI * 2
  const v = (i * 7 / n) * Math.PI * 2
  return new THREE.Vector3(
    (R + r * Math.cos(v)) * Math.cos(u),
    (R + r * Math.cos(v)) * Math.sin(u),
    r * Math.sin(v)
  )
}

// Spiky sphere (speaking)
function spikyPos(i: number, n: number, baseR: number): THREE.Vector3 {
  const phi = Math.PI * (3 - Math.sqrt(5))
  const y = 1 - (i / (n-1)) * 2
  const radius = Math.sqrt(Math.max(0, 1 - y*y))
  const theta = phi * i
  const spike = 1 + 0.45 * Math.pow(Math.abs(Math.cos(theta * 3)), 3)
  return new THREE.Vector3(
    Math.cos(theta) * radius * baseR * spike,
    y * baseR * spike,
    Math.sin(theta) * radius * baseR * spike
  )
}

// Tight dense sphere (paused)
function densePos(i: number, n: number): THREE.Vector3 {
  return fibSphere(n, 0.7)[i]
}

// ── Component ──────────────────────────────────────────────────────────────────

const NODE_COUNT = 220
const BASE_RADIUS = 1.45
const LINE_DIST = 0.52   // connect nodes closer than this

export const NeuralOrb: React.FC<NeuralOrbProps> = ({ state, onClick, audioLevel = 0 }) => {
  const containerRef = useRef<HTMLDivElement>(null)
  const rendererRef  = useRef<THREE.WebGLRenderer | null>(null)
  const sceneRef     = useRef<THREE.Scene | null>(null)
  const cameraRef    = useRef<THREE.PerspectiveCamera | null>(null)
  const animFrameRef = useRef<number>(0)
  const groupRef     = useRef<THREE.Group | null>(null)

  // Node positions
  const homePosRef    = useRef<THREE.Vector3[]>([])   // sphere home
  const targetPosRef  = useRef<THREE.Vector3[]>([])   // shape attractor
  const currentPosRef = useRef<THREE.Vector3[]>([])   // live interpolated

  // Scatter state per node
  type NodeAnim = { flying: boolean; flyPos: THREE.Vector3; flyV: THREE.Vector3; assembleT: number }
  const nodeAnimRef = useRef<NodeAnim[]>([])

  // Points geometry
  const pointsRef  = useRef<THREE.Points | null>(null)
  const lineSegRef = useRef<THREE.LineSegments | null>(null)

  // Animation refs
  const timeRef          = useRef(0)
  const rotSpeedRef      = useRef(0.35)
  const tgtRotSpeedRef   = useRef(0.35)
  const pulseHzRef       = useRef(0.3)
  const tgtPulseHzRef    = useRef(0.3)
  const curColorRef      = useRef(new THREE.Color('#00C4E8'))
  const tgtColorRef      = useRef(new THREE.Color('#00C4E8'))
  const emissiveRef      = useRef(0.6)
  const tgtEmissiveRef   = useRef(0.6)
  const lineOpacityRef   = useRef(0.12)
  const tgtLineOpacityRef= useRef(0.12)
  const glowColorRef     = useRef('#00D9FF')
  const stateRef         = useRef<string>('active')
  const audioLevelRef    = useRef(0)

  // ── Setup ──────────────────────────────────────────────────────────────────

  const initNodes = useCallback(() => {
    const sphere = fibSphere(NODE_COUNT, BASE_RADIUS)
    homePosRef.current   = sphere.map(v => v.clone())
    targetPosRef.current = sphere.map(v => v.clone())
    currentPosRef.current = sphere.map(v => v.clone())
    nodeAnimRef.current = sphere.map(() => ({
      flying: false,
      flyPos: new THREE.Vector3(),
      flyV:   new THREE.Vector3(),
      assembleT: 1,
    }))
  }, [])

  const buildLines = useCallback((positions: Float32Array) => {
    // Build adjacency from current node positions
    const lineVerts: number[] = []
    const n = NODE_COUNT
    for (let i = 0; i < n; i++) {
      const ax = positions[i*3], ay = positions[i*3+1], az = positions[i*3+2]
      for (let j = i+1; j < n; j++) {
        const dx = positions[j*3]-ax, dy = positions[j*3+1]-ay, dz = positions[j*3+2]-az
        if (dx*dx+dy*dy+dz*dz < LINE_DIST*LINE_DIST) {
          lineVerts.push(ax,ay,az, positions[j*3],positions[j*3+1],positions[j*3+2])
        }
      }
    }
    return new Float32Array(lineVerts)
  }, [])

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    initNodes()

    const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.setClearColor(0x000000, 0)
    rendererRef.current = renderer
    const w = container.clientWidth || 400
    const h = container.clientHeight || 400
    renderer.setSize(w, h)
    container.appendChild(renderer.domElement)

    const scene = new THREE.Scene()
    sceneRef.current = scene
    const camera = new THREE.PerspectiveCamera(52, w/h, 0.1, 100)
    camera.position.z = 4.2
    cameraRef.current = camera

    const group = new THREE.Group()
    scene.add(group)
    groupRef.current = group

    // ── Points (nodes) ───────────────────────────────────────────────────────
    const pointGeo = new THREE.BufferGeometry()
    const posArr = new Float32Array(NODE_COUNT * 3)
    currentPosRef.current.forEach((v,i) => { posArr[i*3]=v.x; posArr[i*3+1]=v.y; posArr[i*3+2]=v.z })
    pointGeo.setAttribute('position', new THREE.BufferAttribute(posArr, 3))

    // Size variation per node
    const sizes = new Float32Array(NODE_COUNT).map(() => 4 + Math.random() * 5)
    pointGeo.setAttribute('size', new THREE.BufferAttribute(sizes, 1))

    const pointMat = new THREE.ShaderMaterial({
      uniforms: {
        uColor:   { value: new THREE.Color('#00C4E8') },
        uOpacity: { value: 1.0 },
      },
      vertexShader: `
        attribute float size;
        varying float vAlpha;
        void main() {
          vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
          gl_PointSize = size * (300.0 / -mvPosition.z);
          gl_Position = projectionMatrix * mvPosition;
          vAlpha = 0.6 + 0.4 * smoothstep(4.0, 9.0, size);
        }
      `,
      fragmentShader: `
        uniform vec3 uColor;
        uniform float uOpacity;
        varying float vAlpha;
        void main() {
          float d = length(gl_PointCoord - vec2(0.5));
          if (d > 0.5) discard;
          // Soft glow falloff
          float alpha = (1.0 - smoothstep(0.1, 0.5, d)) * vAlpha * uOpacity;
          gl_FragColor = vec4(uColor + vec3(0.3) * (1.0 - d*2.0), alpha);
        }
      `,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    })

    const points = new THREE.Points(pointGeo, pointMat)
    group.add(points)
    pointsRef.current = points

    // ── Line segments (connections) ───────────────────────────────────────────
    const lineVerts = buildLines(posArr)
    const lineGeo = new THREE.BufferGeometry()
    lineGeo.setAttribute('position', new THREE.BufferAttribute(lineVerts, 3))

    const lineMat = new THREE.LineBasicMaterial({
      color: new THREE.Color('#00D9FF'),
      transparent: true,
      opacity: 0.12,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    })
    const lines = new THREE.LineSegments(lineGeo, lineMat)
    group.add(lines)
    lineSegRef.current = lines

    // ── Resize ────────────────────────────────────────────────────────────────
    const onResize = () => {
      const cw = container.clientWidth || 400
      const ch = container.clientHeight || 400
      renderer.setSize(cw, ch)
      camera.aspect = cw/ch
      camera.updateProjectionMatrix()
    }
    const ro = new ResizeObserver(onResize)
    ro.observe(container)

    // ── Animation loop ────────────────────────────────────────────────────────
    let lastTs: number | null = null

    const animate = (ts: number) => {
      animFrameRef.current = requestAnimationFrame(animate)
      const dtMs = lastTs === null ? 16 : Math.min(ts - lastTs, 50)
      lastTs = ts
      const dt = dtMs / 1000
      timeRef.current += dt

      const t = timeRef.current
      const curState = stateRef.current
      const al = audioLevelRef.current

      // Lerp global values
      rotSpeedRef.current  = lerp(rotSpeedRef.current,  tgtRotSpeedRef.current,  dt*3)
      pulseHzRef.current   = lerp(pulseHzRef.current,   tgtPulseHzRef.current,   dt*2)
      emissiveRef.current  = lerp(emissiveRef.current,  tgtEmissiveRef.current,  dt*2.5)
      lineOpacityRef.current = lerp(lineOpacityRef.current, tgtLineOpacityRef.current, dt*2)
      curColorRef.current  = lerpColor(curColorRef.current, tgtColorRef.current, dt*2.5)

      // Global breathe scale
      const hz = pulseHzRef.current
      let globScale = 1.0
      if (hz > 0) globScale += Math.sin(t * hz * Math.PI * 2) * 0.03
      globScale += al * 0.1

      // Group rotation
      if (group) {
        group.rotation.y += rotSpeedRef.current * dt
        group.rotation.x += rotSpeedRef.current * 0.2 * dt
      }

      // Update node positions
      const posAttr = (points.geometry.getAttribute('position') as THREE.BufferAttribute)
      const posData = posAttr.array as Float32Array

      for (let i = 0; i < NODE_COUNT; i++) {
        const anim = nodeAnimRef.current[i]
        const home = targetPosRef.current[i]
        const cur  = currentPosRef.current[i]

        if (anim.flying) {
          // Scatter phase: fly outward
          anim.flyPos.addScaledVector(anim.flyV, dt)
          // Drag
          anim.flyV.multiplyScalar(0.92)
          // Check if velocity is low enough → start assembling
          if (anim.flyV.lengthSq() < 0.002) {
            anim.flying = false
            anim.assembleT = 0
            anim.flyPos.copy(cur) // start from current fly position
          }
          cur.copy(anim.flyPos)
        } else if (anim.assembleT < 1) {
          // Reassemble with elastic spring
          anim.assembleT = Math.min(1, anim.assembleT + dt * 2.2)
          const eased = easeOutElastic(anim.assembleT)
          cur.lerpVectors(anim.flyPos, home.clone().multiplyScalar(globScale), eased)
        } else {
          // At rest: snap to target with gentle drift
          cur.lerp(home.clone().multiplyScalar(globScale), dt * 4)

          // State-specific motion
          if (curState === 'listening') {
            // Nodes pulse outward in latitude bands with audio
            const lat = Math.abs(home.y / BASE_RADIUS)
            const wave = Math.sin(t * 2.5 + lat * 8) * 0.06 * (1 + al * 1.5)
            cur.addScaledVector(home.clone().normalize(), wave)
          }

          if (curState === 'thinking') {
            // Per-node orbit wobble
            const phase = i * 0.137 + t * 3.1
            cur.x += Math.sin(phase) * 0.006
            cur.y += Math.cos(phase * 0.7) * 0.006
          }

          if (curState === 'speaking') {
            // Radial spike wave — propagates from top to bottom
            const lat = (home.y / BASE_RADIUS + 1) * 0.5
            const wave = Math.sin(t * 4.0 - lat * 10) * 0.1 * (0.5 + al * 1.2)
            cur.addScaledVector(home.clone().normalize(), wave)
          }
        }

        posData[i*3]   = cur.x
        posData[i*3+1] = cur.y
        posData[i*3+2] = cur.z
      }

      posAttr.needsUpdate = true

      // Rebuild lines every 3rd frame (performance: ~20fps line update)
      if (Math.round(t * 60) % 3 === 0 && lineSegRef.current) {
        const newLineVerts = buildLines(posData)
        const lineGeoObj = lineSegRef.current.geometry
        const existing = lineGeoObj.getAttribute('position') as THREE.BufferAttribute | undefined
        if (!existing || existing.array.length !== newLineVerts.length) {
          lineGeoObj.setAttribute('position', new THREE.BufferAttribute(newLineVerts, 3))
        } else {
          ;(existing.array as Float32Array).set(newLineVerts)
          existing.needsUpdate = true
        }
      }

      // Update materials
      const pMat = points.material as THREE.ShaderMaterial
      pMat.uniforms.uColor.value.copy(curColorRef.current)

      if (lineSegRef.current) {
        const lMat = lineSegRef.current.material as THREE.LineBasicMaterial
        lMat.color.copy(curColorRef.current)
        lMat.opacity = lineOpacityRef.current
      }

      // CSS glow
      const glow = 25 + emissiveRef.current * 18 + al * 12
      container.style.filter = `drop-shadow(0 0 ${glow}px ${glowColorRef.current})`

      renderer.render(scene, camera)
    }

    animFrameRef.current = requestAnimationFrame(animate)

    return () => {
      cancelAnimationFrame(animFrameRef.current)
      ro.disconnect()
      renderer.dispose()
      if (container.contains(renderer.domElement)) container.removeChild(renderer.domElement)
    }
  }, [initNodes, buildLines])

  // ── State change handler ─────────────────────────────────────────────────

  useEffect(() => {
    const cfg = STATES[state] ?? STATES.active
    const prev = stateRef.current
    stateRef.current = state

    tgtRotSpeedRef.current   = cfg.rotSpeed
    tgtColorRef.current      = new THREE.Color(cfg.color)
    glowColorRef.current     = cfg.glowColor
    tgtEmissiveRef.current   = cfg.emissive
    tgtPulseHzRef.current    = cfg.pulseHz
    tgtLineOpacityRef.current= cfg.lineOpacity

    // Compute new target shape
    const newTargets = (() => {
      switch(state) {
        case 'thinking': return Array.from({length:NODE_COUNT},(_,i)=>torusPos(i,NODE_COUNT))
        case 'speaking': return Array.from({length:NODE_COUNT},(_,i)=>spikyPos(i,NODE_COUNT,BASE_RADIUS))
        case 'paused':   return Array.from({length:NODE_COUNT},(_,i)=>densePos(i,NODE_COUNT))
        default:         return fibSphere(NODE_COUNT, BASE_RADIUS)
      }
    })()
    targetPosRef.current = newTargets

    // Trigger scatter on qualifying transitions
    if (cfg.scatterForce > 0 && prev !== state) {
      const force = cfg.scatterForce
      nodeAnimRef.current.forEach((anim, i) => {
        const cur = currentPosRef.current[i]
        anim.flying = true
        anim.assembleT = 0
        anim.flyPos.copy(cur)
        // Direction: outward from center + random tangent
        const outward = cur.clone().normalize()
        const rand = new THREE.Vector3(
          (Math.random()-0.5)*2,
          (Math.random()-0.5)*2,
          (Math.random()-0.5)*2
        ).normalize()
        anim.flyV
          .copy(outward)
          .addScaledVector(rand, 0.4)
          .multiplyScalar(force * (1 + Math.random() * 0.8))
        // Stagger: nodes at index end fly first
        const delay = (i / NODE_COUNT) * 0.08
        setTimeout(() => {
          if (!anim.flying) return // already done
        }, delay * 1000)
      })
    }
  }, [state])

  useEffect(() => { audioLevelRef.current = audioLevel }, [audioLevel])

  return (
    <div
      ref={containerRef}
      className="orb-canvas-container"
      onClick={onClick}
      style={{ width:'100%', height:'100%' }}
    />
  )
}
