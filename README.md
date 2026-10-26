# SlideStretch

A local web tool and CLI for moving one 4:3 SMART Board `.pptx` to a full-width 16:9 OneScreen presentation. The original is never overwritten. Slide height is unchanged; horizontal positions and dimensions multiply by exactly 4/3, rounded to integer EMUs.

## Run with local Docker

Install and open Docker Desktop, then download this repository and open a terminal in its folder. Run:

```sh
docker compose up --build
```

Open **http://localhost:8000** in your browser. Upload your PowerPoint, choose a conversion mode, and download the new file. Python, LibreOffice and fonts run inside the container; you do not install them separately. The first run downloads and builds the image; later runs reuse it.

Stop with **Ctrl+C**. Start it again with `docker compose up`. To remove the stopped container, run `docker compose down`. Files remain on your computer and the service accepts connections only from your computer. Temporary uploads/results stay in the container until it is removed; download the result before removing it. No account, password or hosting is required.

## Two conversion approaches

| | Editable | Visual match |
|---|---|---|
| Objects | Original editable objects | One full-slide PNG per slide |
| Letter shapes | **Not horizontally stretched** | Horizontally stretched with the entire rendering |
| Automatic wrapping | Can change | Preserved as rendered |
| Explicit breaks / font sizes | Retained | Captured in the image |
| Notes | Retained | Retained |
| Hyperlinks / animations | Original XML and relationships retained; verify playback | No object-level interactivity or animations |
| Transitions | Retained | Retained |
| Main tradeoff | Approximate appearance, continued editing | Static appearance, no object editing |

PowerPoint does not offer a general, interoperable horizontal glyph-scale property for ordinary editable slide text. Widening a box does **not** stretch its letters. Font size would also change height; character spacing only changes gaps. WordArt warp effects exist, but are not a general solution for faithfully preserving ordinary paragraphs, tables, chart labels, and their editable formatting. See [the investigation](docs/text-stretching.md).

Visual match stretches **LibreOffice's rendering**, not a guaranteed identical PowerPoint rendering. Missing fonts, proprietary effects, equations, media, and SmartArt can render differently. Review previews and check important decks in desktop PowerPoint and on the target display. Source content already clipped or outside the slide remains clipped in a visual rendering. Install the original fonts, with suitable licensing, for better fidelity.

## Run

Python 3.12+, LibreOffice (`soffice` on PATH), and the packages in `requirements.txt` are required. No API keys, external services, or npm build are needed.

```sh
cd /workspace/pptconvert
python -m venv --system-site-packages .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

Open the local app in your own browser. Upload one `.pptx`, choose a labeled mode, compare actual before/after slides, then download the new deck and JSON report. Already-16:9 files are copied **byte-for-byte**, even when Visual match is selected. Other aspect ratios are rejected without an output. Limits: 60 MB upload, 400 MB expanded ZIP, 20,000 parts, 150 slides for rendering. No user-facing preview deployment is configured.

This is a local/trusted development tool, not an authenticated public upload service. Files are stored in ignored `.runtime/`; subsequent uploads remove result folders older than one day. Delete `.runtime/` to clear retained uploads manually when the server is stopped. Rendering runs with an isolated LibreOffice profile and a 180-second timeout per deck. PDF and image previews require the renderer; editable conversion still downloads with a clear warning if rendering is unavailable. Visual conversion requires a successful rendering.

## CLI

```sh
python converter.py input.pptx output-editable.pptx --mode editable
python converter.py input.pptx output-visual.pptx --mode visual
```

Choose a different destination from the source. The CLI prints the mode, dimensions, slide count and warnings as JSON. It refuses unsupported ratios and never writes to the source path.

## Geometry and preservation

Editable mode edits the OOXML ZIP directly, avoiding a lossy save through a presentation library or office renderer. It updates slide size; slide, layout, master, and drawing-part x/cx transforms; table columns; explicit horizontal text margins, insets, and tab stops. It retains y/cy, row heights, font sizes, line breaks, media, notes, charts, workbooks, relationships, timings and transitions. A table/chart's frame expands; its text remains normal-width. Chart layout may be recalculated by the viewer. Paragraph defaults and text style inheritance remain in place.

Every layout/master part is transformed once, without copying inherited shapes into slides. Group offsets, extents, child offsets/extents, and child positions all scale in their respective coordinate systems. The group `ext / chExt` ratio stays constant, preventing repeated stretch in nested groups. Normalized image crop fractions and shape path coordinate systems are unchanged: their containing frame supplies the stretch. Original cropping is retained; no new slide-level crop is added.

Limitations needing manual review: rotated shapes/text (an anisotropic stretch may require skew that native shape transforms cannot express), SmartArt auto-layout, embedded media/OLE, chart internals, automatic text reflow and font substitution. The converter flags detected rotations, SmartArt and common media. Unknown extensions are retained rather than rewritten. It does not promise pixel-exact editable geometry for every Office extension or animation motion path. Preserved animation XML is not proof of unchanged playback on a wider canvas.

Visual mode replaces each slide's visible shape tree with a full-bleed PNG, hides inherited master shapes and removes its animation timing. Text height, line breaks, and object placement match the **rendered** source under horizontal stretch. Notes and slide transitions stay in the package. Original unused package parts may remain: this is not a document-sanitization tool. Static rendering cannot preserve click sequences, linked content, video/audio playback or animated states.

## Older `.ppt` presentations

Recommended: open in desktop PowerPoint → **File → Save As → PowerPoint Presentation (.pptx)**. Confirm the saved deck is still 4:3 and check fonts, layout, links and media, then upload it. The app deliberately does not accept legacy binary `.ppt` files.

LibreOffice is an alternative migration route:

```sh
mkdir -p converted
soffice --headless --convert-to pptx --outdir converted old-lesson.ppt
```

Use a new output directory. This migration can change layout, fonts and effects before stretching; compare it against the original. If exact PowerPoint appearance matters, use PowerPoint for migration. Encrypted/password-protected files must first be opened and saved unencrypted by an authorized user.

## Validate and generate a sample

```sh
python -m pip install -r requirements-dev.txt
python -m unittest discover -v
python -m tests.fixtures
python converter.py artifacts/representative-4x3.pptx artifacts/representative-editable.pptx
python converter.py artifacts/representative-4x3.pptx artifacts/representative-visual.pptx --mode visual
```

Tests generate a three-slide 4:3 deck with explicit and automatic multiline text, an image, nested grouped shapes, a table, master artwork, layout placeholders, chart, notes, hyperlink, timing and transition. They check horizontal geometry across parts, group display coordinates, unchanged vertical geometry and fonts, preservation of non-edited package parts, explicit rendered line breaks/text height, automatic wrapping differences, visible bottom-edge text, slide count, no lost text in the representative text/table slides, visual full-bleed image bounds, pixel equality against a horizontal-only stretch, actual exported rendering, ratio rejection and repeat-conversion safety. Native PowerPoint and OneScreen playback remain manual acceptance checks.

Optional end-to-end browser check (with the app running): `python -m tests.browser_smoke`. It requires the development dependencies and system Chromium at `/usr/bin/chromium`, and saves screenshots and downloaded decks under ignored `artifacts/`.
