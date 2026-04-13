# Real Estate House Tour Video Analyzer

**Project**: ff-auto → New App: `realestate-video-analyzer`
**Goal**: Input a house tour video → AI agents analyze the visual content → Output a detailed prompt that can recreate the same property visuals
**Date**: April 13, 2026

---

## 1. Concept Overview

### What the existing app does (Image Pipeline)

```
Reference Image
  → VisionTool (GPT-4o/Grok/Gemini) extracts visual description
  → Analyst Agent structures the description into categories
  → Turbo Engineer converts structured analysis → generation prompt
  → ComfyUI generates a new image from that prompt
```

### What the new app does (Real Estate Video Pipeline)

```
House Tour Video (.mp4)
  → Frame Extraction (key frames sampled from video)
  → VisionTool analyzes each key frame for property details
  → Property Analyst Agent structures the spatial/architectural analysis
  → Scene Compositor Agent merges frame analyses into a coherent property profile
  → Prompt Engineer Agent converts the profile → generation prompt(s)
  → Output: prompt(s) that can recreate the property's visual identity
```

### Key Difference from the Image Pipeline

The image pipeline analyzes a **single static image** (outfit, pose, expression). The real estate pipeline must analyze a **temporal sequence of frames** from a walkthrough video, understanding that different frames show **different rooms/angles of the same property**. The agents must synthesize a unified understanding of the entire space, not just one frame.

---

## 2. Architecture Overview

### Data Flow

```
┌──────────────────────────────────────────────────────────────────────┐
│                        INPUT: House Tour Video                       │
└──────────────────┬───────────────────────────────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────────────────────────────┐
│  Step 1: Frame Extraction (Programmatic — no agent)                  │
│  - Extract key frames using scene-change detection (PySceneDetect)   │
│  - OR uniform sampling (1 frame every N seconds)                     │
│  - Output: 10–30 representative frames as .jpg files                 │
└──────────────────┬───────────────────────────────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────────────────────────────┐
│  Step 2: Per-Frame Vision Analysis (Programmatic — VisionTool)       │
│  - For each key frame: VisionTool._run(prompt, frame_path)           │
│  - Extracts: room type, materials, layout, lighting, style           │
│  - Output: List[str] — one analysis per frame                        │
└──────────────────┬───────────────────────────────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────────────────────────────┐
│  Step 3: CrewAI Agentic Workflow (3 agents, sequential)              │
│                                                                      │
│  Agent 1: Property Analyst                                           │
│    - Input: all per-frame analyses                                   │
│    - Task: Structure into a unified Property Visual Report           │
│    - Output: categorized property description                        │
│                                                                      │
│  Agent 2: Scene Compositor                                           │
│    - Input: Property Visual Report                                   │
│    - Task: Identify key scenes, resolve duplicates, create a         │
│            room-by-room walkthrough narrative                         │
│    - Output: coherent spatial narrative of the property               │
│                                                                      │
│  Agent 3: Prompt Engineer                                            │
│    - Input: spatial narrative + style constraints                     │
│    - Task: Generate image/video generation prompts                   │
│    - Output: List of prompts (one per room or one unified)           │
└──────────────────┬───────────────────────────────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────────────────────────────┐
│  OUTPUT: Generated prompt(s) for recreating the property visuals     │
│  - Per-room prompts (for image generation of each space)             │
│  - Unified property prompt (for video generation of the full tour)   │
│  - Style profile (reusable across similar properties)                │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 3. Project Structure (Mirroring ff-auto)

```
ff-auto/
├── backend/
│   ├── api/
│   │   ├── workspace.py              # (existing) image pipeline
│   │   ├── video.py                  # (existing) video generation
│   │   └── realestate.py             # ← NEW: real estate video analysis endpoints
│   │
│   ├── models/
│   │   ├── workspace.py              # (existing)
│   │   ├── video.py                  # (existing)
│   │   └── realestate.py             # ← NEW: request/response models
│   │
│   ├── services/
│   │   ├── image_processing.py       # (existing)
│   │   ├── video.py                  # (existing)
│   │   └── realestate.py             # ← NEW: orchestration service
│   │
│   ├── workflows/
│   │   ├── image_to_prompt_workflow.py           # (existing) — PATTERN TO FOLLOW
│   │   ├── video_storyboard_workflow.py          # (existing)
│   │   └── realestate_video_workflow.py          # ← NEW: CrewAI workflow
│   │
│   ├── tools/
│   │   ├── vision_tool.py            # (existing) — REUSE AS-IS
│   │   ├── audio_tool.py             # (existing)
│   │   └── video_frame_tool.py       # ← NEW: frame extraction tool
│   │
│   ├── tasks.py                      # ← ADD: new Celery tasks
│   │
│   ├── database/
│   │   ├── image_logs_storage.py     # (existing)
│   │   ├── video_logs_storage.py     # (existing)
│   │   └── realestate_logs_storage.py # ← NEW: analysis logs
│   │
│   ├── third_parties/                # (existing, reuse as-is)
│   ├── config.py                     # (existing, add new dirs)
│   └── utils/
│       ├── video_utils.py            # (existing, reuse frame extraction)
│       └── constants.py              # (existing, add RE constants)
│
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   │   └── realestate.ts         # ← NEW: API client
│   │   ├── hooks/
│   │   │   ├── useRealEstateAnalysis.ts  # ← NEW
│   │   │   └── usePropertyProfiles.ts    # ← NEW
│   │   ├── pages/
│   │   │   └── RealEstatePage.tsx     # ← NEW: main page
│   │   ├── components/
│   │   │   └── realestate/
│   │   │       ├── VideoUpload.tsx         # ← NEW
│   │   │       ├── FramePreview.tsx        # ← NEW
│   │   │       ├── AnalysisProgress.tsx    # ← NEW
│   │   │       ├── PropertyReport.tsx      # ← NEW
│   │   │       ├── PromptOutput.tsx        # ← NEW
│   │   │       └── AnalysisHistory.tsx     # ← NEW
│   │   └── types/
│   │       └── realestate.ts          # ← NEW: TypeScript interfaces
│   │
│   └── ...
│
├── prompts/
│   ├── templates/                     # (existing persona templates)
│   ├── workflows/                     # (existing video workflow prompts)
│   └── realestate/                    # ← NEW: all RE prompt templates
│       ├── property_analyst_agent.txt
│       ├── property_analyst_task.txt
│       ├── scene_compositor_agent.txt
│       ├── scene_compositor_task.txt
│       ├── prompt_engineer_agent.txt
│       ├── prompt_engineer_task.txt
│       ├── prompt_framework.txt
│       ├── prompt_constraints.txt
│       ├── prompt_examples.txt
│       └── vision_analysis_prompt.txt    # prompt sent to VisionTool per-frame
│
└── realestate_input/                  # ← NEW: input video directory
    └── (uploaded house tour .mp4 files)
