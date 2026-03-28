export const GRID_SIZE = 16;
export const INITIAL_DIRECTION = "right";
export const TICK_MS = 140;

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

export function createInitialState(random = Math.random) {
  const snake = [
    { x: 2, y: 8 },
    { x: 1, y: 8 },
    { x: 0, y: 8 },
  ];

  return {
    gridSize: GRID_SIZE,
    snake,
    direction: INITIAL_DIRECTION,
    queuedDirection: INITIAL_DIRECTION,
    food: placeFood(snake, GRID_SIZE, random),
    score: 0,
    isGameOver: false,
    hasStarted: false,
    isPaused: false,
  };
}

export function queueDirection(state, nextDirection) {
  if (!DIRECTION_VECTORS[nextDirection]) {
    return state;
  }

  const blockedDirection = OPPOSITE_DIRECTIONS[state.direction];
  if (nextDirection === blockedDirection && state.snake.length > 1) {
    return state;
  }

  return {
    ...state,
    queuedDirection: nextDirection,
  };
}

export function stepGame(state, random = Math.random) {
  if (state.isGameOver) {
    return state;
  }

  const direction = state.queuedDirection;
  const vector = DIRECTION_VECTORS[direction];
  const head = state.snake[0];
  const nextHead = { x: head.x + vector.x, y: head.y + vector.y };
  const willGrow = positionsEqual(nextHead, state.food);
  const bodyToCheck = willGrow ? state.snake : state.snake.slice(0, -1);
  const hitsWall = isOutOfBounds(nextHead, state.gridSize);
  const hitsSelf = bodyToCheck.some((segment) => positionsEqual(segment, nextHead));

  if (hitsWall || hitsSelf) {
    return {
      ...state,
      direction,
      hasStarted: true,
      isGameOver: true,
      isPaused: false,
    };
  }

  const nextSnake = [nextHead, ...state.snake];
  if (!willGrow) {
    nextSnake.pop();
  }

  return {
    ...state,
    snake: nextSnake,
    direction,
    queuedDirection: direction,
    food: willGrow ? placeFood(nextSnake, state.gridSize, random) : state.food,
    score: willGrow ? state.score + 1 : state.score,
    hasStarted: true,
    isPaused: false,
  };
}

export function placeFood(snake, gridSize, random = Math.random) {
  const occupied = new Set(snake.map(toKey));
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

  const index = Math.floor(random() * available.length);
  return available[index];
}

export function positionsEqual(a, b) {
  return Boolean(a && b) && a.x === b.x && a.y === b.y;
}

function toKey(position) {
  return `${position.x},${position.y}`;
}

function isOutOfBounds(position, gridSize) {
  return (
    position.x < 0 ||
    position.y < 0 ||
    position.x >= gridSize ||
    position.y >= gridSize
  );
}
