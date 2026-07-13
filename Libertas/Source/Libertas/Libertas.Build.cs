// Copyright Epic Games, Inc. All Rights Reserved.

using UnrealBuildTool;

public class Libertas : ModuleRules
{
	public Libertas(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

		PublicDependencyModuleNames.AddRange(new string[]
		{
			"Core",
			"CoreUObject",
			"Engine",
			"InputCore",
			"EnhancedInput"
		});

		PrivateDependencyModuleNames.AddRange(new string[] { });

		// Uncomment if you use Slate UI
		// PrivateDependencyModuleNames.AddRange(new string[] { "Slate", "SlateCore" });
	}
}