```

---

## 4. CrewAI Workflow Design

### 4.1 Workflow Class: `RealEstateVideoWorkflow`

**File**: `backend/workflows/realestate_video_workflow.py`

**Mirrors**: `ImageToPromptWorkflow` (same caching, LLM init, template loading pattern)

```python
class RealEstateVideoWorkflow:
    """
    CrewAI Workflow to analyze a house tour video and generate
    prompts that can recreate the property's visual identity.
    """

    def __init__(self, verbose: bool = True):
        self.verbose = verbose
        self._cached_llms = {}
        self._cached_agents = {}

    def _get_llm(self, vision_model: str) -> Any:
        # Identical to ImageToPromptWorkflow._get_llm()
        # Supports: gpt-4o, grok-*, gemini-*

    def _create_property_analyst(self, llm: Any) -> Agent:
        # Loads backstory from prompts/realestate/property_analyst_agent.txt

    def _create_scene_compositor(self, llm: Any) -> Agent:
        # Loads backstory from prompts/realestate/scene_compositor_agent.txt

    def _create_prompt_engineer(self, llm: Any) -> Agent:
        # Loads backstory from prompts/realestate/prompt_engineer_agent.txt

    async def process(
        self,
        video_path: str,
        property_type: str = "residential",    # residential | commercial | luxury
        output_mode: str = "per_room",          # per_room | unified | both
        vision_model: str = "gpt-4o",
        max_frames: int = 20,
        variation_count: int = 1,
    ) -> Dict[str, Any]:
        """
        Full pipeline: video → frames → vision → agents → prompts.

        Returns:
            {
                "source_video": str,
                "property_type": str,
                "extracted_frames": List[str],       # paths to key frames
                "frame_analyses": List[str],          # raw vision output per frame
                "property_report": str,               # structured analysis
                "scene_narrative": str,               # spatial narrative
                "generated_prompts": List[Dict],      # [{room, prompt}]
                "unified_prompt": str,                # single combined prompt
                "style_profile": Dict,                # reusable style attributes
            }
        """
```

### 4.2 Process Method — Step by Step

Following the exact pattern from `ImageToPromptWorkflow.process()`:

```python
async def process(self, video_path, property_type, output_mode, vision_model, max_frames, variation_count):

    # ── Step 1: Frame Extraction (Programmatic, no agent) ──────────
    frame_tool = VideoFrameTool()
    frames = frame_tool.extract_key_frames(video_path, max_frames=max_frames)
    # frames = ["frame_001.jpg", "frame_002.jpg", ...]

    # ── Step 2: Per-Frame Vision Analysis (Programmatic) ───────────
    # Mirrors: ImageToPromptWorkflow lines 229-256
    # Uses VisionTool directly, NOT as a CrewAI tool
    vision_tool = VisionTool(model_name=vision_model)

    vision_prompt = _load_template("prompts/realestate/vision_analysis_prompt.txt")

    frame_analyses = []
    for frame_path in frames:
        analysis = vision_tool._run(prompt=vision_prompt, image_path=frame_path)
        # Check for refusal/error (same pattern as image workflow)
        _check_vision_refusal(analysis)
        frame_analyses.append(analysis)

    combined_analysis = "\n\n---\n\n".join(
        f"### Frame {i+1} ({Path(f).name})\n{a}"
        for i, (f, a) in enumerate(zip(frames, frame_analyses))
    )

    # ── Step 3: CrewAI Agent Pipeline ──────────────────────────────
    llm = self._get_llm(vision_model)

    # Agent 1: Property Analyst
    analyst = self._create_property_analyst(llm)
    analyst_task_template = _load_template("prompts/realestate/property_analyst_task.txt")
    analyst_task_desc = analyst_task_template.format(
        property_type=property_type,
        frame_count=len(frames)
    )

    analyze_task = Task(
        description=f"{analyst_task_desc}\n\n{combined_analysis}",
        expected_output="Structured Property Visual Report with categorized findings.",
        agent=analyst
    )

    # Agent 2: Scene Compositor
    compositor = self._create_scene_compositor(llm)
    compositor_task_template = _load_template("prompts/realestate/scene_compositor_task.txt")

    compose_task = Task(
        description=compositor_task_template,
        expected_output="Room-by-room spatial narrative of the property.",
        agent=compositor,
        context=[analyze_task]
    )

    # Agent 3: Prompt Engineer (mirrors Turbo Engineer pattern)
    engineer = self._create_prompt_engineer(llm)

    prompt_framework = _load_template("prompts/realestate/prompt_framework.txt")
    prompt_constraints = _load_template("prompts/realestate/prompt_constraints.txt")
    prompt_examples = _load_template("prompts/realestate/prompt_examples.txt")

    engineer_task_desc = (
        prompt_framework + "\n" +
        prompt_constraints + "\n" +
        prompt_examples
    ).format(
        property_type=property_type,
        output_mode=output_mode,
        variation_count=variation_count
    )

    prompt_tasks = []
    for i in range(variation_count):
        task = Task(
            description=engineer_task_desc,
            expected_output=f"Property generation prompt(s) (Variation {i+1})",
            agent=engineer,
            context=[analyze_task, compose_task]
        )
        prompt_tasks.append(task)

    # ── Run Crew (Sequential, same as image workflow) ──────────────
    all_tasks = [analyze_task, compose_task] + prompt_tasks
    crew = Crew(
        agents=[analyst, compositor, engineer],
        tasks=all_tasks,
        process=Process.sequential,
        memory=False,
        verbose=self.verbose
    )
    crew.kickoff()

    # ── Collect Results ────────────────────────────────────────────
    property_report = analyze_task.output.raw if analyze_task.output else ""
    scene_narrative = compose_task.output.raw if compose_task.output else ""

    generated_prompts = []
    for task in prompt_tasks:
        generated_prompts.append(task.output.raw if task.output else "")

    return {
        "source_video": video_path,
        "property_type": property_type,
        "extracted_frames": frames,
        "frame_analyses": frame_analyses,
        "property_report": property_report,
        "scene_narrative": scene_narrative,
        "generated_prompts": generated_prompts,
        "unified_prompt": generated_prompts[0] if generated_prompts else "",
        "style_profile": _extract_style_profile(property_report),
    }
