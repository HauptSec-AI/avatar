# Avatar generation recipe

The Avatar's icon is the owner's real photo (`knowledge/pic.jpg`) rebuilt as a **synthetic digital
twin**. It is produced programmatically so any site owner gets a matching twin from their own photo.
Three files are produced into `assets/`:

- `avatar-human.png` — natural square crop of the real photo (the **human** icon).
- `avatar-robot.png` — the twin, square, with a HUD frame (hero / showcase use).
- `avatar-robot-round.png` — the twin tuned for circular chat avatars (inner ring, vignette,
  no corner brackets).

## Crop
Square crop centred on the face, output as `avatar-human.png`. If starting from a non-square photo,
crop centred on the face with the eyes roughly 40-45% from the top; a source photo that's already
square (e.g. exported from a portrait tool) can be used as-is.

## Twin treatment — image-to-image via an image-generation model

The shipped assets were produced with an image-capable chat model over OpenRouter (e.g.
`google/gemini-3-pro-image` or `google/gemini-3.1-flash-image`), sending `avatar-human.png` as
input with a text prompt describing the desired filter. This is simpler and more reproducible than
a hand-built pixel pipeline, and adapts automatically to whatever palette the theme is using.

Prompt shape that worked well (adjust the color language to match your `tokens.css` dark-theme
palette — see the brand comment block at the top of that file):

> Apply a "digital twin" synthetic-scan filter to this exact portrait. This is a filter/color-grade
> pass, NOT a redraw — keep the same composition, facial proportions, hairstyle, pose and
> expression, and level of detail/texture. Do not turn it into cartoon or vector-style line art, and
> do not add big glowing cartoon eyes.
>
> Apply: a duotone tone map using [your dark/mid/bright theme colors] across the whole face, hair
> and clothing, no warm tones or skin tones remaining; a subtle posterize/quantized-tone look (like
> a CRT/thermal readout) that still preserves the original texture; faint horizontal scanlines; a
> small, subtle bright catchlight in each eye (not a big glowing orb); a background replaced
> entirely with a dark radial gradient plus a faint grid texture in the same palette; keep it a
> square, centered head-and-shoulders composition matching the source framing.

Send the request with `modalities: ["image", "text"]`, decode the returned base64 image, and you
have your synthetic twin base image (typically ~1024×1024).

## Framing — local post-processing

From that base image, produce the two shipped variants with a small script (PIL/Pillow is enough,
no AI needed for this part) — center-crop to square, resize to 900×900, then:

- **`avatar-robot.png`** (square, HUD hero use) — draw four L-shaped corner brackets in your theme's
  border/accent color, plus a short accent-color tick centered at the top edge.
- **`avatar-robot-round.png`** (circular chat avatars) — draw a thin inscribed ring in the same
  accent color, and a soft vignette outside it. No corner brackets.

Keep the result **recognisably the person** and clearly **synthetic**, in whatever palette the
theme currently uses — this project's current theme is a Matrix-style black/green palette (see
`tokens.css`), so the shipped assets are black-and-green rather than navy-and-cyan; regenerate with
your own palette's colors if you change themes.

## Usage
- Human messages & admin owner chip → `avatar-human.png` in `.avatar-human` (accent-color ring,
  driven by `--yellow-strong` in `tokens.css`).
- Avatar messages → `avatar-robot-round.png` in `.avatar-twin` (accent-color ring, driven by
  `--blue-line`).
- Hero / identity showcase → `avatar-robot.png` (framed square).
