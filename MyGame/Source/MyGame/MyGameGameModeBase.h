// Copyright Epic Games, Inc. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "MyGameGameModeBase.generated.h"

/**
 * Default game mode for MyGame. Extend this (or subclass it in Blueprint)
 * to set your default pawn, player controller, HUD, etc.
 */
UCLASS()
class MYGAME_API AMyGameGameModeBase : public AGameModeBase
{
	GENERATED_BODY()

public:
	AMyGameGameModeBase();
};
