// AtlasAIComponent.h
// Atlas AI — UE5 Actor Component
//
// NO PLUGINS REQUIRED — uses only native UE5 classes:
//   - FHttpModule       → HTTP POST to FastAPI backend
//   - FJsonObject       → parse JSON response
//   - FBase64           → decode audio_b64 string
//   - USoundWaveProcedural → play raw PCM audio from WAV bytes
//   - UAudioComponent   → attached to character, plays audio in 3D space

#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "Components/AudioComponent.h"
#include "HttpModule.h"
#include "Interfaces/IHttpRequest.h"
#include "Interfaces/IHttpResponse.h"
#include "Sound/SoundWaveProcedural.h"

#include "AtlasAIComponent.generated.h"


UCLASS(ClassGroup=(Custom), meta=(BlueprintSpawnableComponent))
class ATLASAI_ENV_API UAtlasAIComponent : public UActorComponent
{
    GENERATED_BODY()

public:
    UAtlasAIComponent();

protected:
    virtual void BeginPlay() override;

public:
    // ── Blueprint-callable ───────────────────────────────────────────────────

    // Simple call — just the player's message
    UFUNCTION(BlueprintCallable, Category = "AtlasAI")
    void TalkToAtlas(FString Message);

    // Full call — message + live game state so Atlas reacts in context
    UFUNCTION(BlueprintCallable, Category = "AtlasAI")
    void TalkToAtlasWithContext(
        FString Message,
        int32   Health,
        int32   MaxHealth,
        FString Enemy,
        FString Quest,
        FString Location
    );

    // ── Configurable in Blueprint / Editor ───────────────────────────────────

    // URL of the FastAPI backend (change to Railway URL in production)
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "AtlasAI")
    FString AtlasBackendURL = TEXT("http://localhost:8000/api/game/chat");

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "AtlasAI")
    FString Language = TEXT("en");

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "AtlasAI",
              meta = (ClampMin = "0.0", ClampMax = "2.0"))
    float VoiceVolume = 1.0f;

private:
    void SendRequest(const FString& JsonBody);

    void OnAtlasResponse(
        FHttpRequestPtr  Request,
        FHttpResponsePtr Response,
        bool             bWasSuccessful
    );

    // Parses WAV bytes → creates USoundWaveProcedural → plays through AudioComponent
    void PlayWavFromBase64(const FString& AudioBase64);

    // The audio component attached to the character — Atlas speaks through this
    UPROPERTY()
    UAudioComponent* AudioComponent;
};
