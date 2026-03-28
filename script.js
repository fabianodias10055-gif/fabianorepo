const GRID_SIZE = 32;
const INITIAL_DIRECTION = "right";
const AI_INITIAL_DIRECTION = "left";
const TICK_MS = 120;
const SNAKE_IDS = ["player", "ai"];

const DIRECTION_VECTORS = {
  up: { x: 0, y: -1 },
  down: { x: 0, y: 1 },
  left: { x: -1, y: 0 },
  right: { x: 1, y: 0 },
};

const OPPOSITE_DIRECTIONS = {
  up: "down",
  down: "up",
  left: "right",
  right: "left",
};

const stage = document.querySelector("#game-board");
const stageContext = stage.getContext("2d");
const playerScoreValue = document.querySelector("#player-score");
const aiScoreValue = document.querySelector("#ai-score");
const statusText = document.querySelector("#status");
const startButton = document.querySelector("#start-button");
const restartButton = document.querySelector("#restart-button");
const controlButtons = document.querySelectorAll("[data-direction]");

let state = createInitialState();
let intervalId = null;
let audioContext = null;
let rendererState = null;
const vegetation = buildVegetation();

resizeStage();
renderUi();

window.addEventListener("resize", () => {
  resizeStage();
  renderUi();
});

startButton.addEventListener("click", () => {
  ensureAudioContext();

  if (state.isGameOver) {
    resetGame();
    startLoop();
    return;
  }

  if (!state.hasStarted || state.isPaused) {
    startLoop();
    return;
  }

  pauseLoop();
});

restartButton.addEventListener("click", () => {
  ensureAudioContext();
  resetGame();
  startLoop();
});

controlButtons.forEach((button) => {
  button.addEventListener("click", () => {
    ensureAudioContext();
    handleDirectionInput(button.dataset.direction);
  });
});

window.addEventListener("keydown", (event) => {
  const direction = mapKeyToDirection(event.key);
  if (!direction) {
    return;
  }

  event.preventDefault();
  handleDirectionInput(direction);
});

function createInitialState(random = Math.random) {
  const snakes = {
    player: createSnake([{ x: 4, y: 16 }, { x: 3, y: 16 }, { x: 2, y: 16 }], INITIAL_DIRECTION),
    ai: createSnake([{ x: 27, y: 16 }, { x: 28, y: 16 }, { x: 29, y: 16 }], AI_INITIAL_DIRECTION),
  };

  return {
    gridSize: GRID_SIZE,
    snakes,
    food: placeFood(getAllSegments(snakes), GRID_SIZE, random),
    isGameOver: false,
    hasStarted: false,
    isPaused: false,
    winner: null,
  };
}

function createSnake(segments, direction) {
  return { segments, direction, queuedDirection: direction, score: 0, alive: true };
}

function queuePlayerDirection(currentState, nextDirection) {
  return {
    ...currentState,
    snakes: {
      ...currentState.snakes,
      player: queueSnakeDirection(currentState.snakes.player, nextDirection),
    },
  };
}

function queueSnakeDirection(snake, nextDirection) {
  if (!snake.alive || !DIRECTION_VECTORS[nextDirection]) {
    return snake;
  }

  if (nextDirection === OPPOSITE_DIRECTIONS[snake.direction] && snake.segments.length > 1) {
    return snake;
  }

  return { ...snake, queuedDirection: nextDirection };
}

