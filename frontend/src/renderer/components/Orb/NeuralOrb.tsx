/**
 * NeuralOrb — JARVIS-style Three.js neural network wireframe orb
 *
 * Renders a blue/cyan icosahedron wireframe with node spheres at vertices.
 * State-reactive: colors, rotation speed, glow and pulse effects change
 * smoothly based on the assistant state.
 *
 * States:
 *   inactive  — dim, slow rotation
 *   active    — cyan, medium rotation, slow breathe
 *   listening — bright cyan, fast rotation + pulse
 *   thinking  — purple, fast rotation, edge flicker
 *   speaking  — cyan/white, ripple ring expands outward
 *   paused    — amber, near-static
 */

import { useEffect, useRef } from 'react'
import * as THREE from 'three'
import './OrbCanvas.css'

// ── Props ──────────────────────────────────────────────────────────────────────

export interface NeuralOrbProps {
  state: 'inactive' | 'active' | 'listening' | 'thinking' | 'speaking' | 'paused'
  onClick?: () => void
  audioLevel?: number
}

// ── State configuration ────────────────────────────────────────────────────────

interface OrbStateConfig {
  rotSpeed:  number
  edgeColor: string
  nodeColor: string
  glowColor: string
  pulseHz:   number
  dim:       boolean
}

const STATE_CONFIGS: Record<string, OrbStateConfig> = {
  inactive: { rotSpeed: 0.2,  edgeColor: '#1a4a6e', nodeColor: '#1a4a6e', glowColor: '#1E90FF', pulseHz: 0,    dim: true  },
  active:   { rotSpeed: 0.5,  edgeColor: '#00D9FF', nodeColor: '#00AAFF', glowColor: '#00D9FF', pulseHz: 0.3,  dim: false },
  listening:{ rotSpeed: 0.8,  edgeColor: '#00FFFF', nodeColor: '#00FFFF', glowColor: '#00FFFF', pulseHz: 1.2,  dim: false },
  thinking: { rotSpeed: 1.5,  edgeColor: '#7B2FFF', nodeColor: '#9B4FFF', glowColor: '#7B2FFF', pulseHz: 0,    dim: false },
  speaking: { rotSpeed: 1.0,  edgeColor: '#00D9FF', nodeColor: '#FFFFFF', glowColor: '#00D9FF', pulseHz: 0,    dim: false },
  paused:   { rotSpeed: 0.1,  edgeColor: '#FFA500', nodeColor: '#FFA500', glowColor: '#FFA500', pulseHz: 0.15, dim: true  },
}

// ── Lerp helpers ───────────────────────────────────────────────────────────────

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t
}

function lerpColor(a: THREE.Color, b: THREE.Color, t: number): THREE.Color {
  return new THREE.Color(
    lerp(a.r, b.r, t),
    lerp(a.g, b.g, t),
    lerp(a.b, b.b, t),
  )
}

// ── Component ──────────────────────────────────────────────────────────────────

