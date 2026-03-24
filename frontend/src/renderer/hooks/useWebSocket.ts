/**
 * useWebSocket Hook - Hook de React para WebSocket.
 *
 * Este hook facilita el uso del WebSocketService en componentes de React,
 * manejando automáticamente la conexión/desconexión y la limpieza de recursos.
 *
 * @example
 * function App() {
 *   const { send, on, isConnected } = useWebSocket();
 *
 *   useEffect(() => {
 *     on('wake_word_detected', (data) => {
 *       console.log('Wake word detected!', data);
 *     });
 *   }, []);
 *
 *   return <div>Connected: {isConnected ? 'Yes' : 'No'}</div>;
 * }
 */

import { useEffect, useState, useCallback } from 'react';
import { wsService } from '../services/websocket';

interface UseWebSocketReturn {
  /**
   * Envía un evento al backend.
   */
  send: (type: string, data?: any) => void;

  /**
   * Registra un listener para un evento.
   */
  on: (eventType: string, handler: (data: any) => void) => void;

  /**
   * Remueve un listener de un evento.
   */
  off: (eventType: string, handler: (data: any) => void) => void;

  /**
   * Estado de la conexión.
   */
  isConnected: boolean;

  /**
   * Desconecta manualmente el WebSocket.
   */
  disconnect: () => void;

  /**
   * Reconecta manualmente el WebSocket.
   */
  reconnect: () => void;
}

/**
 * Hook de React para manejar conexión WebSocket con el backend Atlas AI.
 *
 * Este hook:
 * - Se conecta automáticamente al montar
 * - Se desconecta automáticamente al desmontar
 * - Proporciona funciones para enviar/escuchar eventos
 * - Mantiene el estado de conexión
 *
 * @returns Objeto con funciones y estado del WebSocket
 */
export function useWebSocket(): UseWebSocketReturn {
  const [isConnected, setIsConnected] = useState(false);

  // Funciones memoizadas
  const send = useCallback((type: string, data?: any) => {
    wsService.send(type, data);
  }, []);

  const on = useCallback((eventType: string, handler: (data: any) => void) => {
    wsService.on(eventType, handler);
  }, []);

  const off = useCallback(
    (eventType: string, handler: (data: any) => void) => {
      wsService.off(eventType, handler);
    },
    []
  );

  const disconnect = useCallback(() => {
    wsService.disconnect();
  }, []);

  const reconnect = useCallback(() => {
    wsService.disconnect();
    setTimeout(() => {
      wsService.connect();
    }, 100);
  }, []);

  useEffect(() => {
    // Handler para evento de conexión
    const handleConnected = () => {
      console.log('[useWebSocket] Connected event received');
      setIsConnected(true);
    };

    // Handler para evento de desconexión
    const handleDisconnected = () => {
      console.log('[useWebSocket] Disconnected event received');
      setIsConnected(false);
    };

    // Registrar event listeners
    wsService.on('connected', handleConnected);
    wsService.on('disconnected', handleDisconnected);

    // Conectar al montar
    console.log('[useWebSocket] Mounting - connecting to WebSocket');
    wsService.connect();

    // Cleanup al desmontar — solo remover los handlers locales.
    // No llamar wsService.disconnect() aquí porque wsService es un singleton
    // que vive toda la vida de la app. En React 18 StrictMode los componentes
    // se montan, desmontan y remontan intencionalmente; llamar disconnect()
    // en el cleanup cerraba la conexión WebSocket real y mataba todos los loops
    // del backend (~2s después de iniciar). La desconexión intencional se hace
    // solo desde el botón de mute o al cerrar la ventana.
    return () => {
      console.log('[useWebSocket] Unmounting - removing local handlers');
      wsService.off('connected', handleConnected);
      wsService.off('disconnected', handleDisconnected);
    };
  }, []);

  return {
    send,
    on,
    off,
    isConnected,
    disconnect,
    reconnect,
  };
}