function stepGame(currentState, random = Math.random) {
  if (currentState.isGameOver) {
    return currentState;
  }

  let snakes = { ...currentState.snakes, ai: chooseAiDirection(currentState) };
  const occupiedAtStart = getOccupiedMap(snakes);
  const moves = {};

  SNAKE_IDS.forEach((snakeId) => {
    const snake = snakes[snakeId];
    if (!snake.alive) {
      moves[snakeId] = null;
      return;
    }

    const vector = DIRECTION_VECTORS[snake.queuedDirection];
    const head = snake.segments[0];
    const nextHead = { x: head.x + vector.x, y: head.y + vector.y };
    moves[snakeId] = { nextHead, willGrow: positionsEqual(nextHead, currentState.food) };
  });

  const headCounts = new Map();
  SNAKE_IDS.forEach((snakeId) => {
    if (!moves[snakeId]) {
      return;
    }
    const key = toKey(moves[snakeId].nextHead);
    headCounts.set(key, (headCounts.get(key) || 0) + 1);
  });

  snakes = { ...snakes };
  let foodWasEaten = false;

  SNAKE_IDS.forEach((snakeId) => {
    const snake = snakes[snakeId];
    const move = moves[snakeId];
    if (!move) {
      return;
    }

    const hitsWall = isOutOfBounds(move.nextHead, currentState.gridSize);
    const hitsHead = headCounts.get(toKey(move.nextHead)) > 1;
    const hitsSnake = collidesWithSnakes(move.nextHead, snakeId, snakes, occupiedAtStart, moves);

    if (hitsWall || hitsHead || hitsSnake) {
      snakes[snakeId] = { ...snake, direction: snake.queuedDirection, alive: false };
      return;
    }

    const nextSegments = [move.nextHead, ...snake.segments];
    if (!move.willGrow) {
      nextSegments.pop();
    } else {
      foodWasEaten = true;
    }

    snakes[snakeId] = {
      ...snake,
      segments: nextSegments,
      direction: snake.queuedDirection,
      queuedDirection: snake.queuedDirection,
      score: snake.score + (move.willGrow ? 1 : 0),
      alive: true,
    };
  });

  const playerAlive = snakes.player.alive;
  const aiAlive = snakes.ai.alive;
  const winner = !playerAlive && !aiAlive ? "draw" : !playerAlive ? "ai" : !aiAlive ? "player" : null;
  const food = winner ? currentState.food : foodWasEaten ? placeFood(getAllSegments(snakes), currentState.gridSize, random) : currentState.food;

  return {
    ...currentState,
    snakes,
    food,
    isGameOver: winner !== null,
    hasStarted: true,
    isPaused: false,
    winner,
  };
}

function chooseAiDirection(currentState) {
  const ai = currentState.snakes.ai;
  if (!ai.alive) {
    return ai;
  }

  return queueSnakeDirection(ai, pickBestAiDirection(currentState));
}

function pickBestAiDirection(currentState) {
  const ai = currentState.snakes.ai;
  const head = ai.segments[0];
  const occupied = getOccupiedMap(currentState.snakes);
  const options = Object.keys(DIRECTION_VECTORS).filter((direction) => {
    if (ai.segments.length > 1 && direction === OPPOSITE_DIRECTIONS[ai.direction]) {
      return false;
    }
    const nextHead = addVector(head, DIRECTION_VECTORS[direction]);
    return !wouldCollide(nextHead, "ai", currentState, occupied);
  });

  if (options.length === 0) {
    return ai.direction;
  }

  const scored = options.map((direction) => {
    const simulation = simulateAiMove(currentState, direction);
    const pathLength = findShortestPathLength(simulation.aiHead, currentState.food, currentState.gridSize, simulation.blocked);
    const reachableArea = countReachableArea(simulation.aiHead, currentState.gridSize, simulation.blocked);
    const playerDistance = manhattanDistance(simulation.aiHead, currentState.snakes.player.segments[0]);
    const foodScore = pathLength === null ? -2000 : 2000 - pathLength * 25;
    return {
      direction,
      pathLength,
      score: foodScore + reachableArea * 4 + Math.min(playerDistance, 12) + (direction === ai.direction ? 3 : 0),
    };
  });

  scored.sort((left, right) => {
    if (right.score !== left.score) {
      return right.score - left.score;
    }
    return (left.pathLength ?? Number.MAX_SAFE_INTEGER) - (right.pathLength ?? Number.MAX_SAFE_INTEGER);
  });

  return scored[0].direction;
}

