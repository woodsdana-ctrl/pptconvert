# Investigation: editable horizontal text stretch

Investigated before implementing the converter.

## What the file format supports

The Microsoft Open XML SDK's DrawingML schema describes `CT_TextCharacterProperties` (run/default-run properties) with font size (`sz`), bold/italic, kerning (`kern`), character spacing (`spc`), baseline, and font selection. It provides no general independent x-scale for glyphs. `CT_TextBodyProperties` controls wrapping, margins, rotation, vertical text and auto-fit. `CT_TextNormalAutofit.fontScale` is a font-size scale, not an independent width scale.

Sources:

- [Microsoft Open XML SDK DrawingML schema](https://github.com/dotnet/Open-XML-SDK/blob/main/data/schemas/schemas_openxmlformats_org_drawingml_2006_main.json): inspected `CT_TextCharacterProperties`, `CT_TextBodyProperties`, and `CT_TextNormalAutofit`.
- [SDK TextCharacterPropertiesType reference](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.drawing.textcharacterpropertiestype)
- [SDK NormalAutoFit reference](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.drawing.normalautofit)
- [SDK PresetTextWarp reference](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.drawing.presettextwarp)

PowerPoint's WordArt/text warp effects can deform special editable text objects. They are not a drop-in document-wide glyph-width property: applying them to ordinary paragraphs or table/chart text may change wrapping, sizing, alignment, styling and editing behavior. A custom wider font is likewise font-specific and cannot reliably reproduce arbitrary original lettering. Converting glyphs to vector outlines preserves some appearance but loses ordinary text editing, search and semantic text; it is not offered as editable text here.

## Consequences

1. **Editable conversion:** scale horizontal geometry by 4/3; preserve native text, explicit breaks and font sizes. Do not claim widened letters or exact wrapping. Automatic wraps, autofit and chart label layout can change. The sample rendering test demonstrates an actual changed automatic wrap while explicit line breaks and vertical glyph height remain stable.
2. **Visual-match conversion:** render the original slide before changing slide size; resize that bitmap's width by 4/3 while keeping its pixel height fixed; place it across a 16:9 slide at the original physical height. This stretches the actual rendered letterforms and preserves rendered line breaks and relative placement. It sacrifices object-level editing, links, animations, and interactive media. Raster resolution limits zoom quality.

“Visual match” means match to the chosen renderer. The Docker image includes LibreOffice, so users do not install or run it separately. Its rendering cannot guarantee the exact appearance of desktop PowerPoint, especially with unavailable fonts and proprietary effects. For a renderer-perfect match to PowerPoint, a future Windows/PowerPoint export backend would need to render source slides using the licensed desktop application. That backend is not implemented or claimed here.
