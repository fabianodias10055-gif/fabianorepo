# Snake

Classic Snake with one AI rival, rendered with a built-in 3D-style scene that includes terrain and vegetation.

## Run

Open `index.html` in a browser by double-clicking it.

If your browser is strict about local files, run a local server from this folder instead:

- `python -m http.server`
- `npx serve`

Then navigate to the served `index.html`.

## Manual verification

- Start the game with the Start button, arrow keys, or WASD.
- Confirm Start changes to Pause and Resume during play, and Space toggles pause.
- Confirm both snakes move one grid cell per tick and the player cannot reverse directly into itself.
- Confirm the board renders in a self-contained 3D-style scene with terrain, depth, and vegetation, and resizes cleanly with the window.
- Confirm eating food grows the snake that reached it and increments the matching score.
- Confirm food never appears on top of either snake.
- Confirm collisions with walls, yourself, or the other snake are fatal.
- Confirm Restart resets both scores, both snakes, and food placement.
- Confirm the on-screen arrow buttons work on smaller screens.
