# Conversion details

These details explain how the converter works. To use it, follow the [local Docker instructions](../README.md); no separate runtime installation is needed.

## Geometry and preservation

Editable mode edits the OOXML ZIP directly, avoiding a lossy save through a presentation library or office renderer. It updates slide size; slide, layout, master, and drawing-part x/cx transforms; table columns; explicit horizontal text margins, insets, and tab stops. It retains y/cy, row heights, font sizes, line breaks, media, notes, charts, workbooks, relationships, timings and transitions. A table/chart's frame expands; its text remains normal-width. Chart layout may be recalculated by the viewer. Paragraph defaults and text style inheritance remain in place.

Every layout/master part is transformed once, without copying inherited shapes into slides. Group offsets, extents, child offsets/extents, and child positions all scale in their respective coordinate systems. The group `ext / chExt` ratio stays constant, preventing repeated stretch in nested groups. Normalized image crop fractions and shape path coordinate systems are unchanged: their containing frame supplies the stretch. Original cropping is retained; no new slide-level crop is added.

Limitations needing manual review: rotated shapes/text (an anisotropic stretch may require skew that native shape transforms cannot express), SmartArt auto-layout, embedded media/OLE, chart internals, automatic text reflow and font substitution. The converter flags detected rotations, SmartArt and common media. Unknown extensions are retained rather than rewritten. It does not promise pixel-exact editable geometry for every Office extension or animation motion path. Preserved animation XML is not proof of unchanged playback on a wider canvas.

Visual mode replaces each slide's visible shape tree with a full-bleed PNG, hides inherited master shapes and removes its animation timing. Text height, line breaks, and object placement match the **rendered** source under horizontal stretch. Notes and slide transitions stay in the package. Original unused package parts may remain: this is not a document-sanitization tool. Static rendering cannot preserve click sequences, linked content, video/audio playback or animated states.


## Validation coverage

Tests generate a three-slide 4:3 deck with explicit and automatic multiline text, an image, nested grouped shapes, a table, master artwork, layout placeholders, chart, notes, hyperlink, timing and transition. They check horizontal geometry across parts, group display coordinates, unchanged vertical geometry and fonts, preservation of non-edited package parts, explicit rendered line breaks/text height, automatic wrapping differences, visible bottom-edge text, slide count, no lost text in the representative text/table slides, visual full-bleed image bounds, pixel equality against a horizontal-only stretch, actual exported rendering, ratio rejection and repeat-conversion safety. Native PowerPoint and OneScreen playback remain manual acceptance checks.

The Docker image has also been built and exercised through actual uploads in both modes, before/after previews, and downloads of valid 16:9 presentations at the original height. The container includes the renderer and required fonts; results can still differ from PowerPoint when the original presentation uses other fonts or proprietary effects.
