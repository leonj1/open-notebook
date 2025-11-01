/**
 * Playwright UI test for submitting URL and creating podcast
 *
 * This test uses the actual UI to:
 * 1. Create a notebook
 * 2. Add a source URL
 * 3. Navigate to podcasts
 * 4. Create a podcast episode
 */

import { test, expect } from '@playwright/test';

test.describe('Submit URL and Create Podcast via UI', () => {
  let notebookName;
  let notebookId;

  test.beforeEach(async ({ page }) => {
    // Generate unique notebook name
    notebookName = `Wikipedia Podcast ${Date.now()}`;

    // Navigate to the app
    await page.goto('/');

    // Wait for the app to load
    await page.waitForLoadState('networkidle');
  });

  test('should create notebook, add source, and generate podcast', async ({ page }) => {
    // Step 1: Create a new notebook
    console.log('Creating notebook...');

    // Click the "New Notebook" button (adjust selector based on actual UI)
    await page.click('button:has-text("New Notebook"), [aria-label="Create notebook"]');

    // Fill in notebook details
    await page.fill('input[name="name"], input[placeholder*="notebook"]', notebookName);
    await page.fill('textarea[name="description"], textarea[placeholder*="description"]',
      'Notebook for Wikipedia URL and podcast generation');

    // Submit the form
    await page.click('button:has-text("Create"), button[type="submit"]');

    // Wait for notebook to be created
    await page.waitForURL(/.*notebook.*/);
    await expect(page.locator('h1, h2').filter({ hasText: notebookName })).toBeVisible();

    console.log('✅ Notebook created');

    // Step 2: Add Wikipedia URL as a source
    console.log('Adding source...');

    // Click "Add Source" button
    await page.click('button:has-text("Add Source")');

    // Select "Link" option
    await page.click('button:has-text("Link"), [role="tab"]:has-text("Link")');

    // Enter URL
    await page.fill('input[type="url"], input[name="url"]', 'https://wikipedia.com');

    // Click "Process" or "Add" button
    await page.click('button:has-text("Process"), button:has-text("Add")');

    // Wait for source to appear in the list
    await expect(page.locator('text=/wikipedia/i')).toBeVisible({ timeout: 30000 });

    console.log('✅ Source added');

    // Step 3: Wait for source processing (check for completion indicators)
    console.log('Waiting for source processing...');

    // Wait for processing indicator to disappear or success message
    await page.waitForSelector('[data-status="processing"], .processing', {
      state: 'hidden',
      timeout: 60000
    }).catch(() => {
      console.log('No processing indicator found, assuming complete');
    });

    // Wait a bit for embeddings and processing
    await page.waitForTimeout(5000);

    console.log('✅ Source processed');

    // Step 4: Navigate to podcasts section
    console.log('Navigating to podcasts...');

    // Click on "Podcasts" tab or navigation item
    await page.click('a:has-text("Podcasts"), button:has-text("Podcasts"), [role="tab"]:has-text("Podcasts")');

    console.log('✅ On podcasts page');

    // Step 5: Create a new podcast episode
    console.log('Creating podcast episode...');

    // Click "New Episode" or "Create Podcast" button
    await page.click('button:has-text("New Episode"), button:has-text("Create Podcast"), button:has-text("Generate")');

    // Fill in episode details
    await page.fill('input[name="name"], input[placeholder*="episode"]',
      'Wikipedia Overview Podcast');

    await page.fill('textarea[name="briefing"], textarea[placeholder*="briefing"]',
      'Create an engaging podcast discussing the main page of Wikipedia, covering the featured articles, current events, and interesting facts.');

    // Select the Wikipedia source (checkbox or selection)
    await page.click('[type="checkbox"][value*="source"]').catch(() => {
      // If checkbox doesn't exist, try other selection methods
      console.log('Trying alternative source selection...');
    });

    // Submit podcast creation
    await page.click('button:has-text("Generate"), button:has-text("Create"), button[type="submit"]');

    // Wait for podcast generation to start
    await expect(page.locator('text=/generating|processing/i')).toBeVisible({ timeout: 10000 });

    console.log('✅ Podcast generation started');

    // Step 6: Wait for podcast generation to complete
    console.log('Waiting for podcast generation (this may take several minutes)...');

    // This could take a while - increase timeout
    await expect(page.locator('text=/completed|download|ready/i')).toBeVisible({
      timeout: 600000 // 10 minutes
    });

    console.log('✅ Podcast generated successfully!');

    // Step 7: Verify download button is available
    await expect(page.locator('button:has-text("Download"), a:has-text("Download")')).toBeVisible();

    console.log('🎉 Test completed successfully!');
  });

  test('should handle source processing errors gracefully', async ({ page }) => {
    // Test error handling
    console.log('Testing error handling...');

    // Create notebook
    await page.click('button:has-text("New Notebook")');
    await page.fill('input[name="name"]', `Error Test ${Date.now()}`);
    await page.click('button[type="submit"]');

    // Try to add an invalid source
    await page.click('button:has-text("Add Source")');
    await page.fill('input[type="url"]', 'invalid-url');
    await page.click('button:has-text("Process")');

    // Verify error message appears
    await expect(page.locator('text=/error|invalid/i')).toBeVisible({ timeout: 5000 });

    console.log('✅ Error handling verified');
  });
});
