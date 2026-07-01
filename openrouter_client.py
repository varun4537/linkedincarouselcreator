import os
import json
import httpx
from typing import List, Dict, Any, Optional

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

class OpenRouterClient:
    def __init__(self):
        self.api_key = os.getenv("OPENROUTER_API_KEY", "")
        # Fallback to empty key or load from a config file if needed
        self.default_headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:8000",
            "X-Title": "LinkedIn Carousel Creator"
        }

    def _get_headers(self) -> Dict[str, str]:
        if not self.api_key:
            # Re-read environment just in case it was set after instantiation
            self.api_key = os.getenv("OPENROUTER_API_KEY", "")
            self.default_headers["Authorization"] = f"Bearer {self.api_key}"
        return self.default_headers

    def load_humanizer_rules(self, base_dir: str) -> str:
        """Loads the content of the-humanizer-v2.5.md dynamically."""
        paths = [
            os.path.join(base_dir, "the-humanizer-v2.5.md"),
            os.path.join(base_dir, "the-humanizer.md"),
            "the-humanizer-v2.5.md"
        ]
        for p in paths:
            if os.path.exists(p):
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        return f.read()
                except Exception:
                    pass
        return "Apply strict professional copywriting rules: no generic templates, avoid marketing buzzwords, and use authentic human sentence structures."

    def load_voice_profile(self, base_dir: str) -> str:
        """Loads the brand voice profile from voice_profile.txt."""
        paths = [
            os.path.join(base_dir, "voice_profile.txt"),
            "voice_profile.txt"
        ]
        for p in paths:
            if os.path.exists(p):
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        return f.read()
                except Exception:
                    pass
        return "Calm, specific, metrics-driven, and focused on operational advice rather than high-level inspiration."

    async def generate_stage1_outline(
        self,
        model: str,
        topic: str,
        sources: List[str],
        urls: List[str],
        audience: str,
        angle: str,
        writer_draft: Optional[str],
        base_dir: str
    ) -> Dict[str, Any]:
        """
        Stage 1: Input brief -> Generates the facts ledger, slide outline, and initial humanizer flags.
        """
        humanizer_rules = self.load_humanizer_rules(base_dir)
        
        # Format sources with indices
        formatted_sources = ""
        for i, src in enumerate(sources):
            if src.strip():
                formatted_sources += f"--- SOURCE BLOCK {i+1} ---\n{src.strip()}\n\n"
        
        # Prepare system prompt
        system_prompt = f"""You are an elite research analyst and copywriter specializing in LinkedIn content.
Your goal is to digest the provided source material and create a highly structured, accurate, and human-sounding slide outline for a LinkedIn carousel post.

### STRICT RULES FOR FAITHFULNESS
1. You MUST NOT claim anything that is not directly supported by the source content.
2. Every item in the 'facts_ledger' must be a distinct claim mapped back to its specific source block (e.g. "Source 1", "Source 2", "Draft").
3. If two sources contradict each other or contradict the writer's draft, you MUST flag it inside the 'facts_ledger' explicitly as a contradiction.

### THE HUMANIZER PRINCIPLES
You must apply the following guidelines derived from the Content AI Humanizer protocol:
{humanizer_rules}

### OUTPUT FORMAT
You must respond with a JSON object containing exactly three fields:
1. "facts_ledger": List of claims with the following keys:
   - "id": string (e.g. "F1", "F2")
   - "claim": string (the facts extracted)
   - "source": string (attribution, e.g. "Source 1", "Source 2")
   - "conflict": boolean
   - "conflict_details": string or null
2. "outline": List of proposed slides (minimum 6, maximum 10) with the following keys:
   - "slide_number": integer
   - "job": string (must be one of: "Cover", "Definition", "Mechanics", "Nuance", "Stat", "Who benefits", "Action", "Closing")
   - "headline": string (max 12 words, bold, social-native)
   - "body": string (1-3 sentences max, clean, short. Aim for crisp rhythmic sentences)
   - "stat": string or null (specific numbers, metrics, percentage e.g. "91%", "50%" or short quotes. Essential for Stat slides)
3. "humanizer_flags": List of any phrases generated in your own initial thoughts/outline that violate the Humanizer rules, with keys:
   - "original_phrase": string
   - "reason": string
   - "suggested_rewrite": string

Return ONLY valid JSON. Do not include markdown code block formatting like ```json ... ``` or any pre/post text.
"""

        user_content = f"""
Topic / Working Title: {topic}
Audience: {audience}
Angle: {angle}
Writer Draft (Optional): {writer_draft or "None"}

{formatted_sources}
"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                OPENROUTER_URL,
                headers=self._get_headers(),
                json={
                    "model": model,
                    "messages": messages,
                    "response_format": {"type": "json_object"}
                }
            )
            
            if response.status_code != 200:
                raise Exception(f"OpenRouter API error (Status {response.status_code}): {response.text}")
            
            result_data = response.json()
            raw_text = result_data["choices"][0]["message"]["content"]
            
            # Clean up the output if JSON block format was used by LLM anyway
            raw_text = raw_text.strip()
            if raw_text.startswith("```json"):
                raw_text = raw_text[7:]
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3]
            raw_text = raw_text.strip()
            
            return json.loads(raw_text)

    async def humanize_slide(
        self,
        model: str,
        slide: Dict[str, Any],
        design_system_notes: str,
        base_dir: str
    ) -> Dict[str, str]:
        """
        Stage 2: Outline -> Final copy. Processes a single slide to humanize its text based on
        brand voice, design system constraints, and the-humanizer-v2.5.md.
        """
        humanizer_rules = self.load_humanizer_rules(base_dir)
        voice_profile = self.load_voice_profile(base_dir)

        system_prompt = f"""You are a master LinkedIn copywriter and editor.
Your task is to refine the draft headline and body copy for a single slide of a LinkedIn carousel.
You must enforce strict Brand Voice Calibration and Humanizer rules.

### BRAND VOICE PROFILE
{voice_profile}

### HUMANIZER SYSTEM RULES
{humanizer_rules}

### DESIGN SYSTEM RULES & CONSTRAINTS
{design_system_notes}

### OUTPUT FORMAT
You must respond with a JSON object containing exactly two keys:
1. "headline": string (highly refined, maximum 12 words, optimized for mobile safe zones and asymmetrical layout, no corporate buzzwords)
2. "body": string (1-3 sentences, varying rhythm, no AI vocabulary, concrete and metrics-focused)

Return ONLY valid JSON. Do not include markdown formatting or extra text.
"""

        user_content = f"""
Slide Job: {slide.get('job', 'Content')}
Draft Headline: {slide.get('headline', '')}
Draft Body: {slide.get('body', '')}
Draft Stat/Quote (Optional): {slide.get('stat') or "None"}
"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                OPENROUTER_URL,
                headers=self._get_headers(),
                json={
                    "model": model,
                    "messages": messages,
                    "response_format": {"type": "json_object"}
                }
            )
            
            if response.status_code != 200:
                raise Exception(f"OpenRouter API error (Status {response.status_code}): {response.text}")
            
            result_data = response.json()
            raw_text = result_data["choices"][0]["message"]["content"]
            
            raw_text = raw_text.strip()
            if raw_text.startswith("```json"):
                raw_text = raw_text[7:]
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3]
            raw_text = raw_text.strip()
            
            return json.loads(raw_text)