function simulateAiMove(currentState, direction) {
  const ai = currentState.snakes.ai;
  const player = currentState.snakes.player;
  const aiHead = addVector(ai.segments[0], DIRECTION_VECTORS[direction]);
  const aiWillGrow = positionsEqual(aiHead, currentState.food);
  const nextAiSegments = [aiHead, ...ai.segments];
  if (!aiWillGrow) {
    nextAiSegments.pop();
  }

  const playerHead = addVector(player.segments[0], DIRECTION_VECTORS[player.queuedDirection]);
  const playerWillGrow = positionsEqual(playerHead, currentState.food);
  const nextPlayerSegments = [playerHead, ...player.segments];
  if (!playerWillGrow) {
    nextPlayerSegments.pop();
  }

  const blocked = new Set([
    ...nextAiSegments.slice(1).map(toKey),
    ...nextPlayerSegments.map(toKey),
  ]);
  blocked.delete(toKey(aiHead));
  return { aiHead, blocked };
}

function findShortestPathLength(start, target, gridSize, blocked) {
  if (!target) {
    return null;
  }
  if (positionsEqual(start, target)) {
    return 0;
  }

  const queue = [{ position: start, distance: 0 }];
  const visited = new Set([toKey(start)]);

  while (queue.length > 0) {
    const current = queue.shift();
    for (const vector of Object.values(DIRECTION_VECTORS)) {
      const next = addVector(current.position, vector);
      const nextKey = toKey(next);
      if (isOutOfBounds(next, gridSize) || blocked.has(nextKey) || visited.has(nextKey)) {
        continue;
      }
      if (positionsEqual(next, target)) {
        return current.distance + 1;
      }
      visited.add(nextKey);
      queue.push({ position: next, distance: current.distance + 1 });
    }
  }

  return null;
}

function countReachableArea(start, gridSize, blocked) {
  const queue = [start];
  const visited = new Set([toKey(start)]);
  let area = 0;

  while (queue.length > 0) {
    const current = queue.shift();
    area += 1;
    for (const vector of Object.values(DIRECTION_VECTORS)) {
      const next = addVector(current, vector);
      const nextKey = toKey(next);
      if (isOutOfBounds(next, gridSize) || blocked.has(nextKey) || visited.has(nextKey)) {
        continue;
      }
      visited.add(nextKey);
      queue.push(next);
    }
  }

  return area;
}

function wouldCollide(nextHead, snakeId, currentState, occupied) {
  if (isOutOfBounds(nextHead, currentState.gridSize)) {
    return true;
  }

  const snake = currentState.snakes[snakeId];
  const willGrow = positionsEqual(nextHead, currentState.food);
  const selfTailKey = toKey(snake.segments[snake.segments.length - 1]);
  if (!occupied.has(toKey(nextHead))) {
    return false;
  }
  if (!willGrow && toKey(nextHead) === selfTailKey) {
    return false;
  }

  const otherSnake = snakeId === "player" ? currentState.snakes.ai : currentState.snakes.player;
  const otherTailKey = otherSnake.alive ? toKey(otherSnake.segments[otherSnake.segments.length - 1]) : null;
  return willGrow || toKey(nextHead) !== otherTailKey;
}

function collidesWithSnakes(nextHead, snakeId, snakes, occupiedAtStart, moves) {
  const nextKey = toKey(nextHead);
  if (!occupiedAtStart.has(nextKey)) {
    return false;
  }

  return SNAKE_IDS.some((candidateId) => {
    const candidate = snakes[candidateId];
    if (!candidate.alive) {
      return false;
    }
    const tailKey = toKey(candidate.segments[candidate.segments.length - 1]);
    const tailCanMoveAway = moves[candidateId] && !moves[candidateId].willGrow;
    if (tailCanMoveAway && nextKey === tailKey) {
      return false;
    }
    return candidate.segments.some((segment) => toKey(segment) === nextKey);
  });
}

function placeFood(occupiedSegments, gridSize, random = Math.random) {
  const occupied = new Set(occupiedSegments.map(toKey));
  const available = [];
  for (let y = 0; y < gridSize; y += 1) {
    for (let x = 0; x < gridSize; x += 1) {
      const position = { x, y };
      if (!occupied.has(toKey(position))) {
        available.push(position);
      }
    }
  }
  if (available.length === 0) {
    return null;
  }
  return available[Math.floor(random() * available.length)];
}

