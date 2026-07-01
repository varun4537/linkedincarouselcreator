import os
import re
import json
import asyncio
import httpx
from datetime import datetime
from fastapi import FastAPI, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

from fastapi import Depends
from starlette import status

def check_authenticated(request: Request):
    # Only bypass authentication for print layout calls when requested locally
    if request.url.path.endswith("/print"):
        client_host = request.client.host if request.client else None
        if client_host in ("127.0.0.1", "localhost", "::1"):
            return
    session_id = request.cookies.get("session_id")
    if session_id != "authenticated":
        raise HTTPException(
            status_code=307,
            headers={"Location": "/login"}
        )

from openrouter_client import OpenRouterClient
from pdf_generator import render_html_to_pdf

app = FastAPI(title="LinkedIn Carousel Generator")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
GENERATIONS_DIR = os.path.join(BASE_DIR, "generations")
os.makedirs(GENERATIONS_DIR, exist_ok=True)

# Load local .env file if it exists (for local development, keeping keys out of git)
env_path = os.path.join(BASE_DIR, ".env")
if os.path.exists(env_path):
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip() and not line.startswith("#"):
                parts = line.strip().split("=", 1)
                if len(parts) == 2:
                    os.environ[parts[0].strip()] = parts[1].strip()


# Mount static files and setup templates
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# Load E2E logo base64 if it exists
LOGO_BASE64 = ""
logo_path = os.path.join(BASE_DIR, "logo_base64.txt")
if os.path.exists(logo_path):
    try:
        with open(logo_path, "r", encoding="utf-8") as f:
            LOGO_BASE64 = f.read().strip()
    except Exception as e:
        print(f"Error loading logo: {e}")

def parse_body_list(body_text: str):
    if not body_text:
        return None
    # Normalize newlines
    body_text = body_text.replace("\r\n", "\n")
    lines = [line.strip() for line in body_text.split("\n") if line.strip()]
    # Check if there are multiple lines and at least one starts with a bullet marker or letter/number lists
    has_bullets = any(re.match(r"^[-*•\d\.\s]+|^[A-Za-z0-9]\.\s*", line) for line in lines)
    if len(lines) > 1 and has_bullets:
        parsed = []
        for line in lines:
            # Strip bullet character and leading/trailing spacing
            clean = re.sub(r"^[-*•\d\.\s]+|^[A-Za-z0-9]\.\s*", "", line).strip()
            if clean:
                parsed.append(clean)
        return parsed
    return None

templates.env.filters["parse_body_list"] = parse_body_list

# Initialize OpenRouter Client
client = OpenRouterClient()

@app.get("/login", response_class=HTMLResponse)
async def login_get(request: Request, error: Optional[str] = None):
    if request.cookies.get("session_id") == "authenticated":
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": error}
    )

@app.post("/login")
async def login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...)
):
    app_user = os.getenv("APP_USERNAME", "admin")
    app_pass = os.getenv("APP_PASSWORD", "carousel2026")
    
    if username == app_user and password == app_pass:
        response = RedirectResponse(url="/", status_code=303)
        response.set_cookie(key="session_id", value="authenticated", max_age=86400 * 30, httponly=True)
        return response
    
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": "Invalid username or password"}
    )

@app.get("/logout")
async def logout_get():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(key="session_id")
    return response


# Helper: slugify text for filenames and routes
def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")

# Dependency: Check OpenRouter API Key
def check_api_key():
    key = os.getenv("OPENROUTER_API_KEY", "")
    if not key.strip():
        # We don't crash, but we raise an exception that gets caught or rendered in UI
        pass
    return key

# -------------------------------------------------------------
# WEB INTERFACE ROUTING
# -------------------------------------------------------------

@app.get("/", response_class=HTMLResponse, dependencies=[Depends(check_authenticated)])
async def screen1_brief(request: Request):
    api_key_set = bool(os.getenv("OPENROUTER_API_KEY", "").strip())
    return templates.TemplateResponse(
        "screen1_brief.html",
        {"request": request, "api_key_set": api_key_set}
    )

