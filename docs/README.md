# Documentation

Diagrams and flow references for the YouTube playlist. Each video folder keeps the same material used on camera: narrative guide, short walkthrough, Mermaid source, and exported SVG.

Video folders are snapshots for their episode. For the current runtime design,
including threaded replies and MongoDB Atlas memory, use the related repo docs
below.

## Diagrams by video

| Video | Topic | Folder |
| --- | --- | --- |
| 2 | Integrating real AI (OpenAI + `ai_handler.py`) | [diagrams/video-2-real-ai/](diagrams/video-2-real-ai/) |

## Folder layout (per video)

| File | Purpose |
| --- | --- |
| `README.md` | Full diagram guide: flowchart, sequence view, file boundaries, talking points |
| `flow-walkthrough.md` | Shorter on-slide walkthrough of the main flowchart |
| `flowchart.md` | Mermaid source for the main flowchart |
| `flowchart.svg` | Rendered flowchart for viewers and thumbnails |

## Related repo docs

- [ARCHITECTURE.md](../ARCHITECTURE.md) — runtime architecture for the whole bot
- [PLAYLIST.md](../PLAYLIST.md) — full video roadmap
- [setupslackwebsocket.md](../setupslackwebsocket.md) — Slack Socket Mode setup (Video 1)
