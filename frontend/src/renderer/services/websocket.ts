/**
 * WebSocket Service - Servicio de comunicación WebSocket con el backend.
 *
 * Este servicio mantiene una conexión WebSocket continua con el backend Atlas AI,
 * permitiendo comunicación bidireccional en tiempo real.
 *
 * Características:
 * - Auto-reconexión en caso de desconexión
 * - Sistema de eventos para escuchar mensajes del backend
 * - Envío de eventos al backend
 * - Manejo de errores robusto
 */

type EventHandler = (data: any) => void;

interface WebSocketEvent {
  type: string;
  data?: any;
}

class WebSocketService {
  private ws: WebSocket | null = null;
  private url: string;
  private reconnectInterval: number = 3000; // 3 segundos
  private eventHandlers: Map<string, EventHandler[]> = new Map();
  private isIntentionalClose: boolean = false;
  private reconnectAttempts: number = 0;
  private maxReconnectAttempts: number = 50;
  private connectTimeoutId: ReturnType<typeof setTimeout> | null = null;

  /**
   * Constructor del WebSocketService.
   *
   * @param url - URL del endpoint WebSocket (default: ws://localhost:8000/api/ws)
   */
  constructor(
    url: string = (import.meta.env.VITE_WS_URL as string | undefined) ?? 'ws://localhost:8000/api/ws'
  ) {
    this.url = url;
    console.log('[WebSocket] Service initialized with URL:', this.url);
  }

  /**
   * Conecta al servidor WebSocket.
   *
   * Establece la conexión y configura los event handlers.
   * Si la conexión falla, intentará reconectar automáticamente.
   */
  connect(): void {
    // Prevenir conexiones duplicadas
    if (this.ws?.readyState === WebSocket.OPEN) {
      console.log('[WebSocket] Already connected');
      return;
    }

    if (this.ws?.readyState === WebSocket.CONNECTING) {
      console.log('[WebSocket] Connection already in progress');
      return;
    }

    try {
      // Resetear flag de cierre intencional para que auto-reconexión funcione
      // después de que el usuario llame disconnect() seguido de connect().
      this.isIntentionalClose = false;
      console.log('[WebSocket] Connecting to:', this.url);
      this.ws = new WebSocket(this.url);
      this.setupEventHandlers();

      // Timeout: if still CONNECTING after 5s (TCP accepted but WS handshake
      // not completing), close and let onclose trigger the next retry.
      if (this.connectTimeoutId) clearTimeout(this.connectTimeoutId);
      this.connectTimeoutId = setTimeout(() => {
        if (this.ws?.readyState === WebSocket.CONNECTING) {
          console.log('[WebSocket] Connection timeout — retrying...');
          this.ws.close();
        }
        this.connectTimeoutId = null;
      }, 5000);
    } catch (error) {
      console.error('[WebSocket] Connection error:', error);
      this.scheduleReconnect();
    }
  }

  /**
   * Configura los event handlers del WebSocket nativo.
   */
  private setupEventHandlers(): void {
    if (!this.ws) return;

    this.ws.onopen = () => {
      console.log('[WebSocket] ✅ Connected successfully');
      this.reconnectAttempts = 0;
      if (this.connectTimeoutId) {
        clearTimeout(this.connectTimeoutId);
        this.connectTimeoutId = null;
      }
      this.emit('connected', {
        timestamp: new Date().toISOString(),
      });
    };

    this.ws.onmessage = (event) => {
      try {
        const data: WebSocketEvent = JSON.parse(event.data);
        console.log('[WebSocket] ⬇️ Received:', data.type);

        // Emitir el evento a los listeners registrados
        if (data.type) {
          this.emit(data.type, data.data || data);
        }
      } catch (error) {
        console.error('[WebSocket] Error parsing message:', error);
      }
    };

    this.ws.onerror = (error) => {
      console.error('[WebSocket] ❌ Error:', error);
      this.emit('error', { error });
    };

    this.ws.onclose = (event) => {
      console.log('[WebSocket] ⛔ Closed:', event.code, event.reason);

      this.emit('disconnected', {
        code: event.code,
        reason: event.reason,
        timestamp: new Date().toISOString(),
      });

      // Auto-reconectar si no fue un cierre intencional
      if (!this.isIntentionalClose) {
        this.scheduleReconnect();
      }
    };
  }

