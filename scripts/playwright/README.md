# Open Notebook Playwright Automation Scripts

This directory contains automation scripts for Open Notebook using both API-based and UI-based approaches with Playwright.

## Quick Start

```bash
# 1. Setup (one-time)
cd scripts/playwright
./setup.sh

# 2. Make sure Open Notebook is running
cd ../../
make start-sqlite

# 3. Run the API-based automation
cd scripts/playwright
npm run submit-podcast
```

## Setup

### Automated Setup
```bash
cd scripts/playwright
./setup.sh
```

### Manual Setup

1. Install Node.js dependencies:
```bash
npm install
```

2. Install Playwright browsers (for UI automation):
```bash
npx playwright install chromium
```

## Available Scripts

### 1. API-Based Automation (Recommended)

**submit-url-and-podcast.js** - Uses the REST API directly

**What it does:**
1. Creates a notebook
2. Adds Wikipedia URL as a source
3. Waits for source processing
4. Creates a podcast episode
5. Downloads the generated audio

**Usage:**
```bash
npm run submit-podcast
```

**Output:**
- Creates `wikipedia-podcast.mp3` in the current directory
- Prints IDs for notebook, source, and episode

**Advantages:**
- Fast and reliable
- Easy to debug
- Works headlessly
- Better for CI/CD

---

### 2. UI-Based Automation

**submit-url-podcast-ui.spec.js** - Interacts with the actual UI using Playwright

**What it does:**
- Tests the full user workflow through the browser
- Creates notebook via UI
- Adds source via form
- Generates podcast via UI

**Usage:**
```bash
# Run in headless mode
npm run submit-podcast-ui

# Run with browser visible
npm run test:headed

# Run in interactive UI mode
npm run test:ui

# Run all tests
npm test
```

**Advantages:**
- Tests actual UI functionality
- Catches UI bugs
- Visual feedback
- Better for E2E testing

## Configuration

### API Script Configuration

Edit `submit-url-and-podcast.js`:

```javascript
const API_BASE_URL = 'http://localhost:5055';  // Change API endpoint
const SOURCE_URL = 'https://wikipedia.com';    // Change URL to submit
```

### Playwright Configuration

Edit `playwright.config.js`:

```javascript
use: {
  baseURL: 'http://localhost:3006',  // Frontend URL
  // ... other options
}
```

## Requirements

### System Requirements
- Node.js 18+
- Open Notebook running (API + Frontend)
- Sufficient disk space for audio files

### Open Notebook Configuration
Before running the scripts, ensure Open Notebook has:

1. **Episode Profile** - At least one podcast episode profile configured
   - Go to: Settings → Podcasts → Episode Profiles
   - Create a profile with speaker configuration

2. **AI Models Configured:**
   - **Embedding Model** - For source vectorization (e.g., `text-embedding-3-small`)
   - **Language Model** - For podcast generation (e.g., `gpt-4o-mini`)
   - **TTS Model** - For audio generation (e.g., `tts-1`)
   - Go to: Settings → Models

3. **API Keys Set:**
   - OpenAI, Anthropic, or your preferred provider
   - Go to: Settings → Models → Add Model

## Workflow Details

### API-Based Workflow

```
1. POST /api/notebooks          → Create notebook
2. POST /api/sources            → Add Wikipedia URL
3. GET  /api/sources/{id}       → Poll for processing (every 2s)
4. GET  /api/episode-profiles   → Get available profiles
5. POST /api/podcasts           → Create episode
6. GET  /api/commands/{id}      → Poll for completion (every 5s)
7. GET  /api/podcasts/{id}/audio → Download MP3
```

### Expected Timing
- Source processing: 10-30 seconds
- Podcast generation: 2-10 minutes (depending on content length and AI models)
- Total workflow: ~5-15 minutes

## Output Examples

