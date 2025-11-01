/**
 * Playwright script to submit a URL to Open Notebook and generate a podcast
 *
 * This script:
 * 1. Creates a notebook
 * 2. Adds Wikipedia URL as a source
 * 3. Waits for source processing
 * 4. Creates a podcast episode from the source
 * 5. Waits for podcast generation
 * 6. Downloads the podcast audio
 */

import axios from 'axios';
import { writeFileSync } from 'fs';

const API_BASE_URL = 'http://localhost:5055';
const SOURCE_URL = 'https://wikipedia.com';

// Configure axios with timeout
const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 300000, // 5 minute timeout
  headers: {
    'Content-Type': 'application/json'
  }
});

/**
 * Wait for a period of time
 */
async function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * Step 1: Create a notebook
 */
async function createNotebook() {
  console.log('📚 Creating notebook...');
  const response = await api.post('/api/notebooks', {
    name: 'Wikipedia Podcast',
    description: 'Notebook for Wikipedia URL and podcast generation'
  });
  console.log(`✅ Notebook created: ${response.data.id}`);
  return response.data.id;
}

/**
 * Step 2: Add Wikipedia URL as a source
 */
async function addSource(notebookId) {
  console.log(`📄 Adding source: ${SOURCE_URL}...`);
  const response = await api.post('/api/sources/json', {
    type: 'link',
    notebooks: [notebookId],
    url: SOURCE_URL,
    embed: true,
    delete_source: false,
    async_processing: true  // Use async to avoid DNS issues
  });
  console.log(`✅ Source queued for processing: ${response.data.id}`);
  return response.data;
}

/**
 * Step 3: Wait for source to be processed (async mode)
 */
async function waitForSourceProcessing(sourceData, maxAttempts = 60) {
  console.log('⏳ Waiting for source to be processed...');
  const sourceId = sourceData.id;
  const commandId = sourceData.command_id;

  if (!commandId) {
    console.log('⚠️  No command ID found, checking source directly');
  }

  for (let i = 0; i < maxAttempts; i++) {
    try {
      // Check command status if available
      if (commandId) {
        const commandResponse = await api.get(`/api/commands/${commandId}`);
        const command = commandResponse.data;

        if (command.status === 'completed') {
          console.log(`✅ Source processing completed!`);
          const sourceResponse = await api.get(`/api/sources/${sourceId}`);
          return sourceResponse.data;
        } else if (command.status === 'failed') {
          throw new Error(`Source processing failed: ${command.error || 'Unknown error'}`);
        } else {
          console.log(`   Attempt ${i + 1}/${maxAttempts}: Status=${command.status}`);
        }
      } else {
        // Fall back to checking source directly
        const response = await api.get(`/api/sources/${sourceId}`);
        const source = response.data;

        if (source.full_text && source.full_text.length > 0) {
          console.log(`✅ Source processed successfully (${source.full_text.length} chars)`);
          return source;
        }
      }

      await sleep(2000); // Wait 2 seconds between checks
    } catch (error) {
      console.log(`   Attempt ${i + 1}/${maxAttempts}: Error checking status`);
      await sleep(2000);
    }
  }

  throw new Error('Source processing timeout - exceeded maximum wait time');
}

/**
 * Step 4: Get episode profiles
 */
async function getEpisodeProfiles() {
  console.log('🎙️ Fetching episode profiles...');
  const response = await api.get('/api/episode-profiles');

  if (!response.data || response.data.length === 0) {
    throw new Error('No episode profiles available. Please configure at least one episode profile in Open Notebook.');
  }

  console.log(`✅ Found ${response.data.length} episode profile(s)`);
  return response.data[0]; // Use the first available profile
}

/**
 * Step 5: Create a podcast episode
 */
