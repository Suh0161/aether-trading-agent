import { useEffect, useState } from 'react'
import './Toast.css'

function Toast({ message, type = 'info' }) {
  const [isVisible, setIsVisible] = useState(false)

  useEffect(() => {
    setTimeout(() => setIsVisible(true), 10)
    const timer = setTimeout(() => setIsVisible(false), 3800)
    return () => clearTimeout(timer)
  }, [])

  const icons = {
    success: '✓',
    error: '✕',
    info: 'ℹ',
    warning: '⚠'
  }

  return (
    <div className={`toast toast-${type} ${isVisible ? 'visible' : ''}`}>
      <span className="toast-icon">{icons[type]}</span>
      <span className="toast-message">{message}</span>
    </div>
  )
}

export default Toast
