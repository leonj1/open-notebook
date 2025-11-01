# Quick Start Guide

## 30-Second Setup

```bash
cd /home/jose/src/open-notebook/scripts/playwright
./setup.sh
```

## Run the Script

```bash
# Make sure Open Notebook is running
cd /home/jose/src/open-notebook
make start-sqlite

# In another terminal, run the automation
cd /home/jose/src/open-notebook/scripts/playwright
npm run submit-podcast
```

## What Happens

1. Creates a notebook called "Wikipedia Podcast"
2. Adds https://wikipedia.com as a source
3. Waits for processing (~30 seconds)
4. Creates a podcast episode
5. Waits for podcast generation (~5 minutes)
6. Downloads `wikipedia-podcast.mp3`

## Requirements Checklist

Before running, make sure you have:

- [ ] Open Notebook running at http://localhost:5055
- [ ] At least one Episode Profile configured
- [ ] AI models configured (embedding, language, TTS)
- [ ] API keys set (OpenAI/Anthropic/etc.)

## Common Issues

**"No episode profiles available"**
→ Go to Settings → Podcasts → Episode Profiles → Create

**"Connection refused"**
→ Run `make start-sqlite` in the project root

**"No embedding model"**
→ Go to Settings → Models → Add embedding model

## Next Steps

- Read the full [README.md](README.md) for detailed documentation
- Customize the URL in `submit-url-and-podcast.js`
- Try the UI-based test: `npm run submit-podcast-ui`