function getAllSegments(snakes) {
  return SNAKE_IDS.flatMap((snakeId) => snakes[snakeId].segments);
}

function getOccupiedMap(snakes) {
  return new Set(getAllSegments(snakes).map(toKey));
}

function positionsEqual(a, b) {
  return Boolean(a && b) && a.x === b.x && a.y === b.y;
}

function addVector(position, vector) {
  return { x: position.x + vector.x, y: position.y + vector.y };
}

function manhattanDistance(left, right) {
  return Math.abs(left.x - right.x) + Math.abs(left.y - right.y);
}

function toKey(position) {
  return `${position.x},${position.y}`;
}

function isOutOfBounds(position, gridSize) {
  return position.x < 0 || position.y < 0 || position.x >= gridSize || position.y >= gridSize;
}

function handleDirectionInput(direction) {
  state = queuePlayerDirection(state, direction);
  if (!state.hasStarted && !state.isGameOver) {
    startLoop();
  }
  if (state.isPaused && !state.isGameOver) {
    startLoop();
  }
  renderUi();
}

function startLoop() {
  stopLoop();
  state = { ...state, hasStarted: true, isPaused: false };
  renderUi();
  intervalId = window.setInterval(() => {
    const previousPlayerScore = state.snakes.player.score;
    const previousAiScore = state.snakes.ai.score;
    state = stepGame(state);
    if (state.snakes.player.score > previousPlayerScore || state.snakes.ai.score > previousAiScore) {
      playEatSound();
    }
    renderUi();
    if (state.isGameOver || !state.food) {
      stopLoop();
    }
  }, TICK_MS);
}

function stopLoop() {
  if (intervalId !== null) {
    window.clearInterval(intervalId);
    intervalId = null;
  }
}

function pauseLoop() {
  stopLoop();
  state = { ...state, isPaused: true };
  renderUi();
}

function resetGame() {
  stopLoop();
  state = createInitialState();
  renderUi();
}

function renderUi() {
  renderScene();
  playerScoreValue.textContent = String(state.snakes.player.score);
  aiScoreValue.textContent = String(state.snakes.ai.score);
  statusText.textContent = getStatusText();
  startButton.textContent = state.isGameOver ? "Play Again" : state.isPaused ? "Resume" : state.hasStarted ? "Pause" : "Start";
}

function getStatusText() {
  if (state.isGameOver) {
    return state.winner === "player"
      ? "You win. The AI snake crashed first."
      : state.winner === "ai"
        ? "Game over. The AI snake outlasted you."
        : "Draw. Both snakes crashed.";
  }
  if (state.isPaused) {
    return "Paused. Press Resume or Space to continue.";
  }
  if (!state.hasStarted) {
    return "Press Start or move to race the AI snake in 3D.";
  }
  if (!state.food) {
    return "Board filled. Press Restart to play again.";
  }
  return "Race the AI through the 3D arena and avoid collisions.";
}

function mapKeyToDirection(key) {
  switch (key.toLowerCase()) {
    case " ":
    case "space":
    case "spacebar":
      if (state.hasStarted && !state.isGameOver) {
        state.isPaused ? startLoop() : pauseLoop();
      }
      return null;
    case "arrowup":
    case "w":
      return "up";
    case "arrowdown":
    case "s":
      return "down";
    case "arrowleft":
    case "a":
      return "left";
    case "arrowright":
    case "d":
      return "right";
    default:
      return null;
  }
}

function ensureAudioContext() {
  if (!window.AudioContext && !window.webkitAudioContext) {
    return null;
  }
  if (!audioContext) {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    audioContext = new AudioContextClass();
  }
  if (audioContext.state === "suspended") {
    audioContext.resume().catch(() => {});
  }
  return audioContext;
}

function playEatSound() {
  const context = ensureAudioContext();
  if (!context) {
    return;
  }

  const now = context.currentTime;
  const oscillator = context.createOscillator();
  const gainNode = context.createGain();
  oscillator.type = "square";
  oscillator.frequency.setValueAtTime(440, now);
  oscillator.frequency.exponentialRampToValueAtTime(660, now + 0.08);
  gainNode.gain.setValueAtTime(0.001, now);
  gainNode.gain.exponentialRampToValueAtTime(0.08, now + 0.01);
  gainNode.gain.exponentialRampToValueAtTime(0.001, now + 0.14);
  oscillator.connect(gainNode);
  gainNode.connect(context.destination);
  oscillator.start(now);
  oscillator.stop(now + 0.14);
}