@app.post("/generate-outline", dependencies=[Depends(check_authenticated)])
async def handle_brief_submit(
    request: Request,
    topic: str = Form(...),
    sources: List[str] = Form(...),
    urls: List[str] = Form(None),
    audience: str = Form(...),
    angle: str = Form(...),
    writer_draft: Optional[str] = Form(None),
    stage1_model: str = Form(...),
    stage2_model: str = Form(...),
    design_system: str = Form(...),
    format: str = Form(...),
):
    # Enforce API key check
    if not os.getenv("OPENROUTER_API_KEY", "").strip():
        raise HTTPException(status_code=500, detail="OPENROUTER_API_KEY environment variable is not set. Please set it and restart.")

    # 1. Create a unique generation ID
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    slug = slugify(topic)[:30]
    generation_id = f"{timestamp}-{slug}"
    gen_path = os.path.join(GENERATIONS_DIR, generation_id)
    os.makedirs(gen_path, exist_ok=True)

    # Clean sources and URLs (remove empty elements)
    cleaned_sources = [s.strip() for s in sources if s.strip()]
    cleaned_urls = [u.strip() for u in urls if u.strip()] if urls else []

    # 2. Call OpenRouter Stage 1
    try:
        stage1_output = await client.generate_stage1_outline(
            model=stage1_model,
            topic=topic,
            sources=cleaned_sources,
            urls=cleaned_urls,
            audience=audience,
            angle=angle,
            writer_draft=writer_draft,
            base_dir=BASE_DIR
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Stage 1 Generation Failed: {str(e)}")

    # 3. Save state to filesystem
    state = {
        "generation_id": generation_id,
        "brief": {
            "topic": topic,
            "sources": cleaned_sources,
            "urls": cleaned_urls,
            "audience": audience,
            "angle": angle,
            "writer_draft": writer_draft,
            "design_system": design_system,
            "format": format
        },
        "stage1_model": stage1_model,
        "stage2_model": stage2_model,
        "facts_ledger": stage1_output.get("facts_ledger", []),
        "humanizer_flags": stage1_output.get("humanizer_flags", []),
        "slides": stage1_output.get("outline", [])
    }

    state_file = os.path.join(gen_path, "state.json")
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=4, ensure_ascii=False)

    return RedirectResponse(
        url=f"/generation/{generation_id}/outline",
        status_code=303
    )

@app.get("/generation/{generation_id}/outline", response_class=HTMLResponse, dependencies=[Depends(check_authenticated)])
async def screen2_outline(request: Request, generation_id: str):
    gen_path = os.path.join(GENERATIONS_DIR, generation_id)
    state_file = os.path.join(gen_path, "state.json")
    
    if not os.path.exists(state_file):
        raise HTTPException(status_code=404, detail="Generation data not found.")

    with open(state_file, "r", encoding="utf-8") as f:
        state = json.load(f)

    return templates.TemplateResponse(
        "screen2_outline.html",
        {
            "request": request,
            "generation_id": generation_id,
            "facts_ledger": state["facts_ledger"],
            "humanizer_flags": state["humanizer_flags"],
            "outline": state["slides"],
            "stage2_model": state["stage2_model"],
            "design_system": state["brief"]["design_system"],
            "format": state["brief"]["format"]
        }
    )

