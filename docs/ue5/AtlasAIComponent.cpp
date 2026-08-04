// AtlasAIComponent.cpp
// Atlas AI — UE5 Actor Component Implementation
//
// NO PLUGINS REQUIRED — 100% native UE5.
//
// Full flow when player presses T:
//   1. Build JSON with message + game state
//   2. HTTP POST → Python backend (/api/game/chat)
//   3. Backend: Claude generates text + Fish Audio returns WAV bytes
//   4. Backend: WAV bytes → base64 → JSON response
//   5. UE5: Show text on screen
//   6. UE5: Decode base64 → WAV bytes → parse WAV header → raw PCM
//   7. UE5: Feed PCM into USoundWaveProcedural → play through UAudioComponent
//   → Atlas speaks FROM inside the game character, in 3D space

#include "AtlasAIComponent.h"
#include "HttpModule.h"
#include "Interfaces/IHttpRequest.h"
#include "Interfaces/IHttpResponse.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Misc/Base64.h"
#include "Sound/SoundWaveProcedural.h"
#include "Engine/Engine.h"
#include "GameFramework/Actor.h"


// ── Constructor ───────────────────────────────────────────────────────────────

UAtlasAIComponent::UAtlasAIComponent()
{
    // We don't need Tick — all network calls are async
    PrimaryComponentTick.bCanEverTick = false;
}


// ── BeginPlay ─────────────────────────────────────────────────────────────────

void UAtlasAIComponent::BeginPlay()
{
    Super::BeginPlay();

    // Create an AudioComponent and attach it to the character
    // This makes Atlas's voice come FROM the character in 3D space
    AActor* Owner = GetOwner();
    if (Owner)
    {
        AudioComponent = NewObject<UAudioComponent>(Owner, TEXT("AtlasVoice"));
        AudioComponent->RegisterComponent();
        AudioComponent->AttachToComponent(
            Owner->GetRootComponent(),
            FAttachmentTransformRules::KeepRelativeTransform
        );
        AudioComponent->bAutoActivate = false;
        AudioComponent->SetVolumeMultiplier(VoiceVolume);

        UE_LOG(LogTemp, Log, TEXT("[AtlasAI] AudioComponent attached to %s"), *Owner->GetName());
    }
}


// ── Public API ────────────────────────────────────────────────────────────────

void UAtlasAIComponent::TalkToAtlas(FString Message)
{
    FString JsonBody = FString::Printf(
        TEXT("{\"message\":\"%s\",\"language\":\"%s\"}"),
        *Message.Replace(TEXT("\""), TEXT("\\\"")),
        *Language
    );
    SendRequest(JsonBody);
}

void UAtlasAIComponent::TalkToAtlasWithContext(
    FString Message,
    int32   Health,
    int32   MaxHealth,
    FString Enemy,
    FString Quest,
    FString Location)
{
    FString JsonBody = FString::Printf(
        TEXT("{\"message\":\"%s\",\"language\":\"%s\",\"health\":%d,\"max_health\":%d,\"enemy\":\"%s\",\"quest\":\"%s\",\"location\":\"%s\"}"),
        *Message.Replace(TEXT("\""), TEXT("\\\""), ESearchCase::CaseSensitive),
        *Language,
        Health,
        MaxHealth,
        *Enemy.Replace(TEXT("\""), TEXT("\\\""), ESearchCase::CaseSensitive),
        *Quest.Replace(TEXT("\""), TEXT("\\\""), ESearchCase::CaseSensitive),
        *Location.Replace(TEXT("\""), TEXT("\\\""), ESearchCase::CaseSensitive)
    );
    SendRequest(JsonBody);
}


// ── HTTP Request ──────────────────────────────────────────────────────────────

void UAtlasAIComponent::SendRequest(const FString& JsonBody)
{
    TSharedRef<IHttpRequest, ESPMode::ThreadSafe> HttpRequest =
        FHttpModule::Get().CreateRequest();

    HttpRequest->SetURL(AtlasBackendURL);
    HttpRequest->SetVerb(TEXT("POST"));
    HttpRequest->SetHeader(TEXT("Content-Type"), TEXT("application/json"));
    HttpRequest->SetContentAsString(JsonBody);
    HttpRequest->OnProcessRequestComplete().BindUObject(
        this, &UAtlasAIComponent::OnAtlasResponse
    );
    HttpRequest->ProcessRequest();

    UE_LOG(LogTemp, Log, TEXT("[AtlasAI] Request sent to %s"), *AtlasBackendURL);
}


