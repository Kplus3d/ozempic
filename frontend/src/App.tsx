import { useState, useCallback } from 'react'
import { StepUploader, formatLabel } from './components/StepUploader'
import { Viewer3D } from './components/Viewer3D'
import { ThicknessControl } from './components/ThicknessControl'

interface FileInfo {
  name: string
  size: number
  type: string
  faces?: number
  edges?: number
  volume?: number
  surfaceArea?: number
  boundingBox?: { min: number[], max: number[] }
}

interface MeshData {
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

export default function App() {
  const [file, setFile] = useState<File | null>(null)
  const [fileInfo, setFileInfo] = useState<FileInfo | null>(null)
  const [meshData, setMeshData] = useState<MeshData | null>(null)
  const [fileName, setFileName] = useState<string>('')
  const [thickness, setThickness] = useState<number>(2.0)
  const [processing, setProcessing] = useState(false)
  const [progress, setProgress] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [previewError, setPreviewError] = useState<string | null>(null)
  const [processingInfo, setProcessingInfo] = useState<{
    inputVolume?: number
    outputVolume?: number
    volumeChange?: number
  } | null>(null)

  const handleFileSelected = useCallback(async (selectedFile: File) => {
    setFile(selectedFile)
    setFileName(selectedFile.name)
    setMeshData(null)
    setFileInfo(null)
    setError(null)
    setSuccess(false)
    setProcessingInfo(null)
    setPreviewError(null)
    
    // Set file type
    const fileType = formatLabel(selectedFile.name)
    
    // Validate and get geometry info
    try {
      const formData = new FormData()
      formData.append('file', selectedFile)
      
      const response = await fetch('/api/validate', {
        method: 'POST',
        body: formData
      })
      
      if (response.ok) {
        const data = await response.json()
        setFileInfo({
          name: selectedFile.name,
          size: selectedFile.size,
          type: fileType,
          faces: data.num_faces,
          edges: data.num_edges,
          volume: data.volume,
          surfaceArea: data.surface_area,
          boundingBox: data.bounding_box
        })
      }
    } catch (err) {
      console.error('Validation failed:', err)
      setError('Failed to validate file. Please check the file format.')
    }
    
    // Load 3D preview with loading state
    setPreviewLoading(true)
    setPreviewError(null)
    try {
      const previewFormData = new FormData()
      previewFormData.append('file', selectedFile)
      
      const previewResponse = await fetch('/api/preview', {
        method: 'POST',
        body: previewFormData
      })
      
      if (previewResponse.ok) {
        const previewData = await previewResponse.json()
        if (previewData.success) {
          setMeshData({
            vertices: previewData.vertices,
            indices: previewData.indices,
            triangles: previewData.triangles,
            faces: previewData.faces,
            volume: previewData.volume,
            surfaceArea: previewData.surface_area,
            boundingBox: previewData.bounding_box
          })
        } else {
          throw new Error(previewData.error || 'Preview generation failed')
        }
      } else {
        throw new Error('Preview generation failed')
      }
    } catch (err) {
      console.error('Preview failed:', err)
      setPreviewError('3D preview generation failed. You can still modify thickness.')
    } finally {
      setPreviewLoading(false)
    }
  }, [])

  const handleProcess = async () => {
    if (!file) return
    
    setProcessing(true)
    setProgress(0)
    setError(null)
    setSuccess(false)
    setProcessingInfo(null)
    
    try {
      // Create form data with only the file
      const formData = new FormData()
      formData.append('file', file)
      
      // Use XMLHttpRequest for progress tracking
      const xhr = new XMLHttpRequest()
      
      // Send thickness as query parameter (correct way!)
      xhr.open('POST', `/api/process?thickness=${thickness}`)
      
      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable) {
          const percentComplete = (event.loaded / event.total) * 50
          setProgress(Math.round(percentComplete))
        }
      }
      
      xhr.onload = () => {
        setProgress(100)
        
        if (xhr.status === 200) {
          // Download the file
          const blob = new Blob([xhr.response], { type: 'application/octet-stream' })
          const url = URL.createObjectURL(blob)
          const a = document.createElement('a')
          a.href = url
          
          // Handle different file extensions for download
          const baseName = file.name.replace(/\.(step|stp|sldprt|sldasm|stl|obj|iges|igs)$/i, '')
          a.download = `${baseName}_ozempic_modified.step`
          
          document.body.appendChild(a)
          a.click()
          document.body.removeChild(a)
          URL.revokeObjectURL(url)
          
          // Extract processing info from headers
          const inputVol = xhr.getResponseHeader('X-Input-Volume')
          const outputVol = xhr.getResponseHeader('X-Output-Volume')
          const volChange = xhr.getResponseHeader('X-Volume-Change')
          
          if (inputVol || outputVol) {
            setProcessingInfo({
              inputVolume: parseFloat(inputVol || '0'),
              outputVolume: parseFloat(outputVol || '0'),
              volumeChange: parseFloat(volChange || '0')
            })
          }
          
          setSuccess(true)
        } else {
          try {
            const errorData = JSON.parse(xhr.responseText)
            setError(errorData.detail || 'Processing failed')
          } catch {
            setError('Processing failed. Check console for details.')
          }
        }
        
        setProcessing(false)
      }
      
      xhr.onerror = () => {
        setError('Network error. Please try again.')
        setProcessing(false)
      }
      
      xhr.responseType = 'blob'
      xhr.send(formData)
      
    } catch (err) {
      console.error('Processing failed:', err)
      setError('Processing failed. Check console for details.')
      setProcessing(false)
    }
  }

  const handleReset = () => {
    setFile(null)
    setFileInfo(null)
    setMeshData(null)
    setFileName('')
    setProcessing(false)
    setProgress(null)
    setError(null)
    setSuccess(false)
    setPreviewLoading(false)
    setPreviewError(null)
    setProcessingInfo(null)
  }

  return (
    <div style={{ 
      maxWidth: '1200px', 
      margin: '0 auto', 
      padding: '40px 20px',
      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif'
    }}>
      <header style={{ 
        textAlign: 'center', 
        marginBottom: '40px',
        padding: '20px 0',
        borderBottom: '1px solid #333'
      }}>
        <h1 style={{ 
          fontSize: '42px', 
          fontWeight: 700,
          background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
          WebkitBackgroundClip: 'text',
          WebkitTextFillColor: 'transparent',
          margin: '0 0 10px 0'
        }}>
          Ozempic
        </h1>
        <p style={{ 
          color: '#a0a0a0', 
          fontSize: '18px',
          fontWeight: 400
        }}>
          3D CAD File Thickness Modifier
        </p>
        <p style={{ 
          color: '#666', 
          fontSize: '14px',
          fontWeight: 400
        }}>
          Supports: STEP, SolidWorks, STL, OBJ, IGES
        </p>
      </header>
      
      <StepUploader onFileSelected={handleFileSelected} isUploading={processing} />
      
      {file && (
        <div style={{ marginTop: '30px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '30px' }}>
          {/* Left Column - Controls */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
            {/* File Info */}
            <div style={{
              background: '#1a1a1a',
              border: '1px solid #333',
              borderRadius: '12px',
              padding: '20px'
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '15px' }}>
                <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 600, color: '#fff' }}>
                  File Information
                </h3>
                <button 
                  onClick={handleReset}
                  style={{
                    background: '#333',
                    color: '#fff',
                    border: '1px solid #444',
                    borderRadius: '6px',
                    padding: '6px 12px',
                    fontSize: '12px',
                    cursor: 'pointer',
                    transition: 'all 0.2s'
                  }}
                  onMouseEnter={(e) => (e.currentTarget.style.background = '#444')}
                  onMouseLeave={(e) => (e.currentTarget.style.background = '#333')}
                >
                  Reset
                </button>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                <div>
                  <div style={{ fontSize: '12px', color: '#666' }}>Name</div>
                  <div style={{ fontSize: '14px', color: '#fff', wordBreak: 'break-all' }}>{file.name}</div>
                </div>
                <div>
                  <div style={{ fontSize: '12px', color: '#666' }}>Type</div>
                  <div style={{ fontSize: '14px', color: '#fff' }}>{fileInfo?.type}</div>
                </div>
                <div>
                  <div style={{ fontSize: '12px', color: '#666' }}>Size</div>
                  <div style={{ fontSize: '14px', color: '#fff' }}>{(file.size / 1024 / 1024).toFixed(2)} MB</div>
                </div>
                {fileInfo?.faces !== undefined && (
                  <>
                    <div>
                      <div style={{ fontSize: '12px', color: '#666' }}>Faces</div>
                      <div style={{ fontSize: '14px', color: '#fff' }}>{fileInfo.faces}</div>
                    </div>
                    <div>
                      <div style={{ fontSize: '12px', color: '#666' }}>Edges</div>
                      <div style={{ fontSize: '14px', color: '#fff' }}>{fileInfo.edges}</div>
                    </div>
                  </>
                )}
                {fileInfo?.volume !== undefined && (
                  <div>
                    <div style={{ fontSize: '12px', color: '#666' }}>Volume</div>
                    <div style={{ fontSize: '14px', color: '#fff' }}>{fileInfo.volume?.toFixed(2)} mm³</div>
                  </div>
                )}
                {fileInfo?.surfaceArea !== undefined && (
                  <div>
                    <div style={{ fontSize: '12px', color: '#666' }}>Surface Area</div>
                    <div style={{ fontSize: '14px', color: '#fff' }}>{fileInfo.surfaceArea?.toFixed(2)} mm²</div>
                  </div>
                )}
                {fileInfo?.boundingBox && (
                  <div style={{ gridColumn: '1 / -1' }}>
                    <div style={{ fontSize: '12px', color: '#666' }}>Bounding Box</div>
                    <div style={{ fontSize: '14px', color: '#fff' }}>
                      [{fileInfo.boundingBox.min.map(v => v.toFixed(2)).join(', ')}] to [{fileInfo.boundingBox.max.map(v => v.toFixed(2)).join(', ')}]
                    </div>
                  </div>
                )}
              </div>
            </div>
            
            {/* Thickness Control */}
            <div style={{
              background: '#1a1a1a',
              border: '1px solid #333',
              borderRadius: '12px',
              padding: '20px'
            }}>
              <ThicknessControl 
                value={thickness} 
                onChange={setThickness}
                min={0.1}
                max={20}
                step={0.1}
              />
              
              <button
                onClick={handleProcess}
                disabled={processing || !file}
                style={{
                  width: '100%',
                  padding: '14px',
                  background: processing ? '#666' : 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                  color: 'white',
                  border: 'none',
                  borderRadius: '8px',
                  fontSize: '16px',
                  fontWeight: 600,
                  cursor: processing ? 'not-allowed' : (file ? 'pointer' : 'not-allowed'),
                  marginTop: '20px',
                  transition: 'transform 0.2s, box-shadow 0.2s',
                  opacity: processing ? 0.7 : 1
                }}
              >
                {processing ? 'Processing...' : 'Modify Thickness'}
              </button>
            </div>
            
            {/* Progress Bar */}
            {processing && progress !== null && (
              <div style={{
                background: '#1a1a1a',
                border: '1px solid #333',
                borderRadius: '12px',
                padding: '20px'
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '10px' }}>
                  <span style={{ color: '#fff', fontSize: '14px' }}>Processing...</span>
                  <span style={{ color: '#667eea', fontSize: '14px' }}>{progress}%</span>
                </div>
                <div style={{ 
                  width: '100%', 
                  height: '8px', 
                  background: '#333', 
                  borderRadius: '4px',
                  overflow: 'hidden'
                }}>
                  <div style={{ 
                    width: `${progress}%`, 
                    height: '100%', 
                    background: 'linear-gradient(90deg, #667eea, #764ba2)',
                    transition: 'width 0.3s ease'
                  }} />
                </div>
              </div>
            )}
            
            {/* Processing Info */}
            {processingInfo && (
              <div style={{
                background: '#1a1a1a',
                border: '1px solid #333',
                borderRadius: '12px',
                padding: '20px'
              }}>
                <h3 style={{ margin: '0 0 15px 0', fontSize: '16px', fontWeight: 600, color: '#fff' }}>
                  Processing Results
                </h3>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                  <div>
                    <div style={{ fontSize: '12px', color: '#666' }}>Input Volume</div>
                    <div style={{ fontSize: '14px', color: '#fff' }}>{processingInfo.inputVolume?.toFixed(2)} mm³</div>
                  </div>
                  <div>
                    <div style={{ fontSize: '12px', color: '#666' }}>Output Volume</div>
                    <div style={{ fontSize: '14px', color: '#fff' }}>{processingInfo.outputVolume?.toFixed(2)} mm³</div>
                  </div>
                  <div style={{ gridColumn: '1 / -1' }}>
                    <div style={{ fontSize: '12px', color: '#666' }}>Volume Change</div>
                    <div style={{ fontSize: '14px', color: processingInfo.volumeChange! < 0 ? '#ff6b6b' : '#2ecc71' }}>
                      {processingInfo.volumeChange?.toFixed(2)} mm³ ({((processingInfo.volumeChange! / processingInfo.inputVolume!) * 100).toFixed(1)}%)
                    </div>
                  </div>
                </div>
              </div>
            )}
            
            {/* Status Messages */}
            {error && (
              <div style={{
                background: '#2d1f1f',
                border: '1px solid #ff4757',
                borderRadius: '8px',
                padding: '15px',
                color: '#ff6b6b'
              }}>
                ⚠️ {error}
              </div>
            )}
            
            {success && (
              <div style={{
                background: '#1f2d1f',
                border: '1px solid #2ecc71',
                borderRadius: '8px',
                padding: '15px',
                color: '#2ecc71'
              }}>
                ✓ Modification complete! File downloaded.
              </div>
            )}
          </div>
          
          {/* Right Column - 3D Preview */}
          <div style={{
            background: '#1a1a1a',
            border: '1px solid #333',
            borderRadius: '12px',
            padding: '20px',
            minHeight: '500px'
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '15px' }}>
              <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 600, color: '#fff' }}>
                3D Preview
              </h3>
              {previewLoading && (
                <span style={{ color: '#667eea', fontSize: '14px' }}>Loading preview...</span>
              )}
            </div>
            
            {previewError ? (
              <div style={{
                background: '#2d1f1f',
                border: '1px solid #ff4757',
                borderRadius: '8px',
                padding: '15px',
                color: '#ff6b6b',
                minHeight: '200px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center'
              }}>
                <div style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: '48px', marginBottom: '10px' }}>⚠️</div>
                  <div>{previewError}</div>
                </div>
              </div>
            ) : meshData ? (
              <div>
                <div style={{ 
                  background: '#000', 
                  borderRadius: '8px', 
                  padding: '10px',
                  marginBottom: '10px'
                }}>
                  <div style={{ fontSize: '12px', color: '#fff', fontWeight: 600 }}>{file.name}</div>
                  <div style={{ fontSize: '11px', color: '#aaa' }}>
                    Triangles: {meshData.triangles.toLocaleString()}<br />
                    Volume: {meshData.volume.toLocaleString()} mm³<br />
                    Surface Area: {meshData.surfaceArea.toLocaleString()} mm²
                  </div>
                  <div style={{ fontSize: '11px', color: '#888', marginTop: '5px' }}>
                    Drag to rotate • Scroll to zoom
                  </div>
                </div>
                <Viewer3D meshData={meshData} fileName={fileName} />
              </div>
            ) : (
              <div style={{
                background: '#000',
                borderRadius: '8px',
                padding: '40px 20px',
                minHeight: '200px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                flexDirection: 'column',
                color: '#666'
              }}>
                <div style={{ fontSize: '48px', marginBottom: '10px' }}>📐</div>
                <div style={{ fontSize: '14px', textAlign: 'center' }}>
                  Upload a file to see the 3D preview
                </div>
              </div>
            )}
          </div>
        </div>
      )}
      
      <footer style={{
        textAlign: 'center',
        marginTop: '60px',
        padding: '20px 0',
        borderTop: '1px solid #333',
        color: '#666',
        fontSize: '14px'
      }}>
        Ozempic — 3D CAD File Thickness Modifier
      </footer>
    </div>
  )
}