@app.post("/render-carousel", dependencies=[Depends(check_authenticated)])
async def handle_outline_approve(
    request: Request,
    generation_id: str = Form(...),
    stage2_model: str = Form(...),
    design_system: str = Form(...),
    format: str = Form(...),
):
    gen_path = os.path.join(GENERATIONS_DIR, generation_id)
    state_file = os.path.join(gen_path, "state.json")
    
    if not os.path.exists(state_file):
        raise HTTPException(status_code=404, detail="Generation data not found.")

    with open(state_file, "r", encoding="utf-8") as f:
        state = json.load(f)

    # 1. Parse slide inputs submitted from the outline editor screen
    form_data = await request.form()
    
    updated_outline = []
    # Count how many slides were submitted
    slide_keys = [k for k in form_data.keys() if k.startswith("slide_") and k.endswith("_headline")]
    slide_count = len(slide_keys)

    for i in range(1, slide_count + 1):
        job = form_data.get(f"slide_{i}_job")
        headline = form_data.get(f"slide_{i}_headline")
        body = form_data.get(f"slide_{i}_body")
        stat = form_data.get(f"slide_{i}_stat")
        
        updated_outline.append({
            "slide_number": i,
            "job": job,
            "headline": headline,
            "body": body,
            "stat": stat if stat else None
        })

    state["slides"] = updated_outline
    state["stage2_model"] = stage2_model
    state["brief"]["design_system"] = design_system
    state["brief"]["format"] = format

    # 2. Trigger Stage 2: Parallel Copy Humanization (OpenRouter Calls)
    # Define styling boundaries for layout calibration based on design.md
    design_system_notes = """
    Warm Editorial design rules:
    - Headline must be short (max 12 words), stacked, and punchy.
    - Body must be 1-3 sentences maximum. Keep sentence lengths varied.
    - Numbers/stats should be highlighted separately in the UI (keep stats clean).
    - Enforce 15% mobile safe zones. Do not use verbose filler or templates.
    """

    try:
        tasks = []
        for slide in state["slides"]:
            tasks.append(client.humanize_slide(
                model=stage2_model,
                slide=slide,
                design_system_notes=design_system_notes,
                base_dir=BASE_DIR
            ))
        
        # Gather all slide rewrite calls concurrently
        humanized_results = await asyncio.gather(*tasks)
        
        # Apply the humanized outputs back into state
        for idx, result in enumerate(humanized_results):
            state["slides"][idx]["headline"] = result.get("headline", state["slides"][idx]["headline"])
            state["slides"][idx]["body"] = result.get("body", state["slides"][idx]["body"])
            if "stat" in result and result["stat"]:
                state["slides"][idx]["stat"] = result["stat"]
    except Exception as e:
         raise HTTPException(status_code=500, detail=f"Stage 2 Humanization failed: {str(e)}")

    # 3. Save final generated state
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=4, ensure_ascii=False)

    return RedirectResponse(
        url=f"/generation/{generation_id}/render",
        status_code=303
    )

@app.get("/generation/{generation_id}/render", response_class=HTMLResponse, dependencies=[Depends(check_authenticated)])
async def screen3_render(request: Request, generation_id: str):
    gen_path = os.path.join(GENERATIONS_DIR, generation_id)
    state_file = os.path.join(gen_path, "state.json")
    
    if not os.path.exists(state_file):
        raise HTTPException(status_code=404, detail="Generation data not found.")

    with open(state_file, "r", encoding="utf-8") as f:
        state = json.load(f)

    # Stringify the slides content so we can parse it in client-side javascript
    slides_json = json.dumps({"slides": state["slides"]})

    return templates.TemplateResponse(
        "screen3_render.html",
        {
            "request": request,
            "generation_id": generation_id,
            "slides": state["slides"],
            "slides_json": slides_json,
            "format": state["brief"]["format"],
            "urls": state["brief"]["urls"],
            "stage2_model": state["stage2_model"],
            "design_system": state["brief"]["design_system"],
            "logo_base64": LOGO_BASE64
        }
    )

# -------------------------------------------------------------
# API ROUTING FOR INTERACTIVE UPDATES
# -------------------------------------------------------------

class SlideRegenOutlineRequest(BaseModel):
    generation_id: str
    slide_number: int
    tweak_instruction: str
    model: str