function resizeStage() {
  const width = Math.max(320, Math.floor(stage.clientWidth || stage.parentElement.clientWidth));
  const height = Math.max(320, Math.floor(stage.clientHeight || width / 1.45));
  const dpr = window.devicePixelRatio || 1;

  stage.width = Math.floor(width * dpr);
  stage.height = Math.floor(height * dpr);
  stageContext.setTransform(dpr, 0, 0, dpr, 0, 0);

  rendererState = {
    width,
    height,
    tileWidth: Math.min(width / 24, height / 14),
    tileDepth: Math.min(width / 48, height / 28),
    cubeHeight: Math.min(width / 34, height / 18),
    originX: width / 2,
    originY: height * 0.18,
    boardLift: Math.min(width / 15, height / 8.5),
  };
}

function renderScene() {
  const { width, height } = rendererState;
  stageContext.clearRect(0, 0, width, height);

  drawSky();
  drawTerrain();
  drawBoardBase();
  drawVegetation();
  drawGridSurface();
  drawFood();
  drawSnake(state.snakes.ai, {
    top: "#e8cf8c",
    left: "#c99d48",
    right: "#9d7222",
    headTop: "#f5dea0",
    headLeft: "#d0a450",
    headRight: "#8c6116",
  });
  drawSnake(state.snakes.player, {
    top: "#62a96c",
    left: "#3f8248",
    right: "#2c5f33",
    headTop: "#74bf7c",
    headLeft: "#4a9453",
    headRight: "#23532d",
  });
}

function drawSky() {
  const { width, height } = rendererState;
  const gradient = stageContext.createLinearGradient(0, 0, 0, height);
  gradient.addColorStop(0, "#ebf6e5");
  gradient.addColorStop(0.52, "#cfe7c9");
  gradient.addColorStop(1, "#98b690");
  stageContext.fillStyle = gradient;
  stageContext.fillRect(0, 0, width, height);

  stageContext.fillStyle = "rgba(255, 255, 255, 0.3)";
  stageContext.beginPath();
  stageContext.ellipse(width * 0.5, height * 0.12, width * 0.28, height * 0.06, 0, 0, Math.PI * 2);
  stageContext.fill();
}

function drawTerrain() {
  const { width, height } = rendererState;
  const horizon = stageContext.createLinearGradient(0, height * 0.3, 0, height);
  horizon.addColorStop(0, "#a6c496");
  horizon.addColorStop(1, "#7b9873");
  stageContext.fillStyle = horizon;
  stageContext.beginPath();
  stageContext.moveTo(0, height);
  stageContext.lineTo(0, height * 0.58);
  for (let x = 0; x <= width; x += 18) {
    const y = height * 0.57 + Math.sin(x * 0.012) * 12 + Math.cos(x * 0.022) * 6;
    stageContext.lineTo(x, y);
  }
  stageContext.lineTo(width, height);
  stageContext.closePath();
  stageContext.fill();
}

