# FF-Auto User Guide

Welcome to FF-Auto — your AI image generation and curation workspace. This guide will walk you through every feature with real examples so you can hit the ground running on day one.

---

## Table of Contents

1. [The Big Picture](#1-the-big-picture)
2. [Navigation](#2-navigation)
3. [Workspace — Process Images](#3-workspace--process-images)
4. [Gallery — Review & Approve](#4-gallery--review--approve)
5. [Video — Create Videos](#5-video--create-videos)
6. [Prompts — Manage Personas](#6-prompts--manage-personas)
7. [Monitor — System Health](#7-monitor--system-health)
8. [Archive — Browse Past Work](#8-archive--browse-past-work)
9. [Common Workflows](#9-common-workflows)
10. [Tips & Notices](#10-tips--notices)

---

## 1. The Big Picture

FF-Auto takes your reference photos and turns them into AI-generated variations at scale. The general flow is:

```
You upload photos → AI processes them → You review results → You approve & download
```

Think of it as a **photo production pipeline**: you feed in raw inputs, the system generates options, and you curate the best ones for use.

---

## 2. Navigation

The app has a **left sidebar** with links to all pages:

| Page | What It Does |
|------|-------------|
| Workspace | Upload photos and start AI processing |
| Gallery | Review, approve, or reject generated images |
| Video | Generate AI videos and create compilations |
| Prompts | Configure personas and AI instructions |
| Monitor | Check if the system is healthy |
| Archive | Browse historical outputs (read-only) |

---

## 3. Workspace — Process Images

This is where you start every session. You upload reference photos and configure how the AI should generate variations from them.

### 3.1 Uploading Reference Images

1. Go to **Workspace**
2. In the **Image Library** panel, click **Upload Images**
3. Select one or more photos from your computer
4. Your images appear in the library as thumbnails

> **Notice:** Accepted formats are JPG and PNG. Avoid very small images (under 512×512 px) — the AI works best with clear, well-lit photos.

### 3.2 Selecting Images to Process

- Click a thumbnail to select it (a checkmark appears)
- Click multiple thumbnails to select more
- Click a selected image again to deselect it

You can select as many as you want — the system will queue them all.

### 3.3 Configuring Settings

On the right panel, you'll see the processing settings. Here's what each one does:

| Setting | What It Means | Tip |
|---------|---------------|-----|
| **Persona** | The character style/profile to apply | Start with the persona your team has set up for the project |
| **Workflow Type** | `turbo` = fast (5–30 sec); `standard` = higher quality but slower | Use turbo for testing, standard for final output |
| **Vision Model** | The AI that reads your reference photo | Leave as default unless instructed otherwise |
| **Variations** | How many images to generate per reference | 3 is a good starting point |
| **Strength** | How closely the output follows the reference | Lower = more creative; Higher = stays closer to original |
| **Seed Strategy** | How randomness is controlled | `random` = different results every time; `fixed` = reproducible output |
| **Image Dimensions** | Width × Height of output | Match your final use — e.g., 1024×1024 for square posts |
| **LoRA Model** | Optional style model (advanced) | Leave blank unless instructed |

> **Notice:** You don't need to reconfigure these settings every session. The app **automatically saves your last used settings** and restores them when you return.

### 3.4 Saving and Loading Presets

If you have a configuration you use often (e.g., "portrait batch" with specific settings), you can save it as a preset:

1. Configure the settings you want
2. Click **Save Preset** → give it a name
3. Next time, click **Load Preset** and pick it from the list

### 3.5 Starting Processing

- **Single image:** Select one image → click **Process**
- **Multiple images:** Select several images → click **Process Batch**

The system queues all jobs and processes them in the background. You can navigate away and come back — the jobs keep running.

### 3.6 Watching Progress

The **Active Tasks** panel shows all currently running jobs with a live status:
- `queued` — waiting to start
- `processing` — currently generating
- `done` — complete, find result in Gallery

The **Execution History** table below shows recent jobs including their status and timestamp.

> **Notice:** Processing takes time. A single image on `turbo` takes roughly 10–30 seconds. A batch of 10 images may take several minutes. Do not close the browser tab if you need to track exact job statuses.

---

## 4. Gallery — Review & Approve

After processing, your generated images land in the Gallery. This is where you curate and manage them.

### 4.1 Three Tabs

| Tab | What It Shows |
|-----|---------------|
| **Pending** | Newly generated images waiting for your decision |
| **Approved** | Images you've accepted |
| **Disapproved** | Images you've rejected |

Start in **Pending** each session.

### 4.2 Viewing an Image

- Click any thumbnail to open a larger preview
- Click the **ⓘ info icon** on a card to see metadata:
  - The **reference image** used to create it (shown side by side)
  - The **prompt** the AI used
  - The **persona** applied
  - The **seed** (useful if you want to reproduce the same output)

### 4.3 Approving and Disapproving

**Single image:**
- Hover over a thumbnail to reveal action buttons
- Click ✓ (green checkmark) to approve
- Click ✗ (red X) to disapprove

**Multiple images:**
1. Click the **Select** toggle to enter selection mode
2. Click each image you want to act on (or **Select All**)
3. Click **Approve Selected** or **Disapprove Selected**

> **Notice:** Approving moves the file to the `approved/` folder. Disapproving moves it to `disapproved/`. These are real file moves — but you can always undo.

### 4.4 Renaming on Approval

When approving, you can give the image a custom filename:
1. Single-approve an image (don't use bulk approve)
2. A rename field appears — type the new name
3. Click Approve — the file is moved and renamed

### 4.5 Undoing an Action

Made a mistake? You can recover images:
1. Go to the **Approved** or **Disapproved** tab
2. Select the image(s)
3. Click **Undo** — they return to **Pending**

### 4.6 Downloading Images

- **Single image:** Open the image detail → click **Download**
- **Batch download:** Select multiple images → click **Download as ZIP**

> **Notice:** Downloads are full-resolution originals, not the thumbnails you see in the grid.

### 4.7 Adjusting the Grid

Use the **grid size slider** (top right) to control how many columns appear. Larger grid = smaller thumbnails, more images visible. Smaller grid = bigger thumbnails, easier to judge quality.

---

## 5. Video — Create Videos

The Video page has four sub-sections. You typically use them in this order.

### 5.1 Create Video

Generate short AI videos from your images.

1. Select reference images from your processed library
2. Either write a prompt manually **or** click **Generate Storyboard** (AI writes prompts for you based on the images)
3. Set video options:
   - **Duration** — how long each clip should be (e.g., 5 seconds)
   - **Aspect Ratio** — 16:9 for landscape, 9:16 for portrait/mobile
   - **Model** — higher quality = slower and more expensive
4. Click **Generate** or **Generate Batch** for multiple clips
5. Watch the job list for status updates

> **Notice:** Video generation is slower than image processing — typically several minutes per clip. Queue multiple jobs and let them run.

### 5.2 Video Constructor

Once your clips are ready, use the constructor to build a compilation:

1. Browse the **Video Library** (all generated clips)
2. Click clips to add them to the **Timeline**
3. Reorder clips by dragging them
4. Click **Merge** — the system stitches them into one video file
5. Download the final video

### 5.3 Video Gallery

Browse and play all generated videos. Download any individual clip from here.

### 5.4 Song Producer

Use this to prep audio for video projects:

1. Upload an audio/music file
2. Set trim points (start/end time) to extract just the section you need
3. Click **Analyze Music** — the AI notes key moments (beat drops, transitions)
4. Use the analysis to time your video prompts

> **Notice:** The audio analysis is a creative aid, not a final cut tool. It gives you suggestions — you still decide how to use them.

---

## 6. Prompts — Manage Personas

Personas are character/style profiles that define how the AI interprets your images. This section is mostly for advanced users or team leads, but here's what you need to know.

### 6.1 Templates Tab

Each persona has a set of AI instruction templates that control how it behaves. Unless your team lead tells you to edit these, **leave them as-is**.

### 6.2 Personas & Types Tab

Here you can:
- See all available personas and their types
- Create a new persona type
- Assign a persona to a type
- Edit persona metadata (hair color, hairstyles, etc.)

> **Notice:** Changing a persona's settings affects all future processing jobs that use that persona. Only edit these if you're sure of what you're doing. When in doubt, ask your team lead.

---

## 7. Monitor — System Health

The Monitor page shows real-time system stats. You don't need to do anything here — it auto-refreshes.

| Metric | What It Means |
|--------|---------------|
| **CPU %** | How hard the server is working right now |
| **RAM** | How much memory is in use |
| **Disk** | How much storage space remains |
| **Image Stats** | How many images are pending / completed / failed |
| **Video Stats** | Same but for video jobs |

> **Notice:** If the CPU is at 100% for a long time, the system may be overloaded. Your jobs will still run — they may just be slower. Alert your team lead if things seem stuck.

---

## 8. Archive — Browse Past Work

The Archive is a **read-only** view of historical outputs from all servers/locations.

- Use the **server filter** to narrow down by source
- Browse paginated image grids
- You cannot approve, disapprove, rename, or download from here

> **Notice:** The Archive is for reference only. If you need to reuse an image, locate the original file in your `results/` folder.

---

## 9. Common Workflows

### Workflow A: Generate & Curate a Photo Batch

> Use case: You have 10 reference photos and want 3 AI variations of each to pick the best ones.

1. **Workspace** → Upload your 10 photos
2. Set: Persona = your project persona, Variations = 3, Workflow = turbo
3. Select all 10 images → click **Process Batch**
4. While jobs run, optionally go to **Gallery** to approve earlier results
5. Once all 30 results are in Gallery → Pending tab, review each one
6. Approve the best variation of each reference, disapprove the rest
7. Go to Approved tab → select all → **Download as ZIP**

---

### Workflow B: Create a Short Video Compilation

> Use case: You want a 30-second video made of 6 × 5-second AI clips.

1. **Workspace** → Process 6 reference images (turbo, any variations count)
2. **Gallery** → Approve the best result from each reference
3. **Video → Create Video** → select the 6 approved images
4. Click **Generate Storyboard** → review/edit the AI-written prompts
5. Set Duration = 5s, Aspect = 16:9 → click **Generate Batch**
6. Wait for all 6 clips to finish (check job list)
7. **Video → Video Constructor** → add all 6 clips to timeline
8. Arrange the order you want → click **Merge**
9. Download the final video

---

### Workflow C: Review a Day's Output

> Use case: The overnight batch job finished and you need to curate the results.

1. **Gallery** → Pending tab
2. Click the **ⓘ** icon on each image to compare with its reference
3. For clear rejects, click ✗ immediately
4. For close calls, open full preview to judge quality
5. Batch-approve your best selections
6. Go to Approved tab → filter by today → **Download ZIP**
7. Optionally write notes using the daily notes field

---

## 10. Tips & Notices

### Do's

- **Save presets** for configurations you use often — it takes 10 seconds and saves time every session.
- **Use turbo workflow** when testing new settings. Switch to standard only for final output.
- **Start with 3 variations** per image. You can always re-process if none of them work.
- **Undo is always available** — don't stress about mis-approving. Just go to the Approved tab and undo.

### Don'ts

- **Don't refresh the page** while a batch is processing if you need to track exact job statuses — you can navigate within the app, just don't hard-reload.
- **Don't process hundreds of images at once** until you've confirmed your settings produce good results with a small test batch first.
- **Don't edit persona templates** unless you understand what you're changing — it affects everyone using that persona.

### Common Questions

**"I processed images but I don't see results in Gallery."**
Wait a moment — processing is async. Check the Active Tasks panel in Workspace. If a task shows "failed", alert your team lead.

**"The images in Gallery don't match what I expected from the reference."**
Check the persona and strength settings. A high strength (above 0.8) stays closer to reference. A low strength allows more creative freedom. Also verify the persona was correct.

**"I accidentally disapproved something I wanted."**
Go to Gallery → Disapproved tab → select the image → click **Undo**. It returns to Pending.

**"Processing seems stuck."**
Check the Monitor page. If CPU and RAM look normal but jobs aren't moving, ask your team lead — the Celery worker may need a restart.

**"I can't find an image I approved yesterday."**
Check Gallery → Approved tab. If it's not there, it may have been downloaded and the original is in `results/approved/` on the server. The Archive page may also have it if it was from a different run.

---

*Questions? Ask your team lead or check with the person who set up this system.*