@app.post("/api/regenerate-slide-outline", dependencies=[Depends(check_authenticated)])
async def api_regenerate_slide_outline(req: SlideRegenOutlineRequest):
    gen_path = os.path.join(GENERATIONS_DIR, req.generation_id)
    state_file = os.path.join(gen_path, "state.json")
    
    if not os.path.exists(state_file):
        raise HTTPException(status_code=404, detail="State not found")

    with open(state_file, "r", encoding="utf-8") as f:
        state = json.load(f)

    # Find the target slide
    slide_idx = -1
    for i, slide in enumerate(state["slides"]):
        if slide["slide_number"] == req.slide_number:
            slide_idx = i
            break

    if slide_idx == -1:
        raise HTTPException(status_code=400, detail="Slide number not found")

    target_slide = state["slides"][slide_idx]
    
    # Request outline regen prompt
    system_prompt = f"""You are an editor refinement assistant.
Refine the following slide based on the user's specific instruction.
Maintain strict adherence to the facts from the sources.

Instruction: {req.tweak_instruction}

Respond with a JSON object containing exactly three fields:
1. "job": string (Slide job)
2. "headline": string (max 12 words)
3. "body": string (1-3 sentences)
4. "stat": string or null
"""
    user_content = f"Slide: {json.dumps(target_slide)}"

    async with httpx.AsyncClient(timeout=30.0) as http_client:
        response = await http_client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=client._get_headers(),
            json={
                "model": req.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                "response_format": {"type": "json_object"}
            }
        )
        if response.status_code != 200:
            raise HTTPException(status_code=500, detail="OpenRouter API failure")
        
        res_data = response.json()
        raw_text = res_data["choices"][0]["message"]["content"].strip()
        
        # Clean markdown wrappers if any
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:]
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3]
        
        new_slide = json.loads(raw_text.strip())
        new_slide["slide_number"] = req.slide_number
        
        # Save back to state
        state["slides"][slide_idx] = new_slide
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=4, ensure_ascii=False)

        return new_slide

class SaveEditsRequest(BaseModel):
    generation_id: str
    slides: List[Dict[str, Any]]
    format: str

@app.post("/api/save-slide-edits", dependencies=[Depends(check_authenticated)])
async def api_save_slide_edits(req: SaveEditsRequest):
    gen_path = os.path.join(GENERATIONS_DIR, req.generation_id)
    state_file = os.path.join(gen_path, "state.json")
    
    if not os.path.exists(state_file):
        raise HTTPException(status_code=404, detail="State not found")

    with open(state_file, "r", encoding="utf-8") as f:
        state = json.load(f)

    state["slides"] = req.slides
    state["brief"]["format"] = req.format

    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=4, ensure_ascii=False)

    return {"status": "success"}

class SlideRegenCopyRequest(BaseModel):
    generation_id: str
    slide_index: int
    tweak_instruction: str
    model: str

@app.post("/api/regenerate-slide-copy", dependencies=[Depends(check_authenticated)])
async def api_regenerate_slide_copy(req: SlideRegenCopyRequest):
    gen_path = os.path.join(GENERATIONS_DIR, req.generation_id)
    state_file = os.path.join(gen_path, "state.json")
    
    if not os.path.exists(state_file):
        raise HTTPException(status_code=404, detail="State not found")

    with open(state_file, "r", encoding="utf-8") as f:
        state = json.load(f)

    if req.slide_index < 0 or req.slide_index >= len(state["slides"]):
        raise HTTPException(status_code=400, detail="Invalid slide index")

    target_slide = state["slides"][req.slide_index]
    humanizer_rules = client.load_humanizer_rules(BASE_DIR)
    voice_profile = client.load_voice_profile(BASE_DIR)

    system_prompt = f"""You are a master editor. Rewrite the slide copy based on the instruction.
Apply these strict humanizer rules and voice calibration profile.

### VOICE PROFILE
{voice_profile}

### HUMANIZER RULES
{humanizer_rules}

### USER INSTRUCTION
{req.tweak_instruction}

Respond with a JSON object containing:
1. "headline": string (max 12 words)
2. "body": string (1-3 sentences)
3. "stat": string or null (if slide uses statistics)
"""
    user_content = f"Current Slide Draft: {json.dumps(target_slide)}"

    async with httpx.AsyncClient(timeout=30.0) as http_client:
        response = await http_client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=client._get_headers(),
            json={
                "model": req.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                "response_format": {"type": "json_object"}
            }
        )
        if response.status_code != 200:
            raise HTTPException(status_code=500, detail="OpenRouter API failure")
        
        res_data = response.json()
        raw_text = res_data["choices"][0]["message"]["content"].strip()
        
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:]
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3]

        new_copy = json.loads(raw_text.strip())
        
        # Merge back
        state["slides"][req.slide_index]["headline"] = new_copy["headline"]
        state["slides"][req.slide_index]["body"] = new_copy["body"]
        if "stat" in new_copy:
            state["slides"][req.slide_index]["stat"] = new_copy["stat"]

        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=4, ensure_ascii=False)

        return new_copy

