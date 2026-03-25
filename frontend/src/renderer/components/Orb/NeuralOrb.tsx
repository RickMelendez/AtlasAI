/**
 * NeuralOrb — Crystal Shard JARVIS Orb
 *
 * The orb is built from ~80 glowing crystal shards (flat triangular prisms).
 * On state change it SHATTERS — shards fly outward, spin, then reassemble.
 * Each shard has an iridescent cyan/blue/white material that reacts to state.
 *
 * States:
 *   inactive  — dim steel-blue shards, barely rotating
 *   active    — cyan glowing shards, slow breathe
 *   listening — white-hot shards pulse outward with voice level
 *   thinking  — purple shards, fast spin, random flicker
 *   speaking  — shards ripple outward in waves timed to speech
 *   paused    — amber shards, near-still
 */

import { useEffect, useRef, useCallback } from 'react'
import * as THREE from 'three'
import './OrbCanvas.css'

// ── Types ──────────────────────────────────────────────────────────────────────

export interface NeuralOrbProps {
  state: 'inactive' | 'active' | 'listening' | 'thinking' | 'speaking' | 'paused'
  onClick?: () => void
  audioLevel?: number
}

interface ShardData {
  mesh:         THREE.Mesh
  homePos:      THREE.Vector3   // rest position on orb surface
  homeQuat:     THREE.Quaternion
  flyDir:       THREE.Vector3   // normalized outward direction for shatter
  flyDist:      number          // how far it flies (randomized)
  flyQuat:      THREE.Quaternion // random tumble rotation
  phase:        number          // 0..1 animation phase
  waveDelay:    number          // per-shard delay for wave effects
  index:        number
}

interface OrbStateConfig {
  rotSpeed:   number
  primaryHex: string
  accentHex:  string
  glowHex:    string
  emissive:   number   // emissiveIntensity multiplier
  pulseHz:    number
  shatterOnEnter: boolean
}

// ── State configs ──────────────────────────────────────────────────────────────

const STATES: Record<string, OrbStateConfig> = {
  inactive: { rotSpeed: 0.15, primaryHex: '#1a3a5c', accentHex: '#2a5a8c', glowHex: '#1E6090', emissive: 0.15, pulseHz: 0,    shatterOnEnter: false },
  active:   { rotSpeed: 0.4,  primaryHex: '#00C4E8', accentHex: '#00EEFF', glowHex: '#00D9FF', emissive: 0.7,  pulseHz: 0.35, shatterOnEnter: false },
  listening:{ rotSpeed: 0.7,  primaryHex: '#80FFFF', accentHex: '#FFFFFF', glowHex: '#00FFFF', emissive: 1.0,  pulseHz: 1.4,  shatterOnEnter: true  },
  thinking: { rotSpeed: 1.8,  primaryHex: '#8B3FFF', accentHex: '#B87FFF', glowHex: '#7B2FFF', emissive: 0.9,  pulseHz: 0,    shatterOnEnter: true  },
  speaking: { rotSpeed: 0.9,  primaryHex: '#00D9FF', accentHex: '#FFFFFF', glowHex: '#00D9FF', emissive: 1.1,  pulseHz: 0,    shatterOnEnter: true  },
  paused:   { rotSpeed: 0.08, primaryHex: '#CC7A00', accentHex: '#FFA500', glowHex: '#FF8C00', emissive: 0.3,  pulseHz: 0.12, shatterOnEnter: false },
}

// ── Helpers ────────────────────────────────────────────────────────────────────

function lerp(a: number, b: number, t: number) { return a + (b - a) * t }

function lerpColor(a: THREE.Color, b: THREE.Color, t: number) {
  return new THREE.Color(lerp(a.r, b.r, t), lerp(a.g, b.g, t), lerp(a.b, b.b, t))
}

function easeInOutCubic(t: number) {
  return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2
}

function easeOutBack(t: number) {
  const c1 = 1.70158, c3 = c1 + 1
  return 1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2)
}

