# Atlas AI — UE5 Setup (No Plugins Required)

## What changed
Fish Audio now returns **WAV** instead of MP3.
UE5 plays WAV natively with `USoundWaveProcedural` — **no plugin install needed**.

---

## Step 1: Copy the C++ files

Replace these files in your UE5 project Source folder:

```
YourUE5Project/
└── Source/
    └── AtlasAI_env/
        ├── AtlasAIComponent.h      ← copy from docs/ue5/
        ├── AtlasAIComponent.cpp    ← copy from docs/ue5/
        └── AtlasAI_env.Build.cs   ← copy from docs/ue5/
```

---

## Step 2: Compile

In UE5 editor: **Tools → Compile** (or Ctrl+Alt+F11)

---

## Step 3: Backend .env

```env
FISH_AUDIO_API_KEY=your_key_here
FISH_AUDIO_VOICE_ID=           # leave blank for default
ATLAS_MODE=game
```

Start backend:
```bash
cd AtlasAI/backend
uvicorn src.main:app --reload --port 8000
```

---

## How it works end-to-end

```
Player presses T in UE5
    ↓
TalkToAtlasWithContext() → JSON with health/enemy/quest/location
    ↓
HTTP POST → localhost:8000/api/game/chat
    ↓
Backend: Claude generates short game response text
    ↓
Backend: Fish Audio TTS → WAV bytes (changed from MP3)
    ↓
Backend: WAV bytes → base64 string in JSON response
    ↓
Response: { response: "Watch your flank!", audio_b64: "...", audio_format: "wav" }
    ↓
UE5: Shows text on screen (cyan)
    ↓
UE5: Decodes base64 → WAV bytes
    ↓
UE5: Parses WAV header → extracts raw PCM audio
    ↓
UE5: Creates USoundWaveProcedural (native, no plugin)
    ↓
UAudioComponent attached to character → plays audio
    ↓
Atlas speaks FROM the character in 3D space ✓
```
