/**
 * Toast Component — Simple notification
 */

import React from 'react'
import { Check, AlertCircle, Info } from 'lucide-react'

export interface ToastProps {
  type: 'success' | 'error' | 'info'
  message: string
}

export const Toast: React.FC<ToastProps> = ({ type, message }) => {
  const iconMap = {
    success: <Check size={16} />,
    error: <AlertCircle size={16} />,
    info: <Info size={16} />,
  }

  return (
    <div className={`toast ${type}`}>
      <span className="toast-icon">{iconMap[type]}</span>
      <span>{message}</span>
    </div>
  )
}