// Build shard geometry: flat elongated triangle prism (crystal facet shape)
function buildShardGeometry(w: number, h: number, depth: number): THREE.BufferGeometry {
  // Triangle top/bottom face, 3 rectangular sides
  const hw = w * 0.5
  const hh = h * 0.5
  const hd = depth * 0.5

  // Slight asymmetry for crystal look
  const ox = (Math.random() - 0.5) * w * 0.3
  const oy = (Math.random() - 0.5) * h * 0.3

  const verts = new Float32Array([
    // top face (z = +hd)
    ox - hw,  oy + hh,  hd,
    ox + hw,  oy + hh,  hd,
    ox,       oy - hh,  hd,
    // bottom face (z = -hd)
    ox - hw,  oy + hh, -hd,
    ox + hw,  oy + hh, -hd,
    ox,       oy - hh, -hd,
  ])

  const indices = new Uint16Array([
    0, 1, 2,       // top
    3, 5, 4,       // bottom (flipped winding)
    0, 3, 1,  1, 3, 4,  // side 1
    1, 4, 2,  2, 4, 5,  // side 2
    2, 5, 0,  0, 5, 3,  // side 3
  ])

  const geo = new THREE.BufferGeometry()
  geo.setAttribute('position', new THREE.BufferAttribute(verts, 3))
  geo.setIndex(new THREE.BufferAttribute(indices, 1))
  geo.computeVertexNormals()
  return geo
}

// ── Component ──────────────────────────────────────────────────────────────────

const SHARD_COUNT = 80
const ORB_RADIUS  = 1.4