async function createPodcast(episodeProfileId, sourceId) {
  console.log('🎬 Creating podcast episode...');
  const response = await api.post('/api/podcasts', {
    name: 'Wikipedia Overview Podcast',
    briefing: 'Create an engaging podcast discussing the main page of Wikipedia, covering the featured articles, current events, and interesting facts.',
    episode_profile_id: episodeProfileId,
    source_ids: [sourceId],
    note_ids: []
  });

  console.log(`✅ Podcast episode created: ${response.data.id}`);
  return response.data;
}

/**
 * Step 6: Wait for podcast generation to complete
 */
async function waitForPodcastGeneration(episodeId, maxAttempts = 120) {
  console.log('⏳ Waiting for podcast generation (this may take several minutes)...');

  for (let i = 0; i < maxAttempts; i++) {
    try {
      const response = await api.get(`/api/podcasts/${episodeId}`);
      const episode = response.data;

      // Check command status
      if (episode.command && episode.command.id) {
        const commandResponse = await api.get(`/api/commands/${episode.command.id}`);
        const command = commandResponse.data;

        if (command.status === 'completed') {
          console.log('✅ Podcast generation completed!');
          return episode;
        } else if (command.status === 'failed') {
          throw new Error(`Podcast generation failed: ${command.error || 'Unknown error'}`);
        } else {
          const progress = command.progress || 0;
          console.log(`   Attempt ${i + 1}/${maxAttempts}: Status=${command.status}, Progress=${progress}%`);
        }
      }

      await sleep(5000); // Wait 5 seconds between checks
    } catch (error) {
      if (error.response?.status === 404) {
        console.log(`   Attempt ${i + 1}/${maxAttempts}: Podcast not ready yet...`);
      } else {
        console.log(`   Attempt ${i + 1}/${maxAttempts}: Error checking status`);
      }
      await sleep(5000);
    }
  }

  throw new Error('Podcast generation timeout - exceeded maximum wait time');
}

/**
 * Step 7: Download podcast audio
 */
async function downloadPodcast(episodeId, filename = 'wikipedia-podcast.mp3') {
  console.log(`💾 Downloading podcast audio to ${filename}...`);

  const response = await api.get(`/api/podcasts/${episodeId}/audio`, {
    responseType: 'arraybuffer'
  });

  writeFileSync(filename, response.data);
  console.log(`✅ Podcast downloaded successfully: ${filename}`);
  return filename;
}

/**
 * Main execution flow
 */
async function main() {
  console.log('🚀 Starting Open Notebook automation script...\n');

  try {
    // Step 1: Create notebook
    const notebookId = await createNotebook();
    console.log('');

    // Step 2: Add source
    const sourceData = await addSource(notebookId);
    console.log('');

    // Step 3: Wait for source processing
    await waitForSourceProcessing(sourceData);
    console.log('');

    // Step 4: Get episode profiles
    const episodeProfile = await getEpisodeProfiles();
    console.log(`   Using episode profile: ${episodeProfile.name}`);
    console.log('');

    // Step 5: Create podcast
    const episode = await createPodcast(episodeProfile.id, sourceData.id);
    console.log('');

    // Step 6: Wait for podcast generation
    await waitForPodcastGeneration(episode.id);
    console.log('');

    // Step 7: Download podcast
    const filename = await downloadPodcast(episode.id);
    console.log('');

    console.log('🎉 SUCCESS! Workflow completed successfully!');
    console.log(`📁 Podcast saved to: ${filename}`);
    console.log(`📊 Notebook ID: ${notebookId}`);
    console.log(`📄 Source ID: ${sourceData.id}`);
    console.log(`🎙️ Episode ID: ${episode.id}`);

  } catch (error) {
    console.error('\n❌ ERROR:', error.message);
    if (error.response) {
      console.error('   API Response:', error.response.status, error.response.statusText);
      if (error.response.data) {
        console.error('   Details:', JSON.stringify(error.response.data, null, 2));
      }
    }
    process.exit(1);
  }
}

// Run the script
main();