function drawBoardBase() {
  const boardFrontLeft = worldToScreen(-GRID_SIZE / 2 - 1.4, 0, GRID_SIZE / 2 + 1.4);
  const boardFrontRight = worldToScreen(GRID_SIZE / 2 + 1.4, 0, GRID_SIZE / 2 + 1.4);
  const boardBackRight = worldToScreen(GRID_SIZE / 2 + 1.4, 0, -GRID_SIZE / 2 - 1.4);
  const boardBackLeft = worldToScreen(-GRID_SIZE / 2 - 1.4, 0, -GRID_SIZE / 2 - 1.4);
  const heightValue = rendererState.boardLift;

  fillQuad(
    boardBackLeft,
    boardBackRight,
    boardFrontRight,
    boardFrontLeft,
    "#f1e8da"
  );

  fillQuad(
    boardFrontLeft,
    boardFrontRight,
    { x: boardFrontRight.x, y: boardFrontRight.y + heightValue },
    { x: boardFrontLeft.x, y: boardFrontLeft.y + heightValue },
    "#cfb089"
  );

  fillQuad(
    boardBackRight,
    boardFrontRight,
    { x: boardFrontRight.x, y: boardFrontRight.y + heightValue },
    { x: boardBackRight.x, y: boardBackRight.y + heightValue },
    "#b89263"
  );

  stageContext.fillStyle = "rgba(52, 42, 28, 0.12)";
  stageContext.beginPath();
  stageContext.ellipse(
    (boardFrontLeft.x + boardFrontRight.x) / 2,
    boardFrontLeft.y + heightValue + 22,
    (boardFrontRight.x - boardFrontLeft.x) * 0.48,
    28,
    0,
    0,
    Math.PI * 2
  );
  stageContext.fill();
}

function drawGridSurface() {
  for (let y = GRID_SIZE - 1; y >= 0; y -= 1) {
    for (let x = GRID_SIZE - 1; x >= 0; x -= 1) {
      const screen = worldToScreen(x - GRID_SIZE / 2, 0, y - GRID_SIZE / 2);
      const top = screen.y - rendererState.boardLift;
      drawTile(screen.x, top, (x + y) % 2 === 0 ? "#f8f2e9" : "#eee3d2");
    }
  }
}

function drawTile(centerX, centerY, color) {
  const halfW = rendererState.tileWidth / 2;
  const halfD = rendererState.tileDepth / 2;
  stageContext.beginPath();
  stageContext.moveTo(centerX, centerY - halfD);
  stageContext.lineTo(centerX + halfW, centerY);
  stageContext.lineTo(centerX, centerY + halfD);
  stageContext.lineTo(centerX - halfW, centerY);
  stageContext.closePath();
  stageContext.fillStyle = color;
  stageContext.fill();
  stageContext.strokeStyle = "rgba(171, 146, 106, 0.25)";
  stageContext.stroke();
}

function drawVegetation() {
  const items = [...vegetation].sort((left, right) => left.worldZ - right.worldZ);
  items.forEach((item) => {
    const screen = worldToScreen(item.x, 0, item.z);
    if (item.kind === "tree") {
      drawTree(screen.x, screen.y, item.scale, item.tint);
    } else if (item.kind === "rock") {
      drawRock(screen.x, screen.y, item.scale);
    } else if (item.kind === "flower") {
      drawFlowers(screen.x, screen.y, item.scale);
    } else {
      drawGrass(screen.x, screen.y, item.scale);
    }
  });
}

function drawTree(x, y, scale, tint) {
  const trunkH = 22 * scale;
  const trunkW = 8 * scale;
  stageContext.fillStyle = "#75522f";
  stageContext.fillRect(x - trunkW / 2, y - trunkH - 12 * scale, trunkW, trunkH);

  drawCircle(x, y - trunkH - 18 * scale, 16 * scale, tint);
  drawCircle(x - 10 * scale, y - trunkH - 8 * scale, 12 * scale, shadeColor(tint, -0.12));
  drawCircle(x + 11 * scale, y - trunkH - 7 * scale, 11 * scale, shadeColor(tint, 0.08));
}

function drawRock(x, y, scale) {
  stageContext.fillStyle = "#9ca098";
  stageContext.beginPath();
  stageContext.moveTo(x - 12 * scale, y - 6 * scale);
  stageContext.lineTo(x - 5 * scale, y - 12 * scale);
  stageContext.lineTo(x + 8 * scale, y - 10 * scale);
  stageContext.lineTo(x + 13 * scale, y - 2 * scale);
  stageContext.lineTo(x + 8 * scale, y + 4 * scale);
  stageContext.lineTo(x - 8 * scale, y + 5 * scale);
  stageContext.closePath();
  stageContext.fill();
}

function drawFlowers(x, y, scale) {
  drawGrass(x, y, scale * 0.9);
  const colors = ["#f0d76d", "#de728f", "#f1e8ef"];
  colors.forEach((color, index) => {
    drawCircle(x - 8 * scale + index * 7 * scale, y - 10 * scale, 3.2 * scale, color);
  });
}

