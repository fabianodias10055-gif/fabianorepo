// Copyright Epic Games, Inc. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "InputActionValue.h"
#include "LibertasCharacter.generated.h"

class USpringArmComponent;
class UCameraComponent;
class UInputMappingContext;
class UInputAction;

/**
 * Starter third-person character for Libertas.
 *
 * Comes with a camera boom + follow camera and Enhanced Input handlers for
 * move / look / jump. The Input Mapping Context and Input Actions are exposed
 * as EditAnywhere properties: create those assets in the editor (see the
 * README) and assign them here, or on a Blueprint subclass, to drive input.
 */
UCLASS()
class LIBERTAS_API ALibertasCharacter : public ACharacter
{
	GENERATED_BODY()

public:
	ALibertasCharacter();

protected:
	virtual void BeginPlay() override;
	virtual void SetupPlayerInputComponent(class UInputComponent* PlayerInputComponent) override;

	/** Spring arm that positions the camera behind the character. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Camera", meta = (AllowPrivateAccess = "true"))
	USpringArmComponent* CameraBoom;

	/** Camera that follows the character. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Camera", meta = (AllowPrivateAccess = "true"))
	UCameraComponent* FollowCamera;

	/** Input Mapping Context added for this character's player. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Input")
	UInputMappingContext* DefaultMappingContext;

	/** Move action (expects a 2D axis: X = right/left, Y = forward/back). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Input")
	UInputAction* MoveAction;

	/** Look action (expects a 2D axis: X = yaw, Y = pitch). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Input")
	UInputAction* LookAction;

	/** Jump action (a simple button). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Input")
	UInputAction* JumpAction;

	/** Called from the Move input action. */
	void Move(const FInputActionValue& Value);

	/** Called from the Look input action. */
	void Look(const FInputActionValue& Value);
};
