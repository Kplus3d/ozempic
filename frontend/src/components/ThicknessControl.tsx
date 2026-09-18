interface ThicknessControlProps {
  value: number
  onChange: (value: number) => void
  min?: number
  max?: number
  step?: number
}

export function ThicknessControl({
  value,
  onChange,
  min = 0.1,
  max = 50,
  step = 0.1
}: ThicknessControlProps) {
  return (
    <div>
      <div style={{ 
        display: 'flex', 
        justifyContent: 'space-between', 
        alignItems: 'center',
        marginBottom: '15px'
      }}>
        <label style={{ 
          fontWeight: 600, 
          color: '#fff',
          fontSize: '14px'
        }}>
          Wall Thickness (mm)
        </label>
        <div style={{
          background: '#333',
          borderRadius: '6px',
          padding: '8px 12px',
          minWidth: '80px',
          textAlign: 'center'
        }}>
          <span style={{ 
            fontSize: '20px', 
            fontWeight: 700,
            color: '#667eea'
          }}>
            {value.toFixed(1)}
          </span>
          <span style={{ 
            fontSize: '12px', 
            color: '#666',
            marginLeft: '4px'
          }}>mm</span>
        </div>
      </div>
      
      <input
        type="range"
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        min={min}
        max={max}
        step={step}
        style={{ 
          width: '100%',
          height: '6px',
          borderRadius: '3px',
          outline: 'none',
          WebkitAppearance: 'none',
          background: `linear-gradient(to right, #667eea 0%, #764ba2 ${((value - min) / (max - min)) * 100}%, #333 ${((value - min) / (max - min)) * 100}%, #333 100%)`
        }}
      />
      
      <div style={{ 
        display: 'flex', 
        justifyContent: 'space-between',
        marginTop: '8px',
        fontSize: '12px',
        color: '#666'
      }}>
        <span>Min: {min}mm</span>
        <span>Max: {max}mm</span>
      </div>
    </div>
  )
}
