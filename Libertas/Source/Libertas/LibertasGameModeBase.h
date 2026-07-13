// Copyright Epic Games, Inc. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "LibertasGameModeBase.generated.h"

/**
 * Default game mode for Libertas. Extend this (or subclass it in Blueprint)
 * to set your default pawn, player controller, HUD, etc.
 */
UCLASS()
class LIBERTAS_API ALibertasGameModeBase : public AGameModeBase
{
	GENERATED_BODY()

public:
	ALibertasGameModeBase();
};
