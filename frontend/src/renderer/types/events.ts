/**
 * AtlasAI WebSocket Event Map — STARTER FILE (Session 23 homework)
 *
 * This is 40% done. Your job: finish the TODOs, then retrofit
 * services/websocket.ts and hooks/useWebSocket.ts to use these types.
 * See typescript-study-session-23-atlasai-websocket-live.md for the walkthrough.
 */

// ---------------------------------------------------------------
// Events the BACKEND sends TO the frontend (you listen with .on())
// ---------------------------------------------------------------
export interface ServerEvents {
  // ✅ DONE FOR YOU — study the shape, then copy the pattern.

  // User says "Hey Atlas" → mic icon lights up on screen
  wake_word_detected: { confidence: number; timestamp: number };

  // Backend streams Claude's reply → text appears word-by-word in the chat bubble
  ai_response_chunk: { text: string; done: boolean };

  // ElevenLabs audio arrives → Atlas literally speaks out loud
  tts_audio: { audio_base64: string; format: 'mp3' | 'pcm' };

  // Atlas changes state → the floating bubble changes color/animation
  state_changed: { state: 'idle' | 'listening' | 'thinking' | 'speaking' };

  // 🔲 TODO — you type these. Look at what the backend actually sends.
  ai_response_generated: unknown; // TODO: replace unknown with the real payload shape
  memories_updated: unknown;      // TODO
  tool_screenshot: unknown;       // TODO
  ui_command: unknown;            // TODO
  stop_tts: unknown;              // TODO (hint: might just be `{}` — no payload)
}

// ---------------------------------------------------------------
// Events the FRONTEND sends TO the backend (you call .send())
// ---------------------------------------------------------------
export interface ClientEvents {
  // ✅ DONE FOR YOU
  // User types a message and hits Enter in the chat widget
  chat_message: { text: string; conversation_id?: string };

  // 🔲 TODO
  audio_chunk: unknown;   // TODO: base64 audio from the mic
  audio_command: unknown; // TODO
  ping: unknown;          // TODO (probably {})
  pause: unknown;         // TODO
  resume: unknown;        // TODO
}

// Helper types — these make the generic retrofit possible.
export type ServerEventType = keyof ServerEvents;
export type ClientEventType = keyof ClientEvents;
