// AtlasAI_env.Build.cs
// NO EXTRA PLUGINS NEEDED — only standard UE5 modules

using UnrealBuildTool;

public class AtlasAI_env : ModuleRules
{
    public AtlasAI_env(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

        PublicDependencyModuleNames.AddRange(new string[]
        {
            "Core",
            "CoreUObject",
            "Engine",
            "InputCore",
            "EnhancedInput",

            // Atlas AI — all native UE5, zero external plugins:
            "HTTP",             // HTTP POST to FastAPI backend
            "Json",             // FJsonObject, TJsonReader
            "JsonUtilities",    // FJsonObjectConverter helpers
        });

        PrivateDependencyModuleNames.AddRange(new string[] { });
    }
}
