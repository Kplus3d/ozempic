import { useRef, useEffect } from 'react'
import * as THREE from 'three'

interface Viewer3DProps {
  meshData?: {
    vertices: number[][]
    indices: number[]
    triangles: number
    faces: number
    volume: number
    surfaceArea: number
    boundingBox?: {
      min: number[]
      max: number[]
      center: number[]
      size: number[]
    }
  }
  fileName?: string
}

export function Viewer3D({ meshData, fileName }: Viewer3DProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const sceneRef = useRef<THREE.Scene | null>(null)
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null)
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null)
  const controlsRef = useRef<any>(null)
  const meshRef = useRef<THREE.Mesh | null>(null)
  const gridRef = useRef<THREE.GridHelper | null>(null)

  useEffect(() => {
    if (!containerRef.current) return

    // Setup scene
    const scene = new THREE.Scene()
    scene.background = new THREE.Color(0x0a0a0a)
    sceneRef.current = scene

    // Setup camera
    const camera = new THREE.PerspectiveCamera(
      75,
      containerRef.current.clientWidth / containerRef.current.clientHeight,
      0.1,
      10000
    )
    camera.position.set(100, 100, 100)
    cameraRef.current = camera

    // Setup renderer
    const renderer = new THREE.WebGLRenderer({ antialias: true })
    renderer.setSize(containerRef.current.clientWidth, containerRef.current.clientHeight)
    renderer.setPixelRatio(window.devicePixelRatio)
    containerRef.current.innerHTML = ''
    containerRef.current.appendChild(renderer.domElement)
    rendererRef.current = renderer

    // Manual orbit controls (simpler than OrbitControls)
    const controls = {
      target: new THREE.Vector3(0, 0, 0),
      enableDamping: true,
      dampingFactor: 0.05,
      update: () => {
        // Simple rotation tracking - we'll use mouse events
      }
    }
    controlsRef.current = controls as any

    // Mouse controls
    let isDragging = false
    let previousMousePosition = { x: 0, y: 0 }

    const handleMouseDown = (e: MouseEvent) => {
      isDragging = true
      previousMousePosition = { x: e.clientX, y: e.clientY }
    }

    const handleMouseMove = (e: MouseEvent) => {
      if (!isDragging || !cameraRef.current) return
      const deltaMove = {
        x: e.clientX - previousMousePosition.x,
        y: e.clientY - previousMousePosition.y
      }

      const rotateSpeed = 0.005
      const deltaRotationQuaternion = new THREE.Quaternion()
        .setFromEuler(new THREE.Euler(
          deltaMove.y * rotateSpeed,
          deltaMove.x * rotateSpeed,
          0,
          'XYZ'
        ))

      cameraRef.current.quaternion.multiplyQuaternions(deltaRotationQuaternion, cameraRef.current.quaternion)
      previousMousePosition = { x: e.clientX, y: e.clientY }
    }

    const handleMouseUp = () => {
      isDragging = false
    }

    const handleWheel = (e: WheelEvent) => {
      e.preventDefault()
      if (!cameraRef.current) return
      const zoomSpeed = 0.1
      const direction = new THREE.Vector3()
      cameraRef.current.getWorldDirection(direction)
      cameraRef.current.position.add(direction.multiplyScalar(e.deltaY * zoomSpeed))
    }

    containerRef.current.addEventListener('mousedown', handleMouseDown)
    containerRef.current.addEventListener('mousemove', handleMouseMove)
    containerRef.current.addEventListener('mouseup', handleMouseUp)
    containerRef.current.addEventListener('wheel', handleWheel, { passive: false })

    // Setup lights
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.4)
    scene.add(ambientLight)

    const directionalLight = new THREE.DirectionalLight(0xffffff, 0.8)
    directionalLight.position.set(100, 100, 100)
    scene.add(directionalLight)

    const directionalLight2 = new THREE.DirectionalLight(0xffffff, 0.3)
    directionalLight2.position.set(-100, -100, -100)
    scene.add(directionalLight2)

    // Setup grid
    const grid = new THREE.GridHelper(200, 20, 0x444444, 0x222222)
    scene.add(grid)
    gridRef.current = grid

    // Animation loop
    const animate = () => {
      requestAnimationFrame(animate)
      controls.update()
      renderer.render(scene, camera)
    }
    animate()

    // Handle resize
    const handleResize = () => {
      if (!containerRef.current || !cameraRef.current || !rendererRef.current) return
      const width = containerRef.current.clientWidth
      const height = containerRef.current.clientHeight
      cameraRef.current.aspect = width / height
      cameraRef.current.updateProjectionMatrix()
      rendererRef.current.setSize(width, height)
    }
    window.addEventListener('resize', handleResize)

    // Cleanup
    return () => {
      window.removeEventListener('resize', handleResize)
      if (rendererRef.current) {
        rendererRef.current.dispose()
      }
    }
  }, [])

  useEffect(() => {
    if (!sceneRef.current || !meshData) return

    // Remove previous mesh
    if (meshRef.current) {
      sceneRef.current.remove(meshRef.current)
    }

    // Remove previous grid
    if (gridRef.current) {
      sceneRef.current.remove(gridRef.current)
    }

    // Create geometry from mesh data
    const vertices = new Float32Array(meshData.vertices.length * 3)
    const indices = new Uint32Array(meshData.indices.length)

    for (let i = 0; i < meshData.vertices.length; i++) {
      vertices[i * 3] = meshData.vertices[i][0]
      vertices[i * 3 + 1] = meshData.vertices[i][1]
      vertices[i * 3 + 2] = meshData.vertices[i][2]
    }

    for (let i = 0; i < meshData.indices.length; i++) {
      indices[i] = meshData.indices[i]
    }

    const geometry = new THREE.BufferGeometry()
    geometry.setAttribute('position', new THREE.BufferAttribute(vertices, 3))
    geometry.setIndex(new THREE.BufferAttribute(indices, 1))
    geometry.computeVertexNormals()

    // Create material
    const material = new THREE.MeshPhongMaterial({
      color: 0x667eea,
      specular: 0x111111,
      shininess: 30,
      side: THREE.DoubleSide,
      wireframe: false,
      transparent: true,
      opacity: 0.9
    })

    const mesh = new THREE.Mesh(geometry, material)
    sceneRef.current.add(mesh)
    meshRef.current = mesh

    // Recreate grid
    const grid = new THREE.GridHelper(200, 20, 0x444444, 0x222222)
    sceneRef.current.add(grid)
    gridRef.current = grid

    // Adjust camera to fit the model
    if (meshData.boundingBox) {
      const size = meshData.boundingBox.size
      const maxDim = Math.max(size[0], size[1], size[2])
      if (maxDim > 0) {
        const scale = 150 / maxDim
        cameraRef.current?.position.set(100 * scale, 100 * scale, 100 * scale)
        controlsRef.current?.target.set(0, 0, 0)
        controlsRef.current?.update()
      }
    }
  }, [meshData])

  if (!meshData) {
    return (
      <div style={{ width: '100%', height: '450px', background: '#0a0a0a', borderRadius: '8px', overflow: 'hidden', position: 'relative' }}>
        <div style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          height: '100%',
          color: '#666',
          fontSize: '16px'
        }}>
          <div style={{ fontSize: '64px', marginBottom: '20px', opacity: 0.5 }}>📐</div>
          <div style={{ marginBottom: '10px' }}>3D Preview Not Available</div>
          <div style={{ fontSize: '14px', color: '#888', textAlign: 'center', padding: '0 20px' }}>
            Upload a file to see a 3D preview.
            <br />
            Supports STEP, SolidWorks, STL, OBJ, and IGES files.
          </div>
        </div>
      </div>
    )
  }

  return (
    <div style={{ width: '100%', height: '450px', background: '#0a0a0a', borderRadius: '8px', overflow: 'hidden', position: 'relative' }}>
      <div ref={containerRef} style={{ width: '100%', height: '100%' }} />
      {/* Overlay info */}
      <div style={{
        position: 'absolute',
        top: '10px',
        left: '10px',
        background: 'rgba(0,0,0,0.7)',
        padding: '10px',
        borderRadius: '8px',
        color: '#fff',
        fontSize: '12px',
        maxWidth: '250px'
      }}>
        <div style={{ fontWeight: 600, marginBottom: '5px' }}>
          {fileName || '3D Preview'}
        </div>
        <div>Triangles: {meshData.triangles.toLocaleString()}</div>
        <div>Volume: {meshData.volume?.toLocaleString?.() ?? 'N/A'} mm³</div>
        <div>Surface Area: {meshData.surfaceArea?.toLocaleString?.() ?? 'N/A'} mm²</div>
        <div style={{ marginTop: '5px', color: '#888' }}>
          Drag to rotate • Scroll to zoom
        </div>
      </div>
    </div>
  )
}