function drawGrass(x, y, scale) {
  stageContext.strokeStyle = "#5f9245";
  stageContext.lineWidth = Math.max(1, 1.4 * scale);
  for (let index = 0; index < 5; index += 1) {
    stageContext.beginPath();
    stageContext.moveTo(x + (index - 2) * 2 * scale, y);
    stageContext.lineTo(x + (index - 2) * 3 * scale, y - (8 + Math.abs(index - 2) * 2) * scale);
    stageContext.stroke();
  }
}

function drawFood() {
  if (!state.food) {
    return;
  }

  const world = gridCellToWorld(state.food);
  const screen = worldToScreen(world.x, 0, world.z);
  const baseY = screen.y - rendererState.boardLift - 12;

  stageContext.fillStyle = "rgba(126, 53, 38, 0.16)";
  stageContext.beginPath();
  stageContext.ellipse(screen.x, baseY + 18, 10, 5, 0, 0, Math.PI * 2);
  stageContext.fill();

  stageContext.beginPath();
  stageContext.moveTo(screen.x, baseY - 10);
  stageContext.lineTo(screen.x + 10, baseY);
  stageContext.lineTo(screen.x, baseY + 12);
  stageContext.lineTo(screen.x - 10, baseY);
  stageContext.closePath();
  stageContext.fillStyle = "#e05643";
  stageContext.fill();

  stageContext.beginPath();
  stageContext.moveTo(screen.x - 10, baseY);
  stageContext.lineTo(screen.x, baseY + 12);
  stageContext.lineTo(screen.x, baseY + 20);
  stageContext.lineTo(screen.x - 7, baseY + 6);
  stageContext.closePath();
  stageContext.fillStyle = "#bc3f31";
  stageContext.fill();

  stageContext.beginPath();
  stageContext.moveTo(screen.x + 10, baseY);
  stageContext.lineTo(screen.x, baseY + 12);
  stageContext.lineTo(screen.x, baseY + 20);
  stageContext.lineTo(screen.x + 7, baseY + 6);
  stageContext.closePath();
  stageContext.fillStyle = "#8d2a20";
  stageContext.fill();
}

function drawSnake(snake, palette) {
  const ordered = snake.segments
    .map((segment, index) => ({ segment, index }))
    .sort((left, right) => {
      const leftWorld = gridCellToWorld(left.segment);
      const rightWorld = gridCellToWorld(right.segment);
      return leftWorld.z - rightWorld.z;
    });

  ordered.forEach(({ segment, index }) => {
    const world = gridCellToWorld(segment);
    const screen = worldToScreen(world.x, 0, world.z);
    drawCube(
      screen.x,
      screen.y - rendererState.boardLift - rendererState.cubeHeight * 0.52,
      rendererState.tileWidth * 0.66,
      rendererState.tileDepth * 0.86,
      rendererState.cubeHeight * (index === 0 ? 1.15 : 0.98),
      index === 0
        ? { top: palette.headTop, left: palette.headLeft, right: palette.headRight }
        : { top: palette.top, left: palette.left, right: palette.right },
      snake.alive ? 1 : 0.5,
      index === 0
    );
  });
}

function drawCube(centerX, topY, width, depth, height, colors, alpha, withEyes) {
  const halfW = width / 2;
  const halfD = depth / 2;
  const top = { x: centerX, y: topY };
  const right = { x: centerX + halfW, y: topY + halfD };
  const bottom = { x: centerX, y: topY + depth };
  const left = { x: centerX - halfW, y: topY + halfD };

  const topDrop = { x: top.x, y: top.y + height };
  const rightDrop = { x: right.x, y: right.y + height };
  const bottomDrop = { x: bottom.x, y: bottom.y + height };
  const leftDrop = { x: left.x, y: left.y + height };

  stageContext.fillStyle = `rgba(40, 31, 20, ${0.14 * alpha})`;
  stageContext.beginPath();
  stageContext.ellipse(centerX, bottomDrop.y + 6, halfW * 0.72, halfD * 0.82, 0, 0, Math.PI * 2);
  stageContext.fill();

  fillQuad(left, bottom, bottomDrop, leftDrop, applyAlpha(colors.left, alpha));
  fillQuad(right, bottom, bottomDrop, rightDrop, applyAlpha(colors.right, alpha));
  fillDiamond(top, right, bottom, left, applyAlpha(colors.top, alpha));

  if (withEyes) {
    drawCircle(centerX - width * 0.14, topY + depth * 0.45, 2.6, applyAlpha("#f5fff3", alpha));
    drawCircle(centerX + width * 0.14, topY + depth * 0.45, 2.6, applyAlpha("#f5fff3", alpha));
  }
}

