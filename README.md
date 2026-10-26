# SlideStretch

Convert a 4:3 SMART Board PowerPoint into a full-width 16:9 presentation for OneScreen. Use it in your browser, running locally through Docker. Your original file stays unchanged.

## What you need

**Docker Desktop** is the only software you need to install for the converter. Python, LibreOffice, and fonts are already included in the container. No separate installation, hosting account, or API key is needed.

## Start

1. Install and open [Docker Desktop](https://www.docker.com/products/docker-desktop/). On Windows, use Linux containers (the default).
2. [Download this repository as a ZIP](https://github.com/woodsdana-ctrl/pptconvert/archive/refs/heads/main.zip) and extract it.
3. Open a terminal in the extracted folder containing `compose.yaml`.
4. Run:

   ```sh
   docker compose up --build
   ```

5. Once the app starts, open **http://localhost:8000** in your browser on the same computer.

The first start downloads and builds the container, which can take several minutes and requires Internet access. Later starts reuse the image. No cloud deployment or Codex environment publication is needed.

## Convert a presentation

1. Upload one `.pptx` file.
2. Choose **Editable** or **Visual match** below.
3. Click **Convert to widescreen**.
4. Compare the before-and-after previews. Use the arrows to review each slide.
5. Download the new `.pptx`. Open it in PowerPoint and check it on the OneScreen before presenting.

Slide height remains unchanged. Horizontal positions and widths multiply by 4/3, without added side margins or new cropping. Presentations already in 16:9 are copied unchanged so they cannot stretch twice. Other aspect ratios are flagged and rejected.

### Choose a conversion mode

| | Editable | Visual match |
|---|---|---|
| Best for | Continuing to edit the presentation | Preserving the rendered appearance |
| Text, shapes, images, tables, charts | Remain editable where supported | Become one flat image per slide |
| Actual letter shapes | **Keep their original width** | **Stretch horizontally with the slide** |
| Automatic line breaks | Can change | Preserved as rendered |
| Speaker notes | Retained | Retained |
| Object hyperlinks and animations | Original data retained; check playback | Lost |
| Slide transitions | Retained | Retained |

**Widening a text box does not stretch its letters.** PowerPoint has no general editable glyph-width control for ordinary slide text. Choose Visual match if horizontally stretched lettering is essential. See [the text-stretching investigation](docs/text-stretching.md) for the technical explanation.

Visual match captures the renderer included in Docker. Missing original fonts and PowerPoint-specific effects can change appearance; the previews help you check the result. Content already clipped in the original slide remains clipped in its rendering. See [conversion details and test coverage](docs/conversion-details.md) for the full limitations.

## Stop, restart, or update

**Stop:** press **Ctrl+C** in the terminal where the app is running.

**Start again:** from the same folder, run:

```sh
docker compose up
```

**Remove the container and its temporary files:** after downloading your results, run:

```sh
docker compose down
```

**Update:** stop the app, download and extract the latest repository ZIP, then run `docker compose up --build` in the new folder. If you use Git, pull the latest changes in the existing folder and run the same build command.

## Where your files go

The app runs on your computer and accepts connections only from that computer. Uploaded presentations, previews, and results are stored inside the container, not uploaded to a hosting service. Download your converted presentation before removing the container; `docker compose down` deletes its temporary files. The original presentation on your computer is never modified.

Uploads older than one day are cleaned up on subsequent uploads. Limits are 60 MB per upload, 400 MB expanded presentation data, 20,000 package parts, and 150 slides for previews. Rendering has a 180-second timeout per deck. Start with a smaller deck if a large one cannot finish.

## Older `.ppt` presentations

Open the original in desktop PowerPoint and choose **File → Save As → PowerPoint Presentation (.pptx)**. Save a new file, check that it still looks correct and is still 4:3, then upload the `.pptx` to SlideStretch. Legacy `.ppt` files are not accepted directly.

Password-protected files must first be opened and saved as an unencrypted `.pptx` by an authorized user.

## Troubleshooting

- **Docker cannot connect:** open Docker Desktop and wait until its engine is running, then retry.
- **No configuration file found:** open the terminal in the extracted folder containing `compose.yaml`.
- **Port 8000 is already in use:** stop the other app using that port, then retry.
- **The browser cannot open the app:** keep the terminal running, wait for startup to finish, and use `http://localhost:8000` on the same computer as Docker Desktop.
- **Docker reports an out-of-memory error:** allow Docker Desktop more memory or try a smaller deck.
- **Fonts, wrapping, or effects look different:** review both conversion modes and compare their previews. Editable mode can reflow text; Visual match captures the bundled renderer, which can differ from PowerPoint.
- **Preview or rendering fails:** confirm the original opens in PowerPoint, save it again as `.pptx`, and try a smaller deck. Editable conversion may still offer a download with a preview warning; Visual match requires successful rendering.
