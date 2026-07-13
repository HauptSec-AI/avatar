# Background texture

The visitor page has a subtle HUD-style background texture (the admin dashboard does not). The mark **colour follows the theme** (`--grid-line` in `tokens.css`: a cool tint on dark, a navy tint on light), so any variation works in both modes.

## How it's built (current)

- `frontend/public/components.css`'s `.hud-grid` draws a plain 44px line grid directly, using `--grid-line`:
  ```css
  .hud-grid {
    background-image:
      linear-gradient(var(--grid-line) 1px, transparent 1px),
      linear-gradient(90deg, var(--grid-line) 1px, transparent 1px);
    background-size: 44px 44px;
  }
  ```
- This is what actually ships today. There is no `--grid-mark` token in `tokens.css`, and no `.hud-grid::before` mask overlay — an earlier draft of this doc described a masked-shape variant (rings) as current, but that was never built; the plain grid below is the real, shipped implementation.

## Variations (not implemented — would add a `--grid-mark` token + a mask overlay)

Each of these replaces the plain-grid rule above with a fixed, full-viewport `::before` overlay (`z-index:-1`) whose `background: var(--grid-line)` is **masked** by a small tiled SVG shape, instead of drawing lines directly. To actually switch to one: add the token below to `tokens.css`, remove the plain-grid `background-image`/`background-size` rule from `.hud-grid` in `components.css`, and add a masked `::before` rule referencing it (tune `mask-size` to taste — the shapes below assume the same 44px tile as the grid). This is a real (if untried) CSS technique, not verified against this codebase's exact build — treat it as a starting point, not a drop-in.

**Rings / nodes.** A field of small hollow circles; reads as a network of nodes, no glyph.
```
--grid-mark: url("data:image/svg+xml,%3Csvg%20xmlns='http://www.w3.org/2000/svg'%20width='44'%20height='44'%3E%3Ccircle%20cx='22'%20cy='22'%20r='3'%20fill='none'%20stroke='%23fff'%20stroke-width='1'/%3E%3C/svg%3E");
```

**Registration crosses.** Small "+" marks (a crop-mark / reticle feel). Note: at a glance these read as plus-signs scattered across the page.
```
--grid-mark: url("data:image/svg+xml,%3Csvg%20xmlns='http://www.w3.org/2000/svg'%20width='44'%20height='44'%3E%3Cpath%20d='M22%2017.5v9M17.5%2022h9'%20stroke='%23fff'%20stroke-width='1.2'%20stroke-linecap='round'/%3E%3C/svg%3E");
```

**Dots.** The most minimal — small solid dots.
```
--grid-mark: url("data:image/svg+xml,%3Csvg%20xmlns='http://www.w3.org/2000/svg'%20width='44'%20height='44'%3E%3Ccircle%20cx='22'%20cy='22'%20r='1.4'%20fill='%23fff'/%3E%3C/svg%3E");
```

Tuning tips: increase `mask-size` for a sparser field, or nudge `--grid-line`'s alpha (in the dark/light theme blocks of `tokens.css`) if a mark needs to be a touch more or less visible.