```

### 4.3 Agent Definitions

#### Agent 1: Property Visual Analyst

**Role**: Lead Property Visual Analyst
**Goal**: Review and structure multi-frame visual analyses of a property into a unified architectural report.

**Template file**: `prompts/realestate/property_analyst_agent.txt`

```
You are an expert architectural photographer and interior design analyst.
You specialize in reading multiple frames from a single property walkthrough
and consolidating them into a structured, objective visual report.

YOUR STRENGTHS:
1. You can identify which frames show the same room from different angles
   vs. different rooms entirely.
2. You understand architectural vocabulary (wainscoting, crown molding,
   coffered ceiling, open-plan layout, etc.).
3. You recognize materials precisely (Carrara marble vs. quartz composite,
   engineered hardwood vs. solid oak, etc.).
4. You assess spatial relationships (room adjacency, sightlines, traffic flow).
5. You are objective. You describe what IS, not what you feel.

YOUR LIMITATIONS:
- You do NOT estimate square footage or property value.
- You do NOT make subjective judgments ("beautiful", "stunning").
- You focus purely on visual/material facts.
```

**Task file**: `prompts/realestate/property_analyst_task.txt`

```
You are analyzing a {property_type} property based on {frame_count} key frames
extracted from a house tour video.

Consolidate the per-frame vision analyses below into a STRUCTURED PROPERTY
VISUAL REPORT with the following categories:

### CATEGORY A: PROPERTY OVERVIEW & LAYOUT
- Property type (house, apartment, condo, townhouse)
- Estimated number of distinct rooms visible
- Layout style (open-plan, traditional separated, loft, split-level)
- Architectural era/style (modern, mid-century, Victorian, contemporary, etc.)

### CATEGORY B: ROOM-BY-ROOM INVENTORY
For each distinct room identified:
- Room type (living room, kitchen, master bedroom, bathroom, etc.)
- Which frames show this room (by frame number)
- Dimensions impression (spacious, compact, narrow, double-height)
- Key features (fireplace, island counter, bay window, walk-in closet)

### CATEGORY C: MATERIALS & FINISHES
- Flooring: type and material per room (hardwood, tile, carpet, concrete)
- Walls: paint color, texture, accent walls, wallpaper
- Countertops & surfaces: material (granite, quartz, butcher block)
- Cabinetry: style (shaker, flat-panel, glass-front), finish, hardware
- Fixtures: faucet style, light fixtures, door handles

### CATEGORY D: LIGHTING & ATMOSPHERE
- Natural light: window count/size, orientation impression, time of day
- Artificial lighting: fixture types (recessed, pendant, chandelier, sconce)
- Color temperature: warm, cool, neutral
- Overall mood: bright and airy, dark and moody, industrial, cozy

### CATEGORY E: ARCHITECTURAL DETAILS & STYLE
- Ceiling: height impression, type (flat, vaulted, beamed, coffered)
- Molding & trim: crown molding, baseboards, chair rail
- Windows: style (casement, double-hung, floor-to-ceiling)
- Doors: style and material
- Outdoor views: if visible through windows (garden, city, water, etc.)

### CATEGORY F: STAGING & DECOR (if furnished)
- Furniture style (modern, traditional, Scandinavian, bohemian)
- Color palette of furnishings
- Art and decorative objects
- Plants and greenery
- Textiles (rugs, curtains, throw pillows)

### OUTPUT INSTRUCTION
- Present findings under each Category header with bulleted lists.
- Cite specific frame numbers when referencing visual evidence.
- If a room appears in multiple frames, consolidate — do not duplicate.
- Be PRECISE about materials and finishes. "Dark wood floor" is insufficient.
  Say "Wide-plank espresso-stained engineered hardwood."
```

#### Agent 2: Scene Compositor

**Role**: Property Scene Compositor
**Goal**: Synthesize the structured property report into a coherent room-by-room spatial narrative.

**Template file**: `prompts/realestate/scene_compositor_agent.txt`

```
You are an architectural storyteller and spatial narrative expert.

You take structured property analysis reports and transform them into
flowing, coherent descriptions that read like a high-end real estate
walkthrough — but written for an AI image/video generation system,
not for a human buyer.

YOUR APPROACH:
1. SPATIAL FLOW: Organize rooms in a logical walkthrough order
   (entry → living spaces → kitchen → bedrooms → bathrooms → outdoor).
