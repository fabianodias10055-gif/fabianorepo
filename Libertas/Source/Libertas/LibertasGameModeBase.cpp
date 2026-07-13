// Copyright Epic Games, Inc. All Rights Reserved.

#include "LibertasGameModeBase.h"
#include "LibertasCharacter.h"

ALibertasGameModeBase::ALibertasGameModeBase()
{
	// Spawn the starter character by default. Point this at a Blueprint
	// subclass (e.g. BP_LibertasCharacter) once you make one so you can assign
	// a mesh, animations, and the Enhanced Input assets in the editor.
	DefaultPawnClass = ALibertasCharacter::StaticClass();
	PrimaryActorTick.bCanEverTick = false;
}