export const NeuralOrb: React.FC<NeuralOrbProps> = ({ state, onClick, audioLevel = 0 }) => {
  const containerRef  = useRef<HTMLDivElement>(null)
  const rendererRef   = useRef<THREE.WebGLRenderer | null>(null)
  const sceneRef      = useRef<THREE.Scene | null>(null)
  const cameraRef     = useRef<THREE.PerspectiveCamera | null>(null)
  const animFrameRef  = useRef<number>(0)
  const groupRef      = useRef<THREE.Group | null>(null)       // orbits Y
  const shardsRef     = useRef<ShardData[]>([])

  // Animation state refs
  const timeRef           = useRef(0)
  const rotSpeedRef       = useRef(0.4)
  const targetRotSpeedRef = useRef(0.4)
  const audioLevelRef     = useRef(0)
  const stateRef          = useRef<string>('active')

  // Color refs
  const curPrimaryRef  = useRef(new THREE.Color('#00C4E8'))
  const curAccentRef   = useRef(new THREE.Color('#00EEFF'))
  const tgtPrimaryRef  = useRef(new THREE.Color('#00C4E8'))
  const tgtAccentRef   = useRef(new THREE.Color('#00EEFF'))
  const glowColorRef   = useRef('#00D9FF')
  const emissiveRef    = useRef(0.7)
  const targetEmissiveRef = useRef(0.7)
  const pulseHzRef     = useRef(0.35)
  const targetPulseHzRef = useRef(0.35)

  // Shatter animation
  const isShatteringRef   = useRef(false)
  const shatterPhaseRef   = useRef(0)   // 0=idle, >0=flying out, >0.5=reassembling
  const SHATTER_DURATION  = 0.9         // seconds total for full shatter+reassemble

  // ── Build shards ─────────────────────────────────────────────────────────────

  const buildShards = useCallback((scene: THREE.Scene, group: THREE.Group) => {
    // Remove existing
    shardsRef.current.forEach(s => group.remove(s.mesh))
    shardsRef.current = []

    // Fibonacci sphere distribution for even coverage
    const goldenAngle = Math.PI * (3 - Math.sqrt(5))

    for (let i = 0; i < SHARD_COUNT; i++) {
      const t = i / (SHARD_COUNT - 1)
      const inclination = Math.acos(1 - 2 * t)
      const azimuth = goldenAngle * i

      const x = Math.sin(inclination) * Math.cos(azimuth)
      const y = Math.sin(inclination) * Math.sin(azimuth)
      const z = Math.cos(inclination)

      const surfacePos = new THREE.Vector3(x, y, z).multiplyScalar(ORB_RADIUS)

      // Shard size: vary with latitude for visual interest
      const latFactor = 0.6 + 0.4 * Math.abs(y)
      const w = (0.12 + Math.random() * 0.1) * latFactor
      const h = (0.22 + Math.random() * 0.14) * latFactor
      const d = 0.05 + Math.random() * 0.04

      const geo = buildShardGeometry(w, h, d)

      const mat = new THREE.MeshPhongMaterial({
        color:          new THREE.Color('#00C4E8'),
        emissive:       new THREE.Color('#003A5C'),
        emissiveIntensity: 0.7,
        shininess:      120,
        specular:       new THREE.Color('#AAFFFF'),
        transparent:    true,
        opacity:        0.82 + Math.random() * 0.15,
        side:           THREE.DoubleSide,
      })

      const mesh = new THREE.Mesh(geo, mat)
      mesh.position.copy(surfacePos)

      // Orient so shard face points outward from center
      const outward = surfacePos.clone().normalize()
      const up = new THREE.Vector3(0, 1, 0)
      const axis = new THREE.Vector3().crossVectors(up, outward).normalize()
      const angle = Math.acos(Math.max(-1, Math.min(1, up.dot(outward))))
      const homeQuat = angle < 0.001
        ? new THREE.Quaternion()
        : new THREE.Quaternion().setFromAxisAngle(axis, angle)
      mesh.quaternion.copy(homeQuat)

      // Random tumble quaternion for shatter
      const flyQuat = new THREE.Quaternion(
        (Math.random() - 0.5) * 2,
        (Math.random() - 0.5) * 2,
        (Math.random() - 0.5) * 2,
        1,
      ).normalize()

      group.add(mesh)

      shardsRef.current.push({
        mesh,
        homePos:   surfacePos.clone(),
        homeQuat:  homeQuat.clone(),
        flyDir:    outward.clone(),
        flyDist:   2.5 + Math.random() * 2.5,
        flyQuat,
        phase:     0,
        waveDelay: i / SHARD_COUNT,
        index:     i,
      })
    }

    void scene // keep linter happy
  }, [])

  // ── Scene setup ───────────────────────────────────────────────────────────────

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.setClearColor(0x000000, 0)
    rendererRef.current = renderer

    const w = container.clientWidth  || 400
    const h = container.clientHeight || 400
    renderer.setSize(w, h)
    container.appendChild(renderer.domElement)

    const scene = new THREE.Scene()
    sceneRef.current = scene

    const camera = new THREE.PerspectiveCamera(55, w / h, 0.1, 100)
    camera.position.z = 4.0
    cameraRef.current = camera

    // Lighting — dramatic 3-point for crystal refraction
    const ambient = new THREE.AmbientLight(0x0a1a2e, 0.6)
    scene.add(ambient)

    const keyLight = new THREE.PointLight(0x00D9FF, 3.0, 12)
    keyLight.position.set(3, 3, 4)
    scene.add(keyLight)

    const fillLight = new THREE.PointLight(0x7B2FFF, 1.5, 10)
    fillLight.position.set(-3, -1, 2)
    scene.add(fillLight)

    const rimLight = new THREE.PointLight(0xFFFFFF, 1.2, 8)
    rimLight.position.set(0, -3, -3)
    scene.add(rimLight)

    // Group that rotates
    const group = new THREE.Group()
    scene.add(group)
    groupRef.current = group

    buildShards(scene, group)

    // Resize observer
    const onResize = () => {
      const cw = container.clientWidth  || 400
      const ch = container.clientHeight || 400
      renderer.setSize(cw, ch)
      camera.aspect = cw / ch
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

      // Lerp values
      rotSpeedRef.current   = lerp(rotSpeedRef.current,   targetRotSpeedRef.current,  dt * 3)
      emissiveRef.current   = lerp(emissiveRef.current,   targetEmissiveRef.current,  dt * 2)
      pulseHzRef.current    = lerp(pulseHzRef.current,    targetPulseHzRef.current,   dt * 2)
      curPrimaryRef.current = lerpColor(curPrimaryRef.current, tgtPrimaryRef.current, dt * 2.5)
      curAccentRef.current  = lerpColor(curAccentRef.current,  tgtAccentRef.current,  dt * 2.5)

      // Group rotation
      if (groupRef.current) {
        groupRef.current.rotation.y += rotSpeedRef.current * dt
        groupRef.current.rotation.x += rotSpeedRef.current * 0.25 * dt
      }

      // Pulse scale (breathing)
      const hz = pulseHzRef.current
      let orbScale = 1.0
      if (hz > 0) orbScale += Math.sin(t * hz * Math.PI * 2) * 0.035
      orbScale += al * 0.12  // audio reactive

      // Shatter animation
      if (isShatteringRef.current) {
        shatterPhaseRef.current += dt / SHATTER_DURATION
        if (shatterPhaseRef.current >= 1) {
          shatterPhaseRef.current = 0
          isShatteringRef.current = false
        }
      }

      // Update each shard
      shardsRef.current.forEach((shard) => {
        const mat = shard.mesh.material as THREE.MeshPhongMaterial

        if (isShatteringRef.current) {
          const phase = shatterPhaseRef.current

          if (phase < 0.45) {
            // Flying out — staggered by waveDelay
            const localStart = shard.waveDelay * 0.25
            const flyT = Math.max(0, Math.min(1, (phase - localStart) / 0.35))
            const eased = easeInOutCubic(flyT)

            const flyPos = shard.homePos.clone()
              .add(shard.flyDir.clone().multiplyScalar(eased * shard.flyDist))
            shard.mesh.position.copy(flyPos.multiplyScalar(orbScale))

            // Tumble rotation
            shard.mesh.quaternion.slerpQuaternions(shard.homeQuat, shard.flyQuat, eased)

            // Flash bright on launch
            mat.emissiveIntensity = emissiveRef.current + eased * 1.5
            mat.opacity = lerp(0.9, 0.2, eased * eased)

          } else {
            // Reassemble — staggered in reverse
            const localStart = (1 - shard.waveDelay) * 0.25
            const reassembleOffset = 0.45
            const assembleT = Math.max(0, Math.min(1, (phase - reassembleOffset - localStart) / 0.45))
            const eased = easeOutBack(assembleT)

            // From fly position back to home
            const flyPos = shard.homePos.clone()
              .add(shard.flyDir.clone().multiplyScalar((1 - eased) * shard.flyDist))
            shard.mesh.position.copy(flyPos.multiplyScalar(orbScale))

            shard.mesh.quaternion.slerpQuaternions(shard.flyQuat, shard.homeQuat, eased)

            mat.emissiveIntensity = emissiveRef.current + (1 - eased) * 0.8
            mat.opacity = lerp(0.2, 0.82, eased)
          }

        } else {
          // Normal: rest at home position with scale + wave effects
          let shardScale = orbScale

          // Speaking: radial wave ripple
          if (curState === 'speaking') {
            const wavePhase = ((t * 1.2) - shard.waveDelay * 0.8) % 1
            const ripple = Math.max(0, Math.sin(wavePhase * Math.PI))
            shardScale += ripple * 0.18
          }

          // Thinking: per-shard random flicker
          if (curState === 'thinking') {
            const flicker = 0.85 + 0.15 * Math.sin(t * 23.7 + shard.index * 1.337)
            mat.emissiveIntensity = emissiveRef.current * flicker
          } else {
            mat.emissiveIntensity = lerp(mat.emissiveIntensity, emissiveRef.current, dt * 3)
          }

          // Listening: shards slightly separate with audio level
          if (curState === 'listening') {
            shardScale += al * 0.15 * (0.8 + 0.2 * Math.sin(shard.index * 0.7))
          }

          shard.mesh.position.copy(shard.homePos.clone().multiplyScalar(shardScale))
          shard.mesh.quaternion.copy(shard.homeQuat)

          mat.color.copy(curPrimaryRef.current)
          mat.emissive.copy(curPrimaryRef.current).multiplyScalar(0.35)
          mat.opacity = lerp(mat.opacity, 0.82, dt * 3)
        }
      })

      // CSS glow
      if (container) {
        const glowIntensity = 30 + emissiveRef.current * 20 + al * 15
        container.style.filter = `drop-shadow(0 0 ${glowIntensity}px ${glowColorRef.current})`
      }

      renderer.render(scene, camera)
    }

    animFrameRef.current = requestAnimationFrame(animate)

    return () => {
      cancelAnimationFrame(animFrameRef.current)
      ro.disconnect()
      renderer.dispose()
      if (container.contains(renderer.domElement)) container.removeChild(renderer.domElement)
    }
  }, [buildShards])

  // ── React to state changes ────────────────────────────────────────────────────

  useEffect(() => {
    const cfg = STATES[state] ?? STATES.active
    const prev = stateRef.current
    stateRef.current = state

    targetRotSpeedRef.current   = cfg.rotSpeed
    tgtPrimaryRef.current       = new THREE.Color(cfg.primaryHex)
    tgtAccentRef.current        = new THREE.Color(cfg.accentHex)
    glowColorRef.current        = cfg.glowHex
    targetEmissiveRef.current   = cfg.emissive
    targetPulseHzRef.current    = cfg.pulseHz

    // Trigger shatter on qualifying transitions
    if (cfg.shatterOnEnter && prev !== state && !isShatteringRef.current) {
      isShatteringRef.current = true
      shatterPhaseRef.current = 0
    }
  }, [state])

  // ── Sync audioLevel ───────────────────────────────────────────────────────────

  useEffect(() => {
    audioLevelRef.current = audioLevel
  }, [audioLevel])

  return (
    <div
      ref={containerRef}
      className="orb-canvas-container"
      onClick={onClick}
      style={{ width: '100%', height: '100%' }}
    />
  )
}