function worldToScreen(worldX, worldY, worldZ) {
  return {
    x: rendererState.originX + (worldX - worldZ) * rendererState.tileWidth,
    y: rendererState.originY + (worldX + worldZ) * rendererState.tileDepth - worldY,
  };
}

function gridCellToWorld(cell) {
  return {
    x: cell.x - GRID_SIZE / 2 + 0.5,
    z: cell.y - GRID_SIZE / 2 + 0.5,
  };
}

function fillDiamond(top, right, bottom, left, color) {
  stageContext.beginPath();
  stageContext.moveTo(top.x, top.y);
  stageContext.lineTo(right.x, right.y);
  stageContext.lineTo(bottom.x, bottom.y);
  stageContext.lineTo(left.x, left.y);
  stageContext.closePath();
  stageContext.fillStyle = color;
  stageContext.fill();
}

function fillQuad(a, b, c, d, color) {
  stageContext.beginPath();
  stageContext.moveTo(a.x, a.y);
  stageContext.lineTo(b.x, b.y);
  stageContext.lineTo(c.x, c.y);
  stageContext.lineTo(d.x, d.y);
  stageContext.closePath();
  stageContext.fillStyle = color;
  stageContext.fill();
}

function drawCircle(x, y, radius, color) {
  stageContext.beginPath();
  stageContext.arc(x, y, radius, 0, Math.PI * 2);
  stageContext.fillStyle = color;
  stageContext.fill();
}

function buildVegetation() {
  const rng = createSeededRandom(42);
  const items = [];

  for (let index = 0; index < 180; index += 1) {
    const radius = GRID_SIZE * 0.65 + 2 + rng() * 8;
    const angle = rng() * Math.PI * 2;
    const x = Math.cos(angle) * radius;
    const z = Math.sin(angle) * radius;
    const roll = rng();
    items.push({
      x,
      z,
      worldZ: x + z,
      scale: 0.7 + rng() * 0.8,
      tint: ["#46763a", "#4f8342", "#5d8f4d"][Math.floor(rng() * 3)],
      kind: roll < 0.46 ? "grass" : roll < 0.74 ? "tree" : roll < 0.9 ? "rock" : "flower",
    });
  }

  return items;
}

function createSeededRandom(seed) {
  let current = seed >>> 0;
  return () => {
    current = (current * 1664525 + 1013904223) >>> 0;
    return current / 4294967296;
  };
}

function shadeColor(hex, amount) {
  const normalized = hex.replace("#", "");
  const r = Number.parseInt(normalized.slice(0, 2), 16);
  const g = Number.parseInt(normalized.slice(2, 4), 16);
  const b = Number.parseInt(normalized.slice(4, 6), 16);
  const mix = amount >= 0 ? 255 : 0;
  const ratio = Math.abs(amount);
  return `rgb(${Math.round(r + (mix - r) * ratio)}, ${Math.round(g + (mix - g) * ratio)}, ${Math.round(b + (mix - b) * ratio)})`;
}

function applyAlpha(color, alpha) {
  if (color.startsWith("rgba")) {
    return color;
  }
  if (color.startsWith("rgb")) {
    return color.replace("rgb(", "rgba(").replace(")", `, ${alpha})`);
  }
  const normalized = color.replace("#", "");
  const r = Number.parseInt(normalized.slice(0, 2), 16);
  const g = Number.parseInt(normalized.slice(2, 4), 16);
  const b = Number.parseInt(normalized.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}