export const NeuralOrb: React.FC<NeuralOrbProps> = ({ state, onClick, audioLevel = 0 }) => {
  const containerRef = useRef<HTMLDivElement>(null)

  // Three.js object refs — updated without rebuilding scene
  const rendererRef   = useRef<THREE.WebGLRenderer | null>(null)
  const sceneRef      = useRef<THREE.Scene | null>(null)
  const cameraRef     = useRef<THREE.PerspectiveCamera | null>(null)
  const animFrameRef  = useRef<number>(0)

  // Wireframe + nodes
  const edgesRef      = useRef<THREE.LineSegments | null>(null)
  const nodesGroupRef = useRef<THREE.Group | null>(null)

  // Ripple ring (speaking state)
  const ringRef       = useRef<THREE.Mesh | null>(null)
  const ringMatRef    = useRef<THREE.MeshBasicMaterial | null>(null)

  // Animation state refs (avoid re-renders)
  const timeRef       = useRef(0)
  const rotSpeedRef   = useRef(0.5)
  const targetRotSpeedRef = useRef(0.5)

  // Current interpolated colors
  const edgeColorRef  = useRef(new THREE.Color('#00D9FF'))
  const nodeColorRef  = useRef(new THREE.Color('#00AAFF'))
  const targetEdgeColorRef = useRef(new THREE.Color('#00D9FF'))
  const targetNodeColorRef = useRef(new THREE.Color('#00AAFF'))

  // Pulse state
  const pulseHzRef    = useRef(0.3)
  const targetPulseHzRef = useRef(0.3)

  // State name ref for thinking flicker + speaking ring
  const stateRef      = useRef<string>('active')

  // Glow color ref for CSS drop-shadow
  const glowColorRef  = useRef('#00D9FF')

  // audioLevel ref
  const audioLevelRef = useRef(0)

  // ── Scene setup (once on mount) ──────────────────────────────────────────────

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    // ── Renderer ────────────────────────────────────────────────────────────
    const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true })
    renderer.setPixelRatio(window.devicePixelRatio)
    renderer.setClearColor(0x000000, 0)
    rendererRef.current = renderer

    // Size to container
    const w = container.clientWidth  || 400
    const h = container.clientHeight || 400
    renderer.setSize(w, h)
    container.appendChild(renderer.domElement)

    // ── Scene + Camera ───────────────────────────────────────────────────────
    const scene  = new THREE.Scene()
    sceneRef.current = scene

    const camera = new THREE.PerspectiveCamera(60, w / h, 0.1, 100)
    camera.position.z = 3.5
    cameraRef.current = camera

    // ── Lighting ─────────────────────────────────────────────────────────────
    const ambient = new THREE.AmbientLight(0x112244, 0.4)
    scene.add(ambient)

    const pointLight = new THREE.PointLight(0x00D9FF, 2.0, 10)
    pointLight.position.set(2, 2, 3)
    scene.add(pointLight)

    // ── Icosahedron wireframe ─────────────────────────────────────────────────
    const icoGeo   = new THREE.IcosahedronGeometry(1.5, 3)
    const edgesGeo = new THREE.EdgesGeometry(icoGeo)
    const edgesMat = new THREE.LineBasicMaterial({
      color: new THREE.Color('#00D9FF'),
      transparent: true,
      opacity: 0.85,
    })
    const edges = new THREE.LineSegments(edgesGeo, edgesMat)
    scene.add(edges)
    edgesRef.current = edges

    // ── Node spheres at icosahedron vertices ──────────────────────────────────
    const nodesGroup = new THREE.Group()
    const nodeMat = new THREE.MeshPhongMaterial({
      color: new THREE.Color('#00AAFF'),
      emissive: new THREE.Color('#003366'),
      shininess: 80,
    })
    const nodeGeo = new THREE.SphereGeometry(0.03, 8, 8)

    const posAttr = icoGeo.getAttribute('position')
    // Collect unique vertex positions
    const seen = new Set<string>()
    for (let i = 0; i < posAttr.count; i++) {
      const x = posAttr.getX(i)
      const y = posAttr.getY(i)
      const z = posAttr.getZ(i)
      // Round to 4 decimal places for dedup key
      const key = `${x.toFixed(4)},${y.toFixed(4)},${z.toFixed(4)}`
      if (!seen.has(key)) {
        seen.add(key)
        const sphere = new THREE.Mesh(nodeGeo, nodeMat.clone())
        sphere.position.set(x, y, z)
        nodesGroup.add(sphere)
      }
    }
    scene.add(nodesGroup)
    nodesGroupRef.current = nodesGroup

    // ── Ripple ring (speaking state) ──────────────────────────────────────────
    const ringGeo = new THREE.TorusGeometry(1.5, 0.02, 8, 64)
    const ringMat = new THREE.MeshBasicMaterial({
      color: new THREE.Color('#00D9FF'),
      transparent: true,
      opacity: 0,
    })
    const ring = new THREE.Mesh(ringGeo, ringMat)
    scene.add(ring)
    ringRef.current    = ring
    ringMatRef.current = ringMat

    // ── Handle resize ─────────────────────────────────────────────────────────
    const onResize = () => {
      const cw = container.clientWidth  || 400
      const ch = container.clientHeight || 400
      renderer.setSize(cw, ch)
      camera.aspect = cw / ch
      camera.updateProjectionMatrix()
    }
    const resizeObserver = new ResizeObserver(onResize)
    resizeObserver.observe(container)

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

      // ── Lerp rotation speed ──────────────────────────────────────────────
      rotSpeedRef.current = lerp(rotSpeedRef.current, targetRotSpeedRef.current, dt * 3)

      // ── Lerp edge/node colors ────────────────────────────────────────────
      edgeColorRef.current  = lerpColor(edgeColorRef.current,  targetEdgeColorRef.current, dt * 2)
      nodeColorRef.current  = lerpColor(nodeColorRef.current,  targetNodeColorRef.current, dt * 2)

      // ── Lerp pulse Hz ────────────────────────────────────────────────────
      pulseHzRef.current = lerp(pulseHzRef.current, targetPulseHzRef.current, dt * 2)

      // ── Apply colors to materials ────────────────────────────────────────
      if (edgesRef.current) {
        const mat = edgesRef.current.material as THREE.LineBasicMaterial
        mat.color.copy(edgeColorRef.current)
      }
      if (nodesGroupRef.current) {
        nodesGroupRef.current.children.forEach(child => {
          const mesh = child as THREE.Mesh
          const mat  = mesh.material as THREE.MeshPhongMaterial
          mat.color.copy(nodeColorRef.current)
        })
      }

      // ── Rotate icosahedron ───────────────────────────────────────────────
      const rotY = rotSpeedRef.current * dt
      const rotX = rotSpeedRef.current * 0.3 * dt
      if (edgesRef.current) {
        edgesRef.current.rotation.y += rotY
        edgesRef.current.rotation.x += rotX
      }
      if (nodesGroupRef.current) {
        nodesGroupRef.current.rotation.y += rotY
        nodesGroupRef.current.rotation.x += rotX
      }

      // ── Pulse breathing ──────────────────────────────────────────────────
      const hz = pulseHzRef.current
      let scale = 1.0
      if (hz > 0) {
        scale = 1.0 + Math.sin(t * hz * Math.PI * 2) * 0.04
      }
      // Audio reactivity: slightly expand with audio level
      scale += al * 0.08
      if (edgesRef.current) {
        edgesRef.current.scale.setScalar(scale)
      }
      if (nodesGroupRef.current) {
        nodesGroupRef.current.scale.setScalar(scale)
      }

      // ── Thinking: edge flicker ───────────────────────────────────────────
      if (curState === 'thinking') {
        const mat = edgesRef.current?.material as THREE.LineBasicMaterial | undefined
        if (mat) {
          mat.opacity = 0.5 + 0.5 * Math.random()
        }
      } else {
        const mat = edgesRef.current?.material as THREE.LineBasicMaterial | undefined
        if (mat) {
          mat.opacity = lerp(mat.opacity, 0.85, dt * 4)
        }
      }

      // ── Speaking: ripple ring ────────────────────────────────────────────
      if (curState === 'speaking' && ringRef.current && ringMatRef.current) {
        // Animate ring scale 1→3 and fade opacity 0.8→0 over 1.5s period
        const ringPhase = (t % 1.5) / 1.5  // 0→1 over 1.5s
        ringRef.current.scale.setScalar(1 + ringPhase * 2)
        ringMatRef.current.opacity = 0.8 * (1 - ringPhase)
        ringRef.current.rotation.y += dt * 0.5
      } else if (ringMatRef.current) {
        ringMatRef.current.opacity = lerp(ringMatRef.current.opacity, 0, dt * 4)
      }

      // ── Update glow color CSS ────────────────────────────────────────────
      if (container) {
        container.style.filter = `drop-shadow(0 0 40px ${glowColorRef.current})`
      }

      renderer.render(scene, camera)
    }

    animFrameRef.current = requestAnimationFrame(animate)

    return () => {
      cancelAnimationFrame(animFrameRef.current)
      resizeObserver.disconnect()
      renderer.dispose()
      if (container.contains(renderer.domElement)) {
        container.removeChild(renderer.domElement)
      }
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // ── React to state changes (no scene rebuild) ─────────────────────────────

  useEffect(() => {
    const cfg = STATE_CONFIGS[state] ?? STATE_CONFIGS.active
    stateRef.current = state
    targetRotSpeedRef.current = cfg.rotSpeed
    targetEdgeColorRef.current = new THREE.Color(cfg.edgeColor)
    targetNodeColorRef.current = new THREE.Color(cfg.nodeColor)
    targetPulseHzRef.current   = cfg.pulseHz
    glowColorRef.current       = cfg.glowColor

    // Dim edges opacity target for inactive/paused
    if (edgesRef.current) {
      const mat = edgesRef.current.material as THREE.LineBasicMaterial
      if (cfg.dim) {
        mat.opacity = 0.35
      }
    }
  }, [state])

  // ── Sync audioLevel ref ────────────────────────────────────────────────────

  useEffect(() => {
    audioLevelRef.current = audioLevel
  }, [audioLevel])

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div
      ref={containerRef}
      className="orb-canvas-container"
      onClick={onClick}
      style={{ width: '100%', height: '100%' }}
    />
  )
}