### Successful Run
```
🚀 Starting Open Notebook automation script...

📚 Creating notebook...
✅ Notebook created: notebook:abc123

📄 Adding source: https://wikipedia.com...
✅ Source created: source:xyz789

⏳ Waiting for source to be processed...
✅ Source processed successfully (15234 chars)

🎙️ Fetching episode profiles...
✅ Found 1 episode profile(s)
   Using episode profile: default_profile

🎬 Creating podcast episode...
✅ Podcast episode created: episode:def456

⏳ Waiting for podcast generation (this may take several minutes)...
   Attempt 15/120: Status=running, Progress=75%
✅ Podcast generation completed!

💾 Downloading podcast audio to wikipedia-podcast.mp3...
✅ Podcast downloaded successfully: wikipedia-podcast.mp3

🎉 SUCCESS! Workflow completed successfully!
📁 Podcast saved to: wikipedia-podcast.mp3
📊 Notebook ID: notebook:abc123
📄 Source ID: source:xyz789
🎙️ Episode ID: episode:def456
```

## Troubleshooting

### "No episode profiles available"
**Solution:** Create an episode profile in Open Notebook
1. Open http://localhost:3006
2. Go to Settings → Podcasts → Episode Profiles
3. Click "Create Profile"
4. Configure speakers and settings
5. Save

### "Source processing timeout"
**Solution:** Increase timeout or check source
- Source might be very large
- Check network connectivity
- Increase `maxAttempts` in `waitForSourceProcessing()`

### "Podcast generation timeout"
**Solution:** Increase timeout
- Podcast generation can take 5-10 minutes for long content
- Check AI model availability
- Increase `maxAttempts` in `waitForPodcastGeneration()`

### "Connection refused" or "ECONNREFUSED"
**Solution:** Start Open Notebook
```bash
cd /home/jose/src/open-notebook
make start-sqlite
```

Wait until you see:
```
✅ Services started!
📱 Frontend: http://localhost:3006
🔗 API: http://localhost:5055
```

### "No embedding model configured"
**Solution:** Configure embedding model
1. Go to Settings → Models
2. Add an embedding model (e.g., `text-embedding-3-small` from OpenAI)
3. Set it as default embedding model

### UI test fails with selector errors
**Solution:** Update selectors
- The UI might have changed
- Update selectors in `tests/submit-url-podcast-ui.spec.js`
- Use Playwright Inspector: `npx playwright test --debug`

## Advanced Usage

### Custom URL and Settings

```javascript
// Modify submit-url-and-podcast.js
const SOURCE_URL = 'https://en.wikipedia.org/wiki/Artificial_intelligence';

// Change podcast briefing
const briefing = 'Create a detailed technical discussion about AI...';
```

### Batch Processing Multiple URLs

Create a new script:
```javascript
const urls = [
  'https://wikipedia.com',
  'https://en.wikipedia.org/wiki/Machine_learning',
  'https://en.wikipedia.org/wiki/Deep_learning'
];

for (const url of urls) {
  // Process each URL
}
```

### Integration with CI/CD

```yaml
# .github/workflows/test.yml
- name: Run automation tests
  run: |
    npm run submit-podcast-ui
```

## API Documentation

For detailed API reference:
- **Interactive Docs:** http://localhost:5055/docs
- **Local Documentation:** `/docs/development/api-reference.md`
- **Swagger JSON:** http://localhost:5055/openapi.json

## Project Structure

```
scripts/playwright/
├── README.md                          # This file
├── package.json                       # Dependencies and scripts
├── playwright.config.js               # Playwright configuration
├── setup.sh                          # Setup script
├── submit-url-and-podcast.js         # API-based automation
├── tests/
│   └── submit-url-podcast-ui.spec.js # UI-based Playwright test
└── .gitignore                        # Ignore node_modules, audio files
```

## Contributing

To add new automation scripts:

1. Create a new `.js` file in this directory
2. Add a script entry in `package.json`
3. Document usage in this README
4. Test thoroughly before committing

## License

This follows the same license as Open Notebook (MIT).
