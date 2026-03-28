import {
  GRID_SIZE,
  TICK_MS,
  createInitialState,
  queueDirection,
  stepGame,
} from "./game.js";

const board = document.querySelector("#game-board");
const scoreValue = document.querySelector("#score");
const statusText = document.querySelector("#status");
const startButton = document.querySelector("#start-button");
const restartButton = document.querySelector("#restart-button");
const controlButtons = document.querySelectorAll("[data-direction]");

let state = createInitialState();
let intervalId = null;

const cells = buildBoard(board, GRID_SIZE);
render();

startButton.addEventListener("click", () => {
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
  resetGame();
  startLoop();
});

controlButtons.forEach((button) => {
  button.addEventListener("click", () => {
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

function handleDirectionInput(direction) {
  state = queueDirection(state, direction);
  if (!state.hasStarted && !state.isGameOver) {
    startLoop();
  }
  if (state.isPaused && !state.isGameOver) {
    startLoop();
  }
  render();
}

function startLoop() {
  stopLoop();
  state = {
    ...state,
    isPaused: false,
  };
  intervalId = window.setInterval(() => {
    state = stepGame(state);
    render();

    if (state.isGameOver || !state.food) {
      stopLoop();
    }
  }, TICK_MS);
  render();
}

function stopLoop() {
  if (intervalId !== null) {
    window.clearInterval(intervalId);
    intervalId = null;
  }
}

function pauseLoop() {
  stopLoop();
  state = {
    ...state,
    isPaused: true,
  };
  render();
}

function resetGame() {
  stopLoop();
  state = createInitialState();
  render();
}

function render() {
  const snakeLookup = new Map(
    state.snake.map((segment, index) => [`${segment.x},${segment.y}`, index])
  );
  const foodKey = state.food ? `${state.food.x},${state.food.y}` : null;

  cells.forEach((cell, index) => {
    const x = index % GRID_SIZE;
    const y = Math.floor(index / GRID_SIZE);
    const key = `${x},${y}`;
    const snakeIndex = snakeLookup.get(key);

    cell.className = "cell";

    if (key === foodKey) {
      cell.classList.add("food");
    }

    if (snakeIndex !== undefined) {
      cell.classList.add("snake");
      if (snakeIndex === 0) {
        cell.classList.add("head");
      }
    }
  });

  scoreValue.textContent = String(state.score);
  statusText.textContent = getStatusText();
  startButton.textContent = state.isGameOver
    ? "Play Again"
    : state.isPaused
      ? "Resume"
      : state.hasStarted
        ? "Pause"
        : "Start";
}

function getStatusText() {
  if (state.isGameOver) {
    return "Game over. Press Restart or Play Again.";
  }

  if (state.isPaused) {
    return "Paused. Press Resume or Space to continue.";
  }

  if (!state.hasStarted) {
    return "Press Start or use an arrow key to begin.";
  }

  if (!state.food) {
    return "You filled the board. Restart to play again.";
  }

  return "Collect food and avoid walls or your own tail.";
}

function buildBoard(container, gridSize) {
  const fragment = document.createDocumentFragment();
  const boardCells = [];

  for (let index = 0; index < gridSize * gridSize; index += 1) {
    const cell = document.createElement("div");
    cell.className = "cell";
    cell.setAttribute("role", "gridcell");
    fragment.appendChild(cell);
    boardCells.push(cell);
  }

  container.replaceChildren(fragment);
  return boardCells;
}

function mapKeyToDirection(key) {
  switch (key.toLowerCase()) {
    case " ":
    case "space":
    case "spacebar":
      if (state.hasStarted && !state.isGameOver) {
        if (state.isPaused) {
          startLoop();
        } else {
          pauseLoop();
        }
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