// ── HTTP Response ─────────────────────────────────────────────────────────────

void UAtlasAIComponent::OnAtlasResponse(
    FHttpRequestPtr  Request,
    FHttpResponsePtr Response,
    bool             bWasSuccessful)
{
    // Guard: connection failed
    if (!bWasSuccessful || !Response.IsValid())
    {
        UE_LOG(LogTemp, Error, TEXT("[AtlasAI] HTTP failed — backend running?"));
        if (GEngine)
        {
            GEngine->AddOnScreenDebugMessage(-1, 5.f, FColor::Red,
                TEXT("[Atlas] ERROR: Can't reach backend. Is it running?"));
        }
        return;
    }

    if (Response->GetResponseCode() != 200)
    {
        UE_LOG(LogTemp, Error, TEXT("[AtlasAI] HTTP %d: %s"),
            Response->GetResponseCode(), *Response->GetContentAsString());
        return;
    }

    // Parse JSON: { "response": "...", "audio_b64": "...", "audio_format": "wav" }
    TSharedPtr<FJsonObject> JsonObject;
    TSharedRef<TJsonReader<>> Reader =
        TJsonReaderFactory<>::Create(Response->GetContentAsString());

    if (!FJsonSerializer::Deserialize(Reader, JsonObject) || !JsonObject.IsValid())
    {
        UE_LOG(LogTemp, Error, TEXT("[AtlasAI] JSON parse failed"));
        return;
    }

    // ── 1. Show text response on screen ──────────────────────────────────────
    FString ResponseText;
    if (JsonObject->TryGetStringField(TEXT("response"), ResponseText))
    {
        UE_LOG(LogTemp, Log, TEXT("[AtlasAI] Atlas: %s"), *ResponseText);
        if (GEngine)
        {
            GEngine->AddOnScreenDebugMessage(-1, 6.f, FColor::Cyan,
                FString::Printf(TEXT("Atlas: %s"), *ResponseText));
        }
    }

    // ── 2. Play audio ─────────────────────────────────────────────────────────
    FString AudioBase64;
    if (JsonObject->TryGetStringField(TEXT("audio_b64"), AudioBase64) && !AudioBase64.IsEmpty())
    {
        UE_LOG(LogTemp, Log, TEXT("[AtlasAI] Audio received (%d chars b64)"), AudioBase64.Len());
        PlayWavFromBase64(AudioBase64);
    }
    else
    {
        UE_LOG(LogTemp, Warning,
            TEXT("[AtlasAI] No audio in response. Set FISH_AUDIO_API_KEY in .env to enable voice."));
    }
}


// ── WAV Audio Playback ────────────────────────────────────────────────────────
//
// WAV file layout (standard PCM):
//
//   Offset  Size  Value
//   0       4     "RIFF"
//   4       4     file size - 8
//   8       4     "WAVE"
//   12      4     "fmt "
//   16      4     16 (chunk size for PCM)
//   20      2     1  (PCM audio format)
//   22      2     num channels  (1=mono, 2=stereo)
//   24      4     sample rate   (e.g. 44100)
//   28      4     byte rate
//   32      2     block align
//   34      2     bits per sample (16 = standard)
//   36      4     "data"
//   40      4     PCM data size in bytes
//   44      ...   raw PCM audio data
//
// USoundWaveProcedural takes the raw PCM bytes + sample rate + channels.
// No plugin, no files written to disk, no external dependencies.

