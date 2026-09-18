import { useState } from 'react'

// Constants
export const MAX_FILE_SIZE = 50 * 1024 * 1024; // 50MB
export const supportedFormats = [
  'step', 'stp',  // STEP files
  'sldprt', 'sldasm',  // SolidWorks
  'stl', 'obj',  // Mesh formats
  'iges', 'igs',  // IGES files
];

export function isValidFormat(filename: string): boolean {
  const ext = filename.split('.').pop()?.toLowerCase() || '';
  return supportedFormats.includes(ext);
}

export function formatLabel(filename: string): string {
  const ext = filename.split('.').pop()?.toLowerCase() || '';
  const formatNames: Record<string, string> = {
    'step': 'STEP',
    'stp': 'STEP',
    'sldprt': 'SolidWorks Part',
    'sldasm': 'SolidWorks Assembly',
    'stl': 'STL',
    'obj': 'OBJ',
    'iges': 'IGES',
    'igs': 'IGES',
  };
  return formatNames[ext] || ext.toUpperCase();
}

export function supportedFormatsList(): string {
  return 'STEP, SolidWorks, STL, OBJ, IGES';
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(2) + ' MB';
}

export function isValidSize(bytes: number): boolean {
  return bytes <= MAX_FILE_SIZE;
}

interface StepUploaderProps {
  onFileSelected: (file: File) => void
  isUploading?: boolean
}

export function StepUploader({ onFileSelected, isUploading = false }: StepUploaderProps) {
  const [isDragging, setIsDragging] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')
  
  const handleFile = (file: File) => {
    // Validate format
    if (!isValidFormat(file.name)) {
      setErrorMessage('Unsupported file format. Please use STEP, SolidWorks, STL, OBJ, or IGES files.');
      return;
    }
    
    // Validate size
    if (!isValidSize(file.size)) {
      setErrorMessage(`File too large. Maximum size is ${formatFileSize(MAX_FILE_SIZE)}.`);
      return;
    }
    
    setErrorMessage('');
    onFileSelected(file);
  };
  
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
    const file = e.dataTransfer.files[0]
    if (file) {
      handleFile(file)
    }
  }
  
  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      handleFile(file)
    }
  }
  
  return (
    <div
      onDrop={handleDrop}
      onDragOver={(e) => e.preventDefault()}
      onDragEnter={() => setIsDragging(true)}
      onDragLeave={() => setIsDragging(false)}
      style={{
        border: `2px dashed ${isDragging ? '#667eea' : '#444'}`,
        borderRadius: '16px',
        padding: '60px 40px',
        textAlign: 'center',
        cursor: isUploading ? 'not-allowed' : 'pointer',
        transition: 'all 0.3s ease',
        background: isDragging ? 'rgba(102, 126, 234, 0.1)' : 'transparent',
        marginBottom: '30px',
        opacity: isUploading ? 0.6 : 1,
        pointerEvents: isUploading ? 'none' : 'auto'
      }}
    >
      <input
        type="file"
        accept=".step,.stp,.sldprt,.sldasm,.stl,.obj,.iges,.igs"
        onChange={handleInputChange}
        style={{ display: 'none' }}
        id="step-file-input"
        disabled={isUploading}
      />
      <label htmlFor="step-file-input" style={{ cursor: 'pointer', display: 'block' }}>
        <div style={{ fontSize: '48px', marginBottom: '20px' }}>
          {isUploading ? '⏳' : '📁'}
        </div>
        <p style={{ 
          fontSize: '20px', 
          margin: '0 0 10px 0',
          fontWeight: 600,
          color: isDragging ? '#667eea' : (isUploading ? '#999' : '#fff')
        }}>
          {isDragging ? 'Drop your file here' : (isUploading ? 'Processing...' : 'Drag & drop your CAD file')}
        </p>
        <p style={{ 
          fontSize: '14px', 
          color: '#666', 
          margin: 0
        }}>
          or click to browse ({supportedFormatsList()}, max {formatFileSize(MAX_FILE_SIZE)})
        </p>
      </label>
      {errorMessage && (
        <div style={{ 
          color: '#ff6b6b', 
          marginTop: '10px',
          fontSize: '14px',
          padding: '8px 12px',
          background: 'rgba(255, 107, 107, 0.1)',
          borderRadius: '6px'
        }}>
          ⚠️ {errorMessage}
        </div>
      )}
    </div>
  )
}
