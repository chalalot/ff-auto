import os
import asyncio
import logging
from pathlib import Path
from dotenv import load_dotenv
from typing import List, Optional, Dict, Any
from crewai import Agent, Task, Crew, Process

load_dotenv()

# Configure logger
logger = logging.getLogger(__name__)

from backend.tools.vision_tool import VisionTool
from backend.utils.constants import DEFAULT_NEGATIVE_PROMPT
from backend.workflows.config_manager import WorkflowConfigManager
from backend.config import GlobalConfig

class ImageToPromptWorkflow:
    """
    CrewAI Workflow to analyze an image and generate a specific prompt 
    for Instagirl WAN2.2, adapted for daily/casual style.
    """

    def __init__(self, verbose: bool = True):
        self.verbose = verbose
        self.config_manager = WorkflowConfigManager()
        # Cache to reuse agents and LLMs across invocations
        self._cached_llms = {}
        self._cached_agents = {}

    def _get_llm(self, vision_model: str) -> Any:
        if vision_model in self._cached_llms:
            return self._cached_llms[vision_model]
            
        if vision_model.lower().startswith("grok"):
            from crewai import LLM
            import litellm
            
            litellm.telemetry = False
            
            # Conditionally enable deep litellm debugging if workflow is verbose
            if self.verbose:
                litellm.set_verbose = True
                litellm.turn_off_message_logging = False
                litellm.suppress_debug_info = False
            else:
                litellm.turn_off_message_logging = True 
                litellm.suppress_debug_info = True
                
            litellm.success_callback = []
            litellm.failure_callback = []
            
            llm = LLM(
                model="openai/" + vision_model,
                base_url="https://api.x.ai/v1",
                api_key=GlobalConfig.GROK_API_KEY
            )
            logger.info(f"Initialized cached Grok LLM ({vision_model}) for Agents")
        elif vision_model.lower().startswith("gemini"):
            from crewai import LLM
            _GEMINI_ALIASES = {
                "gemini-1.5-pro": "gemini-1.5-pro-latest",
                "gemini-1.5-flash": "gemini-1.5-flash-latest",
                "gemini-1.0-pro": "gemini-1.5-pro-latest",
            }
            resolved = _GEMINI_ALIASES.get(vision_model, vision_model)
            if resolved != vision_model:
                logger.warning(f"Gemini model '{vision_model}' is deprecated, using '{resolved}'")
            llm = LLM(
                model="gemini/" + resolved,
                api_key=GlobalConfig.GEMINI_API_KEY
            )
            logger.info(f"Initialized cached Gemini LLM ({resolved}) for Agents")
        else:
            llm = vision_model
            logger.info(f"Initialized cached default LLM ({vision_model}) for Agents")
            
        self._cached_llms[vision_model] = llm
        return llm

    def _create_analyst(self, template_dir: str, llm: Any) -> Agent:
        # Load backstory from file in specific template directory
        backstory_path = os.path.join(template_dir, 'analyst_agent.txt')
        try:
            with open(backstory_path, 'r', encoding='utf-8') as f:
                backstory_content = f.read()
        except Exception as e:
            # Fallback if file missing
            backstory_content = """You are an expert visual director with an eye for detail.
            You can analyze an image and breakdown the:
            - Outfit (colors, textures, cuts)
            - Pose and body language
            - Camera Angle and Head Direction
            - Background and setting details (briefly)
            - Lighting setup (shadows, source)
            
            You focus on OBJECTIVE reality. You do not fluff or over-dramatize.
            """
            if self.verbose:
                logger.warning(f"Warning: Could not load analyst_agent.txt from {backstory_path}, using fallback. Error: {e}")

        return Agent(
            role='Lead Visual Analyst',
            goal='Review and structure the visual analysis of reference images.',
            backstory=backstory_content,
            tools=[], # No tools needed, receives analysis text
            verbose=self.verbose,
            allow_delegation=False,
            memory=False,
            llm=llm
        )

    def _create_engineer(self, llm: Any) -> Agent:
        # Engineer agent for WAN2.2 (Legacy) - potentially not used in Turbo workflow
        return Agent(
            role='Instagirl WAN2.2 Prompt Specialist',
            goal='Convert visual descriptions into strict Instagirl WAN2.2 keyword prompts.',
            backstory="""You are a specialist in prompting for the Instagirl WAN2.2 model.
            
            **YOUR STYLE GUIDE:**
            1. **Daily & Casual**: We are creating daily, casual images. DO NOT make them look "cinematic" or "professional studio".
            2. **Natural Realism**: 
               - AVOID "soft pores", "smooth skin", "glowy", "plastic".
               - Aim for natural skin texture.
            3. **High Detail**: You need to produce prompts around 700-800 characters. Describe the outfit, pose, textures, background, lighting, and atmosphere in great detail using keywords.
            4. **Formatting**:
               - Use comma-separated keywords ONLY.
               - No full sentences.
               - No bullet points.
            """,
            verbose=self.verbose,
            allow_delegation=False,
            memory=False,
            llm=llm
        )

    def _create_turbo_engineer(self, template_dir: str, llm: Any) -> Agent:
        # Load backstory from file in specific template directory
        backstory_path = os.path.join(template_dir, 'turbo_agent.txt')
        try:
            with open(backstory_path, 'r', encoding='utf-8') as f:
                backstory_content = f.read()
        except Exception as e:
            # Fallback
            backstory_content = """You are an expert visual storyteller and prompt engineer.
            
            **YOUR GOAL:**
            Translate visual analysis into rich, descriptive narrative prompts that follow a strict structure.
            
            **YOUR STYLE GUIDE:**
            1. **Descriptive Flow**: Write in fluid, natural sentences. Avoid broken keyword lists.
            2. **High Density**: Pack as much visual detail as possible into the narrative (textures, lighting, atmosphere).
            3. **Objective Realism**: Focus on physical reality (fabric weight, light direction), avoiding abstract metaphors.
            4. **Formatting**:
               - Use a single, cohesive paragraph.
               - Follow the structure requested in the task exactly.
            """
            if self.verbose:
                print(f"Warning: Could not load turbo_agent.txt from {backstory_path}, using fallback. Error: {e}")

        return Agent(
            role='Visual Narrative Prompt Expert',
            goal='Convert visual analysis into rich, descriptive narrative prompts.',
            backstory=backstory_content,
            verbose=self.verbose,
            allow_delegation=False,
            memory=False,
            llm=llm
        )

    async def process(self, image_path: str, persona_name: str = "Jennie", workflow_type: str = "turbo", vision_model: str = "gpt-4o", variation_count: int = 1, clip_model_type: str = "sd3") -> Dict[str, Any]:
        """
        Run the workflow for a single image.
        
        Args:
            image_path: Path to local image file.
            persona_name: Name of the persona (e.g. "Jennie").
            workflow_type: Type of workflow ("turbo").
            vision_model: The vision model to use ("gpt-4o" or "grok-4-1-fast-non-reasoning").
            variation_count: Number of prompt variations to generate (default: 1).
            
        Returns:
            A dictionary containing the reference image path and the generated prompt(s).
        """
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image not found at {image_path}")

        logger.info(f"📸 Starting Workflow for: {image_path} (Persona: {persona_name}, Workflow: {workflow_type})")
        
        # DEBUG: Verify image readability
        try:
            with open(image_path, "rb") as f:
                header = f.read(8)
                logger.info(f"[DEBUG] Successfully verified image readability at {image_path} (Header: {header})")
        except Exception as e:
            logger.error(f"[ERROR] Failed to read image at {image_path}: {e}")
            raise IOError(f"Cannot read image file: {e}")

        # Load Persona Config
        persona_config = self.config_manager.get_persona_config(persona_name)
        
        # Determine Persona Type and Template Directory
        persona_type = persona_config.get("type", "instagirl")
        
        # Get project root assuming structure src/workflows/this_file.py
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        prompts_base = os.path.join(project_root, 'prompts', 'templates')
        
        template_dir = os.path.join(prompts_base, persona_type)
        
        # Fallback to instagirl if type folder doesn't exist (though it should)
        if not os.path.exists(template_dir):
            if self.verbose:
                logger.warning(f"Warning: Template directory for type '{persona_type}' not found at {template_dir}. Falling back to 'instagirl'.")
            template_dir = os.path.join(prompts_base, 'instagirl')

        # --- PROGRAMMATIC VISION STEP ---
        # 1. Load Analyst Task (Prompt)
        analyst_task_path = os.path.join(template_dir, 'analyst_task.txt')
        try:
            with open(analyst_task_path, 'r', encoding='utf-8') as f:
                analyst_task_template = f.read()
        except Exception as e:
            # Fallback
            analyst_task_template = "Analyze the visual elements of this image in detail."
            if self.verbose:
                logger.warning(f"Warning: Could not load analyst_task.txt from {analyst_task_path}, using fallback. Error: {e}")

        # 2. Prepare Prompt (replace {image_path} with generic text or just keep prompt)
        # The prompt usually says "Analyze the reference image at: {image_path}"
        # We want to send the instructions to the Vision Model.
        # We can just format it, but the VisionTool doesn't need the path in the PROMPT if it has it in the arg.
        safe_image_path = Path(image_path).resolve().as_posix()
        vision_prompt = analyst_task_template.format(image_path=f'"{safe_image_path}"')

        # 3. Execute Vision Tool Programmatically
        logger.info(f"Executing Vision Analysis programmatically for {image_path} with model {vision_model}...")
        vision_tool_instance = VisionTool(model_name=vision_model)
        vision_result = vision_tool_instance._run(prompt=vision_prompt, image_path=image_path)

        # 4. Check for Failure/Moderation
        _REFUSAL_PHRASES = [
            "sorry, i cannot", "sorry i cannot", "i'm sorry", "i am sorry",
            "i cannot assist", "i can't assist", "i cannot help", "i can't help",
            "i'm unable", "i am unable", "i cannot analyze", "i can't analyze",
            "i'm not able", "i am not able", "i apologize, but",
            "unfortunately, i cannot", "unfortunately i cannot",
        ]
        if vision_result is None:
            raise ValueError("Vision model returned None (empty response)")
        vision_lower = vision_result.strip().lower()

        if not vision_lower:
            logger.error("❌ Vision Analysis Failed: empty response from vision model.")
            raise ValueError("Vision model returned an empty response.")

        if vision_result.startswith("Error"):
            logger.error(f"❌ Vision Analysis Failed (tool error): {vision_result}")
            raise ValueError(f"Vision model returned an error: {vision_result}")

        if any(phrase in vision_lower for phrase in _REFUSAL_PHRASES):
            logger.error(f"❌ Vision Analysis Failed: LLM refused to analyze the image.\nModel response: {vision_result}")
            raise ValueError(f"Vision model refused to analyze the image (content policy or moderation). Response: {vision_result[:300]}")

        logger.info(f"✅ Vision Analysis Successful.\n{'='*60}\n[VISION RESULT]\n{'='*60}\n{vision_result}\n{'='*60}")

        # --- CREW SETUP ---
        
        # Get cached LLM
        llm = self._get_llm(vision_model)

        # Initialize or get cached Agents
        analyst_key = f"analyst_{template_dir}_{vision_model}"
        if analyst_key not in self._cached_agents:
            self._cached_agents[analyst_key] = self._create_analyst(template_dir, llm)
        analyst = self._cached_agents[analyst_key]
        
        turbo_key = f"turbo_{template_dir}_{vision_model}"
        if turbo_key not in self._cached_agents:
            self._cached_agents[turbo_key] = self._create_turbo_engineer(template_dir, llm)
        turbo_engineer = self._cached_agents[turbo_key]
        
        engineer_key = f"engineer_{vision_model}"
        if engineer_key not in self._cached_agents:
            self._cached_agents[engineer_key] = self._create_engineer(llm)
        engineer = self._cached_agents[engineer_key]

        # Get Hairstyle Config
        available_hairstyles = persona_config.get("hairstyles", [])
        if not available_hairstyles:
             # Fallback defaults if config is empty
             available_hairstyles = ["long loose hair"] 

        # Generate Prompt(s)
        generate_prompt_tasks = []

        hair_color = persona_config.get("hair_color", "Honey-blonde")

        header = "  - You MUST choose ONE from this list explicitly (Do not invent others):"
        hairstyle_list = "\n".join([f"  - {style}" for style in available_hairstyles])
        hairstyle_options = f"{header}\n{hairstyle_list}"

        def _read_part(filename):
            path = os.path.join(template_dir, filename)
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return f.read()
            except Exception as e:
                raise FileNotFoundError(f"Could not load {filename} from {template_dir}: {e}")

        turbo_template = (
            _read_part('turbo_framework.txt') + "\n" +
            _read_part('turbo_constraints.txt') + "\n" +
            _read_part('turbo_example.txt')
        )

        base_instruction = turbo_template.format(hair_color=hair_color, hairstyle_options=hairstyle_options)

        for i in range(variation_count):
            task = Task(
                description=f"Based on this visual analysis of the reference image:\n\n{vision_result}\n\n{base_instruction}",
                expected_output=f"A detailed paragraph describing the image (Variation {i+1})",
                agent=turbo_engineer,
            )
            generate_prompt_tasks.append(task)

        crew = Crew(
            agents=[turbo_engineer],
            tasks=generate_prompt_tasks,
            process=Process.sequential,
            memory=False,
            verbose=self.verbose
        )

        crew.kickoff()

        # Collect generated prompts
        generated_prompts = []
        for task in generate_prompt_tasks:
            if task.output:
                logger.info(f"[TASK OUTPUT DEBUG] raw={repr(task.output.raw)}")
                logger.info(f"[TASK OUTPUT DEBUG] pydantic={task.output.pydantic}")
                logger.info(f"[TASK OUTPUT DEBUG] json_dict={task.output.json_dict}")
                logger.info(f"[TASK OUTPUT DEBUG] agent={task.output.agent}")
            generated_prompts.append(task.output.raw if task.output else "")

        logger.info(f"\n✅ Generated {len(generated_prompts)} Prompts.")

        first_prompt = generated_prompts[0] if generated_prompts else ""

        return {
            "reference_image": image_path,
            "generated_prompt": first_prompt,
            "generated_prompts": generated_prompts,
            "descriptive_prompt": vision_result,
        }

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True, help="Path to image")
    parser.add_argument("--persona", default="Jennie", help="Persona name")
    args = parser.parse_args()
    
    workflow = ImageToPromptWorkflow()
    asyncio.run(workflow.process(args.image, args.persona))