  /**
   * Programa un intento de reconexión.
   */
  private scheduleReconnect(): void {
    // Don't count as an attempt if we're already waiting on a connection.
    if (this.ws?.readyState === WebSocket.CONNECTING) return;

    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error(
        '[WebSocket] Max reconnection attempts reached. Stopping reconnect.'
      );
      this.emit('reconnect_failed', {
        attempts: this.reconnectAttempts,
      });
      return;
    }

    this.reconnectAttempts++;
    const delay = Math.min(
      this.reconnectInterval * Math.pow(1.5, Math.min(this.reconnectAttempts - 1, 8)),
      30000
    );
    console.log(
      `[WebSocket] Scheduling reconnect attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts} in ${Math.round(delay)}ms`
    );

    setTimeout(() => {
      console.log('[WebSocket] Attempting to reconnect...');
      this.connect();
    }, delay);
  }

  /**
   * Desconecta el WebSocket.
   *
   * Cierra la conexión de manera limpia y previene auto-reconexión.
   */
  disconnect(): void {
    console.log('[WebSocket] Disconnecting...');
    this.isIntentionalClose = true;

    if (this.ws) {
      this.ws.close(1000, 'Intentional disconnect');
      this.ws = null;
    }
  }

  /**
   * Envía un evento al backend via WebSocket.
   *
   * @param type - Tipo del evento
   * @param data - Datos del evento (opcional)
   */
  send(type: string, data?: any): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      console.warn('[WebSocket] Cannot send, not connected:', type);
      return;
    }

    try {
      const message: WebSocketEvent = { type, data };
      this.ws.send(JSON.stringify(message));
      console.log('[WebSocket] ⬆️ Sent:', type);
    } catch (error) {
      console.error('[WebSocket] Error sending message:', error);
    }
  }

  /**
   * Registra un listener para un tipo de evento específico.
   *
   * @param eventType - Tipo de evento a escuchar
   * @param handler - Función a ejecutar cuando se reciba el evento
   *
   * @example
   * wsService.on('wake_word_detected', (data) => {
   *   console.log('Wake word:', data);
   * });
   */
  on(eventType: string, handler: EventHandler): void {
    if (!this.eventHandlers.has(eventType)) {
      this.eventHandlers.set(eventType, []);
    }
    this.eventHandlers.get(eventType)!.push(handler);
    console.log('[WebSocket] Registered handler for event:', eventType);
  }

  /**
   * Remueve un listener específico.
   *
   * @param eventType - Tipo de evento
   * @param handler - Handler a remover
   */
  off(eventType: string, handler: EventHandler): void {
    const handlers = this.eventHandlers.get(eventType);
    if (handlers) {
      const index = handlers.indexOf(handler);
      if (index !== -1) {
        handlers.splice(index, 1);
        console.log('[WebSocket] Removed handler for event:', eventType);
      }
    }
  }

  /**
   * Emite un evento a todos los listeners registrados.
   *
   * @param eventType - Tipo de evento
   * @param data - Datos del evento
   */
  private emit(eventType: string, data: any): void {
    const handlers = this.eventHandlers.get(eventType);
    if (handlers && handlers.length > 0) {
      handlers.forEach((handler) => {
        try {
          handler(data);
        } catch (error) {
          console.error(
            `[WebSocket] Error in handler for event '${eventType}':`,
            error
          );
        }
      });
    }
  }

  /**
   * Obtiene el estado actual de la conexión.
   *
   * @returns Estado de la conexión WebSocket
   */
  getReadyState(): number {
    return this.ws?.readyState ?? WebSocket.CLOSED;
  }

  /**
   * Verifica si el WebSocket está conectado.
   *
   * @returns true si está conectado
   */
  isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }
}

// Singleton instance - instancia global única del WebSocketService
export const wsService = new WebSocketService();