void UAtlasAIComponent::PlayWavFromBase64(const FString& AudioBase64)
{
    if (!AudioComponent)
    {
        UE_LOG(LogTemp, Error, TEXT("[AtlasAI] AudioComponent null"));
        return;
    }

    // ── Step 1: base64 → raw WAV bytes ────────────────────────────────────────
    TArray<uint8> WavBytes;
    if (!FBase64::Decode(AudioBase64, WavBytes))
    {
        UE_LOG(LogTemp, Error, TEXT("[AtlasAI] Base64 decode failed"));
        return;
    }

    // ── Step 2: Validate WAV header ───────────────────────────────────────────
    // Minimum valid WAV file is 44 bytes (header) + at least 1 byte of audio
    if (WavBytes.Num() < 44)
    {
        UE_LOG(LogTemp, Error, TEXT("[AtlasAI] WAV too small: %d bytes"), WavBytes.Num());
        return;
    }

    // Check "RIFF" and "WAVE" magic bytes
    if (WavBytes[0] != 'R' || WavBytes[1] != 'I' || WavBytes[2] != 'F' || WavBytes[3] != 'F')
    {
        UE_LOG(LogTemp, Error, TEXT("[AtlasAI] Not a valid WAV file (missing RIFF header)"));
        return;
    }

    // ── Step 3: Read audio parameters from WAV header ─────────────────────────
    // All values are little-endian in the WAV spec
    auto ReadUInt16 = [&](int32 Offset) -> uint16
    {
        return (uint16)(WavBytes[Offset]) | ((uint16)(WavBytes[Offset + 1]) << 8);
    };
    auto ReadUInt32 = [&](int32 Offset) -> uint32
    {
        return (uint32)(WavBytes[Offset])
             | ((uint32)(WavBytes[Offset + 1]) << 8)
             | ((uint32)(WavBytes[Offset + 2]) << 16)
             | ((uint32)(WavBytes[Offset + 3]) << 24);
    };

    uint16 NumChannels   = ReadUInt16(22);   // 1 = mono, 2 = stereo
    uint32 SampleRate    = ReadUInt32(24);   // e.g. 44100 or 22050
    uint16 BitsPerSample = ReadUInt16(34);   // 16 for standard PCM

    // ── Step 4: Find the "data" chunk (search instead of hardcoding offset 36)─
    // Some WAV files have extra metadata chunks before "data"
    int32 DataOffset = -1;
    int32 DataSize   = 0;

    for (int32 i = 12; i < WavBytes.Num() - 8; i++)
    {
        if (WavBytes[i]   == 'd' && WavBytes[i+1] == 'a' &&
            WavBytes[i+2] == 't' && WavBytes[i+3] == 'a')
        {
            DataSize   = (int32)ReadUInt32(i + 4);
            DataOffset = i + 8;
            break;
        }
    }

    if (DataOffset < 0 || DataSize <= 0)
    {
        UE_LOG(LogTemp, Error, TEXT("[AtlasAI] No 'data' chunk found in WAV"));
        return;
    }

    // Make sure the data doesn't run past end of file
    int32 ActualDataSize = FMath::Min(DataSize, WavBytes.Num() - DataOffset);

    UE_LOG(LogTemp, Log,
        TEXT("[AtlasAI] WAV: %d Hz, %d ch, %d-bit, %d PCM bytes"),
        SampleRate, NumChannels, BitsPerSample, ActualDataSize);

    // ── Step 5: Create USoundWaveProcedural ───────────────────────────────────
    // This is UE5's built-in class for playing raw audio data at runtime.
    // RF_Transient = don't save to disk, just exists in memory during play.
    USoundWaveProcedural* SoundWave = NewObject<USoundWaveProcedural>(
        GetTransientPackage(), NAME_None, RF_Transient
    );

    SoundWave->SetSampleRate(SampleRate);
    SoundWave->NumChannels = NumChannels;
    SoundWave->SoundGroup  = SOUNDGROUP_Default;
    SoundWave->bLooping    = false;

    // Calculate duration from PCM data size
    // Duration = bytes / (sample_rate * channels * bytes_per_sample)
    int32 BytesPerSample = BitsPerSample / 8;
    SoundWave->Duration  = (float)ActualDataSize /
                           (float)(SampleRate * NumChannels * BytesPerSample);

    // ── Step 6: Feed PCM data into the sound wave ─────────────────────────────
    // QueueAudio takes a raw pointer to the PCM bytes
    SoundWave->QueueAudio(WavBytes.GetData() + DataOffset, ActualDataSize);

    // ── Step 7: Play through the character's AudioComponent ───────────────────
    // Stop any currently playing Atlas audio first
    if (AudioComponent->IsPlaying())
    {
        AudioComponent->Stop();
    }

    AudioComponent->SetSound(SoundWave);
    AudioComponent->Play();

    UE_LOG(LogTemp, Log,
        TEXT("[AtlasAI] Playing %.2f seconds of audio through character"),
        SoundWave->Duration);
}