2. DEDUPLICATION: If the analyst mentions the same room multiple times
   from different frames, merge them into one cohesive description.
3. TRANSITIONS: Note how rooms connect (doorway, open archway,
   hallway, staircase).
4. CONSISTENCY: Maintain a consistent description style across all rooms.
5. COMPLETENESS: Every room from the analyst report must appear in your
   narrative. Do not drop rooms.

YOUR OUTPUT STYLE:
- Write in descriptive paragraphs, not bullet points.
- Each room gets its own paragraph.
- Include material/finish details inline with the spatial description.
- Mention lighting conditions as they relate to each room's atmosphere.
```

**Task file**: `prompts/realestate/scene_compositor_task.txt`

```
Based on the Property Visual Report from the analyst, create a SPATIAL
NARRATIVE of the property.

Your output must:

1. ORDER rooms in a natural walkthrough sequence (entry → main living
   areas → kitchen/dining → bedrooms → bathrooms → special rooms → outdoor).

2. For EACH room, write a single cohesive paragraph that covers:
   - Spatial dimensions and feel
   - Key architectural features
   - Materials and finishes (flooring, walls, surfaces)
   - Lighting conditions
   - Furniture/staging if visible
   - Connection to adjacent rooms

3. END with a brief "Style Summary" paragraph that captures:
   - The property's overall design language
   - Dominant color palette
   - Material theme (e.g., "warm wood + white stone + matte black hardware")
   - Lighting character (e.g., "abundant natural light from oversized windows")

OUTPUT FORMAT:
---
**[Room Name]**
[Descriptive paragraph]

**[Room Name]**
[Descriptive paragraph]

...

**Style Summary**
[Summary paragraph]
---
```

#### Agent 3: Property Prompt Engineer

**Role**: Property Visual Prompt Engineer
**Goal**: Convert spatial narratives into precise image/video generation prompts.

**Template file**: `prompts/realestate/prompt_engineer_agent.txt`

```
You are an expert prompt engineer specializing in architectural and
interior design image generation.

You understand how AI image generation models (Stable Diffusion, FLUX,
Midjourney, DALL-E, Kling) interpret prompts, and you write prompts
that maximize visual fidelity for architectural subjects.

YOUR EXPERTISE:
1. You know which keywords trigger photorealistic architectural renders.
2. You understand camera terminology for interior photography
   (wide-angle, tilt-shift, HDR bracketing, twilight exterior).
3. You emphasize MATERIAL SPECIFICITY over vague descriptors.
4. You include lighting direction and quality in every prompt.
5. You balance detail density with prompt length limits.

YOUR RULES:
- Write in flowing descriptive prose, not keyword lists.
- Every prompt must start with the camera/shot context.
- Every prompt must end with technical quality keywords.
- Prompt length: 600–1000 characters per room.
- Never use subjective adjectives ("beautiful", "stunning", "gorgeous").
  Use material/physical descriptors instead.
```

### 4.4 Prompt Template Files

#### `prompts/realestate/prompt_framework.txt`

```
## TASK DESCRIPTION
Your task is to convert the Scene Compositor's spatial narrative into
generation-ready prompts for a {property_type} property.

Output mode: {output_mode}
- "per_room": One prompt per room identified in the narrative.
- "unified": One prompt capturing the overall property aesthetic.
- "both": Both per-room and unified prompts.

### PROMPT STRUCTURE (per room)
Assemble each room prompt in this linear order:

**[Slot 1: Camera & Shot Type]**
Interior photography shot type and lens.
(e.g., "Wide-angle interior photograph, 16mm lens, eye-level perspective,
 looking into a spacious open-plan living room...")

**[Slot 2: Spatial Context & Layout]**
Room dimensions feel, ceiling height, layout.
(e.g., "...double-height ceiling with exposed white-painted wooden beams,
 open floor plan flowing into dining area...")

**[Slot 3: Materials & Surfaces]**
Flooring, walls, key surfaces — be maximally specific.
(e.g., "...wide-plank white oak hardwood flooring, smooth matte white walls,
 floor-to-ceiling Carrara marble fireplace surround...")

**[Slot 4: Fixtures & Details]**
Lighting fixtures, hardware, architectural details.
(e.g., "...brass sputnik chandelier, matte black steel-framed windows,
 minimalist recessed LED downlights along the perimeter...")

**[Slot 5: Furniture & Staging]**
Key furniture pieces and decor.
(e.g., "...low-profile cream boucle sectional sofa, walnut live-edge
 coffee table, woven jute area rug, potted fiddle-leaf fig...")

**[Slot 6: Lighting & Atmosphere]**
Natural and artificial light description.
(e.g., "...soft afternoon sunlight streaming through west-facing windows,
 warm 3000K ambient glow from recessed lights, gentle shadows...")

**[Slot 7: Technical Quality Tags]**
(e.g., "...professional architectural photography, HDR, sharp detail,
 color-accurate, Architectural Digest quality, 8K resolution.")
```

#### `prompts/realestate/prompt_constraints.txt`

```
### CONSTRAINTS — CRITICAL RULES

1. **NO subjective adjectives**: Never use "beautiful", "stunning",
   "gorgeous", "amazing", "perfect". Use physical descriptors only.

2. **MATERIAL PRECISION**: "Dark floor" is WRONG. "Espresso-stained
   wide-plank engineered European oak flooring" is CORRECT.

3. **CAMERA CONSISTENCY**: Every prompt must specify a real camera
   perspective (wide-angle, standard, telephoto) and height
   (eye-level, low-angle, elevated).

4. **LIGHTING IS MANDATORY**: Every prompt must describe light source,
   direction, quality, and color temperature.

5. **NO PEOPLE**: Unless the source video clearly features people as
   part of the staging, do not add humans to prompts.

6. **PROMPT LENGTH**: Each room prompt: 600–1000 characters.
   Unified prompt: 1000–1500 characters.

7. **REALISM ANCHOR**: End every prompt with photorealism keywords.
   Never drift into illustration, painting, or fantasy aesthetics.

8. **CONSISTENCY**: All room prompts for the same property must share
   the same color temperature, photography style, and quality level.
```

#### `prompts/realestate/prompt_examples.txt`

```
### EXAMPLE OUTPUT

**Living Room:**
Wide-angle interior photograph, 14mm rectilinear lens, eye-level
perspective looking into a spacious double-height living room with
exposed whitewashed timber ceiling beams. Wide-plank natural white oak
hardwood flooring with a subtle matte finish. Smooth warm-white walls
with minimal trim. A floor-to-ceiling linear gas fireplace set into a
honed Carrara marble surround flanked by built-in walnut shelving.
Low-profile oatmeal linen sectional sofa facing the fireplace, a
round travertine coffee table on a cream wool area rug. Oversized
black steel-framed windows along the south wall flooding the room
with soft midday diffused sunlight. A brass arc floor lamp in the
corner. Recessed LED downlights at 3000K along the ceiling perimeter.
Professional architectural photography, HDR, sharp throughout,
Architectural Digest editorial quality, color-accurate, 8K.

**Kitchen:**
Standard interior photograph, 24mm lens, eye-level, centered on a
large waterfall-edge kitchen island with book-matched Calacatta Oro
marble. Flat-panel matte navy cabinetry with brushed brass knob
hardware. White subway tile backsplash with dark grout lines.
Integrated stainless-steel appliances. Three clear glass globe pendant
lights hanging above the island on thin black cords. Engineered
herringbone oak flooring transitioning from the adjacent living area.
Morning light entering from a large casement window above the sink,
casting soft directional shadows across the countertop. Professional
interior photography, HDR, tack-sharp, natural color grading.
```

#### `prompts/realestate/vision_analysis_prompt.txt`

This is the prompt sent to VisionTool for each extracted key frame:

```
Analyze this frame from a real estate house tour video. Describe
EXACTLY what you see with architectural and interior design precision.

Cover these aspects:

1. ROOM IDENTIFICATION: What type of room is this? (living room,
   kitchen, bedroom, bathroom, hallway, exterior, etc.)

2. SPATIAL PROPERTIES: Approximate room size impression (spacious,
   compact, narrow), ceiling height (standard, high, double-height,
   vaulted), and layout notes.

3. MATERIALS & FINISHES:
   - Flooring: exact material and color (e.g., "light gray porcelain
     tile in large format 24x48")
   - Walls: paint color, texture, any accent treatment
   - Countertops/surfaces: material identification
   - Cabinetry: door style, finish, hardware

4. ARCHITECTURAL FEATURES: Windows (type, size), doors, molding,
   fireplace, built-ins, columns, staircases — anything structural.

5. FIXTURES: Light fixtures (type, material, count), faucets,
   handles, outlets visible.

6. FURNITURE & STAGING: Key furniture pieces, their material/color,
   arrangement. Decorative objects, plants, textiles.

7. LIGHTING CONDITIONS: Natural light direction and intensity,
   artificial lights that are on, overall brightness, shadows.

8. CAMERA ANGLE: What perspective is this frame shot from?
   (Eye-level, elevated, low, looking up/down, corner view, etc.)

OUTPUT: Structured text under each numbered heading. Be SPECIFIC
about materials — "wood floor" is insufficient, say
"medium-tone wire-brushed oak hardwood plank flooring."
Do not editorialize. Only describe what is physically visible.
```

---

## 5. New Tool: VideoFrameTool

**File**: `backend/tools/video_frame_tool.py`

Mirrors the pattern of `VisionTool` (inherits from `crewai.tools.BaseTool`), but its primary use is **programmatic** (called before the crew runs), not as an agent tool.

```python
class VideoFrameTool:
    """Extract representative key frames from a video file."""

    def extract_key_frames(
        self,
        video_path: str,
        max_frames: int = 20,
        method: str = "scene_detect",  # "scene_detect" | "uniform" | "hybrid"
        min_scene_duration: float = 2.0,
    ) -> List[str]:
        """
        Extract key frames and save them as numbered JPEGs.

        Methods:
        - scene_detect: Uses PySceneDetect ContentDetector for scene changes
        - uniform: Sample 1 frame every (duration / max_frames) seconds
        - hybrid: Scene detect first, then fill gaps with uniform samples

        Returns: List of file paths to extracted frame images.
        """

    def _scene_detect_frames(self, video_path, max_frames, min_scene_duration):
        """Use scenedetect library to find scene boundaries."""
        # pip install scenedetect[opencv]
        # from scenedetect import detect, ContentDetector

    def _uniform_sample_frames(self, video_path, max_frames):
        """Sample frames at uniform intervals using OpenCV."""
        # cv2.VideoCapture → seek to timestamps → save frames

    def _save_frame(self, frame_array, output_dir, frame_index) -> str:
        """Save a numpy frame array as JPEG, return path."""
```

**Dependencies**: `opencv-python`, `scenedetect` (optional, for smarter frame selection)

---

## 6. Backend: API Endpoints

**File**: `backend/api/realestate.py`

**Router prefix**: `/api/realestate`

```
POST   /api/realestate/analyze
       → Upload a video and start the full analysis pipeline
       → Body (multipart): video file + {property_type, output_mode,
         vision_model, max_frames, variation_count}
       → Returns: {task_id}

GET    /api/realestate/task/{task_id}/status
       → Poll Celery task state
       → Returns: {state, status_message, progress, result}

GET    /api/realestate/analyses
       → List recent analyses with pagination
       → Query: ?page=1&per_page=20
       → Returns: {items: [{id, video_filename, property_type, status,
                            created_at, prompt_count}], total, page, pages}

GET    /api/realestate/analyses/{analysis_id}
       → Get full analysis result
       → Returns: {source_video, property_type, extracted_frames,
                   property_report, scene_narrative, generated_prompts,
                   unified_prompt, style_profile}

GET    /api/realestate/analyses/{analysis_id}/frames
       → List extracted key frames for an analysis
       → Returns: [{frame_index, filename, thumbnail_url, room_type}]

GET    /api/realestate/analyses/{analysis_id}/frames/{frame_index}/thumbnail
       → Serve frame thumbnail

DELETE /api/realestate/analyses/{analysis_id}
       → Delete an analysis and its extracted frames

POST   /api/realestate/re-prompt
       → Re-run only the prompt generation step with different settings
       → Body: {analysis_id, output_mode, variation_count, property_type}
       → Returns: {task_id}
```

---

## 7. Backend: Pydantic Models

**File**: `backend/models/realestate.py`

```python
class AnalyzeVideoRequest(BaseModel):
    property_type: str = "residential"        # residential | commercial | luxury
    output_mode: str = "per_room"             # per_room | unified | both
    vision_model: str = "gpt-4o"
    max_frames: int = 20
    variation_count: int = 1

class AnalysisStatusResponse(BaseModel):
    task_id: str
    state: str                                # PENDING | EXTRACTING_FRAMES | ANALYZING_FRAMES
                                              # | RUNNING_AGENTS | SUCCESS | FAILURE
    status_message: str
    progress: int                             # 0-100
    result: Optional[Dict[str, Any]] = None

class FrameInfo(BaseModel):
    frame_index: int
    filename: str
    thumbnail_url: str
    room_type: Optional[str] = None

class RoomPrompt(BaseModel):
    room_name: str
    prompt: str
    frame_references: List[int]               # which frames show this room

class AnalysisResult(BaseModel):
    id: int
    source_video: str
    property_type: str
    extracted_frames: List[str]
    frame_analyses: List[str]
    property_report: str
    scene_narrative: str
    generated_prompts: List[RoomPrompt]
    unified_prompt: str
    style_profile: Dict[str, Any]
    created_at: str
    status: str

class AnalysisListItem(BaseModel):
    id: int
    video_filename: str
    property_type: str
    status: str
    created_at: str
    prompt_count: int

class AnalysisListResponse(BaseModel):
    items: List[AnalysisListItem]
    total: int
    page: int
    pages: int
```

---

## 8. Backend: Service Layer

**File**: `backend/services/realestate.py`

Mirrors `ImageProcessingService` pattern:

```python
class RealEstateService:
    def __init__(self):
        self.workflow = RealEstateVideoWorkflow(verbose=False)
        self.storage = RealEstateLogsStorage()
        self.frame_tool = VideoFrameTool()

    def dispatch_analysis(
        self, video_path: str, config: AnalyzeVideoRequest
    ) -> str:
        """Queue the analysis as a Celery task, return task_id."""
        task = analyze_property_video_task.delay(
            video_path=video_path,
            property_type=config.property_type,
            output_mode=config.output_mode,
            vision_model=config.vision_model,
            max_frames=config.max_frames,
            variation_count=config.variation_count,
        )
        return task.id

    def get_task_status(self, task_id: str) -> AnalysisStatusResponse:
        """Wrap AsyncResult into a clean response."""
        result = AsyncResult(task_id)
        # ... same pattern as ImageProcessingService.get_task_status()

    def list_analyses(self, page, per_page) -> AnalysisListResponse:
        """Paginated listing from database."""

    def get_analysis(self, analysis_id: int) -> AnalysisResult:
        """Full analysis result from database."""

    def get_frame_thumbnail(self, analysis_id, frame_index) -> bytes:
        """Serve frame thumbnail."""
```

---

## 9. Backend: Celery Task

**Added to**: `backend/tasks.py`

```python
@celery_app.task(bind=True, name="backend.tasks.analyze_property_video_task")
def analyze_property_video_task(
    self,
    video_path: str,
    property_type: str,
    output_mode: str,
    vision_model: str,
    max_frames: int,
    variation_count: int,
):
    """Celery task to run the full real estate video analysis pipeline."""
    try:
        self.update_state(
            state="EXTRACTING_FRAMES",
            meta={"status": "Extracting key frames from video...", "progress": 10}
        )

        result = asyncio.run(
            workflow.process(
                video_path=video_path,
                property_type=property_type,
                output_mode=output_mode,
                vision_model=vision_model,
                max_frames=max_frames,
                variation_count=variation_count,
            )
        )

        # Custom state updates happen inside workflow.process() via callback
        # ANALYZING_FRAMES (20-60%), RUNNING_AGENTS (60-90%), SUCCESS (100%)

        storage.log_analysis(result)

        self.update_state(
            state="SUCCESS",
            meta={"status": "Analysis complete", "progress": 100}
        )

        return result

    except Exception as e:
        logger.error(f"Error in analyze_property_video_task: {e}")
        raise e
```

**Task States**:

| State | Progress | Description |
|-------|----------|-------------|
| PENDING | 0% | Task queued |
| EXTRACTING_FRAMES | 10% | Running scene detection / frame sampling |
| ANALYZING_FRAMES | 20–60% | VisionTool processing each frame (progress updates per frame) |
| RUNNING_AGENTS | 60–90% | CrewAI agents analyzing and generating prompts |
| SUCCESS | 100% | Complete |
| FAILURE | — | Error occurred |

---

## 10. Backend: Database

**File**: `backend/database/realestate_logs_storage.py`

Mirrors `ImageLogsStorage` pattern (SQLite, same CRUD style):

```sql
CREATE TABLE IF NOT EXISTS realestate_analyses (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    video_filename  TEXT NOT NULL,
    video_path      TEXT NOT NULL,
    property_type   TEXT DEFAULT 'residential',
    output_mode     TEXT DEFAULT 'per_room',
    vision_model    TEXT DEFAULT 'gpt-4o',
    frame_count     INTEGER DEFAULT 0,
    property_report TEXT,
    scene_narrative TEXT,
    unified_prompt  TEXT,
    style_profile   TEXT,                -- JSON string
    status          TEXT DEFAULT 'pending',   -- pending | processing | completed | failed
    error_message   TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS realestate_frames (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    analysis_id     INTEGER NOT NULL,
    frame_index     INTEGER NOT NULL,
    frame_path      TEXT NOT NULL,
    room_type       TEXT,
    vision_analysis TEXT,                -- raw VisionTool output
    FOREIGN KEY (analysis_id) REFERENCES realestate_analyses(id)
);

CREATE TABLE IF NOT EXISTS realestate_prompts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    analysis_id     INTEGER NOT NULL,
    room_name       TEXT,
    prompt          TEXT NOT NULL,
    variation_index INTEGER DEFAULT 1,
    frame_references TEXT,               -- JSON array of frame indices
    FOREIGN KEY (analysis_id) REFERENCES realestate_analyses(id)
);
```

---

## 11. Frontend: React Components

**Page**: `RealEstatePage.tsx`

```
┌──────────────────────────────────────────────────────────┐
│  Real Estate Video Analyzer                              │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  ┌─────────────────┐  ┌──────────────────────────────┐  │
│  │  Video Upload    │  │  Configuration               │  │
│  │  ┌───────────┐  │  │  Property Type: [Residential]│  │
│  │  │  Drop     │  │  │  Output Mode:  [Per Room  ▼]│  │
│  │  │  video    │  │  │  Vision Model: [GPT-4o    ▼]│  │
│  │  │  here     │  │  │  Max Frames:   [20        ] │  │
│  │  └───────────┘  │  │  Variations:   [1         ] │  │
│  │  video.mp4      │  │                              │  │
│  └─────────────────┘  │  [▶ Analyze Property]        │  │
│                        └──────────────────────────────┘  │
│                                                          │
│  ┌──────────────────────────────────────────────────────┐│
│  │  Analysis Progress                                    ││
│  │  ████████████████████░░░░░  72%                       ││
│  │  "Analyzing frame 15/20..."                           ││
│  └──────────────────────────────────────────────────────┘│
│                                                          │
│  ┌──────────────────────────────────────────────────────┐│
│  │  Extracted Frames                                     ││
│  │  [img1] [img2] [img3] [img4] [img5] [img6] ...      ││
│  │  Living  Kitchen  Bed   Bath   Entry  Patio          ││
│  └──────────────────────────────────────────────────────┘│
│                                                          │
│  ┌──────────────────────────────────────────────────────┐│
│  │  Property Report  │  Scene Narrative  │  Prompts     ││
│  │  ─────────────────────────────────────────────────── ││
│  │  [Tab content: structured report / narrative / list  ││
│  │   of generated prompts with copy buttons]            ││
│  └──────────────────────────────────────────────────────┘│
│                                                          │
│  ┌──────────────────────────────────────────────────────┐│
│  │  Analysis History                                     ││
│  │  ┌────────────┬──────────┬────────┬─────────────┐   ││
│  │  │ Video      │ Type     │ Status │ Date        │   ││
│  │  ├────────────┼──────────┼────────┼─────────────┤   ││
│  │  │ tour_01.mp4│ Luxury   │ ✅     │ Apr 13      │   ││
│  │  │ unit_5B.mp4│ Resid.   │ ✅     │ Apr 12      │   ││
│  │  └────────────┴──────────┴────────┴─────────────┘   ││
│  └──────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────┘
```

### Component Breakdown

| Component | Purpose |
|-----------|---------|
| `VideoUpload.tsx` | Drag-and-drop video upload, preview thumbnail |
| `FramePreview.tsx` | Horizontal scrollable grid of extracted frames |
| `AnalysisProgress.tsx` | Real-time progress bar with status messages (polls task status) |
| `PropertyReport.tsx` | Tabbed view: Report / Narrative / Raw Frame Analyses |
| `PromptOutput.tsx` | List of generated prompts with per-prompt copy button |
| `AnalysisHistory.tsx` | Paginated table of past analyses |

### TypeScript Types

**File**: `frontend/src/types/realestate.ts`

```typescript
interface AnalyzeVideoRequest {
  property_type: "residential" | "commercial" | "luxury";
  output_mode: "per_room" | "unified" | "both";
  vision_model: string;
  max_frames: number;
  variation_count: number;
}

interface AnalysisStatus {
  task_id: string;
  state: string;
  status_message: string;
  progress: number;
  result?: AnalysisResult;
}

interface FrameInfo {
  frame_index: number;
  filename: string;
  thumbnail_url: string;
  room_type?: string;
}

interface RoomPrompt {
  room_name: string;
  prompt: string;
  frame_references: number[];
}

interface AnalysisResult {
  id: number;
  source_video: string;
  property_type: string;
  extracted_frames: string[];
  frame_analyses: string[];
  property_report: string;
  scene_narrative: string;
  generated_prompts: RoomPrompt[];
  unified_prompt: string;
  style_profile: Record<string, any>;
  created_at: string;
}

interface AnalysisListItem {
  id: number;
  video_filename: string;
  property_type: string;
  status: string;
  created_at: string;
  prompt_count: number;
}
```

### API Client

**File**: `frontend/src/api/realestate.ts`

```typescript
export const realestateApi = {
  analyze: (file: File, config: AnalyzeVideoRequest) => {
    const formData = new FormData();
    formData.append("video", file);
    Object.entries(config).forEach(([k, v]) => formData.append(k, String(v)));
    return client.post<{ task_id: string }>("/api/realestate/analyze", formData);
  },

  getTaskStatus: (taskId: string) =>
    client.get<AnalysisStatus>(`/api/realestate/task/${taskId}/status`),

  listAnalyses: (page = 1, perPage = 20) =>
    client.get<AnalysisListResponse>(`/api/realestate/analyses`, {
      params: { page, per_page: perPage },
    }),

  getAnalysis: (id: number) =>
    client.get<AnalysisResult>(`/api/realestate/analyses/${id}`),

  getFrames: (id: number) =>
    client.get<FrameInfo[]>(`/api/realestate/analyses/${id}/frames`),

  deleteAnalysis: (id: number) =>
    client.delete(`/api/realestate/analyses/${id}`),

  rePrompt: (analysisId: number, config: Partial<AnalyzeVideoRequest>) =>
    client.post<{ task_id: string }>("/api/realestate/re-prompt", {
      analysis_id: analysisId,
      ...config,
    }),
};
```

### Custom Hook

**File**: `frontend/src/hooks/useRealEstateAnalysis.ts`

```typescript
// Mirrors useVideoGenerate.ts pattern
export function useRealEstateAnalysis() {
  const [taskId, setTaskId] = useState<string | null>(null);
  const [status, setStatus] = useState<AnalysisStatus | null>(null);

  const analyze = async (file: File, config: AnalyzeVideoRequest) => {
    const { data } = await realestateApi.analyze(file, config);
    setTaskId(data.task_id);
  };

  // Poll status while task is active
  useQuery(
    ["realestate-status", taskId],
    () => realestateApi.getTaskStatus(taskId!),
    {
      enabled: !!taskId,
      refetchInterval: (data) =>
        data?.state === "SUCCESS" || data?.state === "FAILURE" ? false : 3000,
      onSuccess: (data) => setStatus(data),
    }
  );

  return { analyze, taskId, status };
}
```

---

## 12. Config & Environment Changes

### GlobalConfig additions (`backend/config.py`):

```python
# Real Estate
REALESTATE_INPUT_DIR = os.getenv("REALESTATE_INPUT_DIR", "/app/realestate_input")
REALESTATE_FRAMES_DIR = os.getenv("REALESTATE_FRAMES_DIR", "/app/realestate_frames")
REALESTATE_DB_PATH = os.getenv("REALESTATE_DB_PATH", "/app/realestate_logs.db")
```

### Docker Compose volume additions:

```yaml
services:
  backend:
    volumes:
      # ... existing volumes ...
      - ../realestate_input:/app/realestate_input
      - ../realestate_frames:/app/realestate_frames
      - ../realestate_logs.db:/app/realestate_logs.db
  worker:
    volumes:
      # ... same additions ...
```

### New Python dependencies (`requirements.txt`):

```
scenedetect[opencv]>=0.6
opencv-python-headless>=4.8
```

---

## 13. Execution Order

| Step | Task | Effort | Notes |
|------|------|--------|-------|
| 1 | Create `prompts/realestate/` directory with all 10 template files | 0.5 day | Start here — the prompts are the soul of the system |
| 2 | Build `VideoFrameTool` in `backend/tools/video_frame_tool.py` | 0.5 day | Test with a sample house tour video |
| 3 | Build `RealEstateVideoWorkflow` in `backend/workflows/` | 1 day | Follow `ImageToPromptWorkflow` pattern exactly |
| 4 | Build `RealEstateLogsStorage` in `backend/database/` | 0.5 day | 3 tables, standard CRUD |
| 5 | Build `RealEstateService` in `backend/services/` | 0.5 day | Thin orchestration layer |
| 6 | Add Celery task to `backend/tasks.py` | 0.5 day | Single task with progress updates |
| 7 | Build API routes in `backend/api/realestate.py` | 0.5 day | Register router in `main.py` |
| 8 | Add Pydantic models in `backend/models/realestate.py` | 0.5 day | |
| 9 | Build React page + components | 2 days | VideoUpload, FramePreview, PromptOutput |
| 10 | Integration test with a real house tour video | 0.5 day | End-to-end verification |
| **Total** | | **~7 days** | |

---

## 14. Pattern Mapping Reference

Quick reference showing how each ff-auto pattern maps to the new real estate app:

| ff-auto (Image Pipeline) | Real Estate (Video Pipeline) |
|--------------------------|------------------------------|
| `ImageToPromptWorkflow` | `RealEstateVideoWorkflow` |
| `VisionTool` on 1 image | `VisionTool` on N frames (loop) |
| `analyst_agent.txt` / `analyst_task.txt` | `property_analyst_agent.txt` / `property_analyst_task.txt` |
| `turbo_agent.txt` / `turbo_framework.txt` | `prompt_engineer_agent.txt` / `prompt_framework.txt` |
| 2 agents (Analyst → Turbo Engineer) | 3 agents (Analyst → Compositor → Engineer) |
| `Crew(sequential)` | `Crew(sequential)` |
| `process_image_task` (Celery) | `analyze_property_video_task` (Celery) |
| `ImageProcessingService` | `RealEstateService` |
| `POST /api/workspace/process` | `POST /api/realestate/analyze` |
| `ImageLogsStorage` (SQLite) | `RealEstateLogsStorage` (SQLite) |
| `WorkspacePage.tsx` | `RealEstatePage.tsx` |
| `useTaskProgress.ts` | `useRealEstateAnalysis.ts` |
| Persona config (hair, type) | Property config (type, output_mode) |
| `prompts/templates/{type}/` | `prompts/realestate/` |
| Input: single `.png`/`.jpg` | Input: `.mp4` video → extracted frames |
| Output: image generation prompt | Output: per-room + unified property prompts |