# -------------------------------------------------------------
# PRINT LAYOUT & PDF EXPORT
# -------------------------------------------------------------

@app.get("/generation/{generation_id}/print", response_class=HTMLResponse, dependencies=[Depends(check_authenticated)])
async def print_layout(request: Request, generation_id: str, format: str = "1080x1350"):
    gen_path = os.path.join(GENERATIONS_DIR, generation_id)
    state_file = os.path.join(gen_path, "state.json")
    
    if not os.path.exists(state_file):
        raise HTTPException(status_code=404, detail="Generation data not found.")

    with open(state_file, "r", encoding="utf-8") as f:
        state = json.load(f)

    return templates.TemplateResponse(
        "print.html",
        {
            "request": request,
            "slides": state["slides"],
            "format": format,
            "urls": state["brief"]["urls"],
            "design_system": state["brief"]["design_system"],
            "logo_base64": LOGO_BASE64
        }
    )

@app.get("/generation/{generation_id}/download", dependencies=[Depends(check_authenticated)])
async def download_pdf(generation_id: str, format: str = "1080x1350"):
    gen_path = os.path.join(GENERATIONS_DIR, generation_id)
    state_file = os.path.join(gen_path, "state.json")
    
    if not os.path.exists(state_file):
        raise HTTPException(status_code=404, detail="Generation data not found.")

    with open(state_file, "r", encoding="utf-8") as f:
        state = json.load(f)

    # Determine canvas aspect ratios
    if format == "1080x1440":
        width_px, height_px = (1080, 1440)
    elif format == "1080x1350":
        width_px, height_px = (1080, 1350)
    else:
        width_px, height_px = (1080, 1080)

    # Local print URL
    print_url = f"http://localhost:8000/generation/{generation_id}/print?format={format}"
    pdf_filename = f"{slugify(state['brief']['topic'])}-{datetime.now().strftime('%Y-%m-%d')}.pdf"
    output_pdf_path = os.path.join(gen_path, pdf_filename)

    # Run Playwright PDF render task
    try:
        await render_html_to_pdf(
            url=print_url,
            output_pdf_path=output_pdf_path,
            width_px=width_px,
            height_px=height_px
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {str(e)}")

    if not os.path.exists(output_pdf_path):
        raise HTTPException(status_code=500, detail="PDF output file was not generated.")

    return FileResponse(
        path=output_pdf_path,
        media_type="application/pdf",
        filename=pdf_filename
    )

# -------------------------------------------------------------
# DESIGN SYSTEM SETTINGS EDITOR
# -------------------------------------------------------------

@app.get("/design", response_class=HTMLResponse, dependencies=[Depends(check_authenticated)])
async def get_design_settings(request: Request):
    design_path = os.path.join(BASE_DIR, "design.md")
    content = ""
    if os.path.exists(design_path):
        with open(design_path, "r", encoding="utf-8") as f:
            content = f.read()
    return templates.TemplateResponse(
        "design_settings.html",
        {"request": request, "content": content}
    )

@app.post("/design", dependencies=[Depends(check_authenticated)])
async def post_design_settings(request: Request, content: str = Form(...)):
    design_path = os.path.join(BASE_DIR, "design.md")
    with open(design_path, "w", encoding="utf-8") as f:
        f.write(content)
    return RedirectResponse(url="/", status_code=303)

# Startup check script
@app.on_event("startup")
async def startup_event():
    key = os.getenv("OPENROUTER_API_KEY", "")
    if not key.strip():
        print("*" * 60)
        print("WARNING: OPENROUTER_API_KEY environment variable is not set!")
        print("Please set it in your environment before using the generation features.")
        print("*" * 60)

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
