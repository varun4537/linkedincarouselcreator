import os
import uuid
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

import inspect

def render_template(template_name: str, request: Request, context: dict):
    context["request"] = request
    sig = inspect.signature(templates.TemplateResponse)
    if "request" in sig.parameters:
        return templates.TemplateResponse(request=request, name=template_name, context=context)
    else:
        return templates.TemplateResponse(name=template_name, context=context)

from database import SessionLocal, Carousel

def db_get_carousel_state(generation_id: str) -> dict:
    db = SessionLocal()
    try:
        carousel = db.query(Carousel).filter(Carousel.id == generation_id).first()
        if not carousel:
            return None
        return json.loads(carousel.state_json)
    finally:
        db.close()

def db_save_carousel_state(generation_id: str, state: dict):
    db = SessionLocal()
    try:
        carousel = db.query(Carousel).filter(Carousel.id == generation_id).first()
        if not carousel:
            carousel = Carousel(
                id=generation_id,
                user_id="admin",
                topic=state.get("brief", {}).get("topic", "Untitled Topic"),
                aspect_ratio=state.get("brief", {}).get("format", "1080x1440"),
                design_system=state.get("brief", {}).get("design_system", "e2e_premium"),
                state_json=json.dumps(state)
            )
            db.add(carousel)
        else:
            carousel.topic = state.get("brief", {}).get("topic", carousel.topic)
            carousel.aspect_ratio = state.get("brief", {}).get("format", carousel.aspect_ratio)
            carousel.design_system = state.get("brief", {}).get("design_system", carousel.design_system)
            carousel.state_json = json.dumps(state)
        db.commit()
    finally:
        db.close()

from database import BrandKit, WriterProfile
from typing import Optional

# Pydantic Schemas for API Requests
class BrandKitSchema(BaseModel):
    name: str
    logo_url: Optional[str] = None
    primary_color: Optional[str] = "#1f6e7c"
    secondary_color: Optional[str] = "#f4f7f6"
    accent_color: Optional[str] = "#e27d60"
    font_header: Optional[str] = "Big Shoulders Display"
    font_body: Optional[str] = "Plus Jakarta Sans"
    handle_cta: Optional[str] = ""
    is_default: Optional[bool] = False

class WriterProfileSchema(BaseModel):
    name: str
    tone_description: str
    sample_text: Optional[str] = None
    is_default: Optional[bool] = False

# CRUD for Brand Kits
@app.get("/api/brand-kits", dependencies=[Depends(check_authenticated)])
def get_brand_kits():
    db = SessionLocal()
    try:
        kits = db.query(BrandKit).filter(BrandKit.user_id == "admin").all()
        return [{
            "id": k.id,
            "name": k.name,
            "logo_url": k.logo_url,
            "primary_color": k.primary_color,
            "secondary_color": k.secondary_color,
            "accent_color": k.accent_color,
            "font_header": k.font_header,
            "font_body": k.font_body,
            "handle_cta": k.handle_cta,
            "is_default": k.is_default
        } for k in kits]
    finally:
        db.close()

@app.post("/api/brand-kits", dependencies=[Depends(check_authenticated)])
def create_brand_kit(kit: BrandKitSchema):
    db = SessionLocal()
    try:
        kit_id = str(uuid.uuid4())
        
        # If this is marked as default, unset other defaults
        if kit.is_default:
            db.query(BrandKit).filter(BrandKit.user_id == "admin").update({"is_default": False})
            
        new_kit = BrandKit(
            id=kit_id,
            user_id="admin",
            name=kit.name,
            logo_url=kit.logo_url,
            primary_color=kit.primary_color,
            secondary_color=kit.secondary_color,
            accent_color=kit.accent_color,
            font_header=kit.font_header,
            font_body=kit.font_body,
            handle_cta=kit.handle_cta,
            is_default=kit.is_default
        )
        db.add(new_kit)
        db.commit()
        return {"status": "success", "id": kit_id}
    finally:
        db.close()

@app.put("/api/brand-kits/{kit_id}", dependencies=[Depends(check_authenticated)])
def update_brand_kit(kit_id: str, kit: BrandKitSchema):
    db = SessionLocal()
    try:
        db_kit = db.query(BrandKit).filter(BrandKit.id == kit_id, BrandKit.user_id == "admin").first()
        if not db_kit:
            raise HTTPException(status_code=404, detail="Brand kit not found")
            
        # If this is marked as default, unset other defaults
        if kit.is_default:
            db.query(BrandKit).filter(BrandKit.user_id == "admin").update({"is_default": False})
            
        db_kit.name = kit.name
        db_kit.logo_url = kit.logo_url
        db_kit.primary_color = kit.primary_color
        db_kit.secondary_color = kit.secondary_color
        db_kit.accent_color = kit.accent_color
        db_kit.font_header = kit.font_header
        db_kit.font_body = kit.font_body
        db_kit.handle_cta = kit.handle_cta
        db_kit.is_default = kit.is_default
        db.commit()
        return {"status": "success"}
    finally:
        db.close()

@app.delete("/api/brand-kits/{kit_id}", dependencies=[Depends(check_authenticated)])
def delete_brand_kit(kit_id: str):
    db = SessionLocal()
    try:
        db_kit = db.query(BrandKit).filter(BrandKit.id == kit_id, BrandKit.user_id == "admin").first()
        if not db_kit:
            raise HTTPException(status_code=404, detail="Brand kit not found")
        db.delete(db_kit)
        db.commit()
        return {"status": "success"}
    finally:
        db.close()

# CRUD for Writer Profiles
@app.get("/api/writer-profiles", dependencies=[Depends(check_authenticated)])
def get_writer_profiles():
    db = SessionLocal()
    try:
        profiles = db.query(WriterProfile).filter(WriterProfile.user_id == "admin").all()
        return [{
            "id": p.id,
            "name": p.name,
            "tone_description": p.tone_description,
            "sample_text": p.sample_text,
            "is_default": p.is_default
        } for p in profiles]
    finally:
        db.close()

@app.post("/api/writer-profiles", dependencies=[Depends(check_authenticated)])
def create_writer_profile(profile: WriterProfileSchema):
    db = SessionLocal()
    try:
        profile_id = str(uuid.uuid4())
        
        # If this is marked as default, unset other defaults
        if profile.is_default:
            db.query(WriterProfile).filter(WriterProfile.user_id == "admin").update({"is_default": False})
            
        new_profile = WriterProfile(
            id=profile_id,
            user_id="admin",
            name=profile.name,
            tone_description=profile.tone_description,
            sample_text=profile.sample_text,
            is_default=profile.is_default
        )
        db.add(new_profile)
        db.commit()
        return {"status": "success", "id": profile_id}
    finally:
        db.close()

@app.put("/api/writer-profiles/{profile_id}", dependencies=[Depends(check_authenticated)])
def update_writer_profile(profile_id: str, profile: WriterProfileSchema):
    db = SessionLocal()
    try:
        db_profile = db.query(WriterProfile).filter(WriterProfile.id == profile_id, WriterProfile.user_id == "admin").first()
        if not db_profile:
            raise HTTPException(status_code=404, detail="Writer profile not found")
            
        # If this is marked as default, unset other defaults
        if profile.is_default:
            db.query(WriterProfile).filter(WriterProfile.user_id == "admin").update({"is_default": False})
            
        db_profile.name = profile.name
        db_profile.tone_description = profile.tone_description
        db_profile.sample_text = profile.sample_text
        db_profile.is_default = profile.is_default
        db.commit()
        return {"status": "success"}
    finally:
        db.close()

@app.delete("/api/writer-profiles/{profile_id}", dependencies=[Depends(check_authenticated)])
def delete_writer_profile(profile_id: str):
    db = SessionLocal()
    try:
        db_profile = db.query(WriterProfile).filter(WriterProfile.id == profile_id, WriterProfile.user_id == "admin").first()
        if not db_profile:
            raise HTTPException(status_code=404, detail="Writer profile not found")
        db.delete(db_profile)
        db.commit()
        return {"status": "success"}
    finally:
        db.close()




# Initialize OpenRouter Client
client = OpenRouterClient()

@app.get("/login", response_class=HTMLResponse)
async def login_get(request: Request, error: Optional[str] = None):
    if request.cookies.get("session_id") == "authenticated":
        return RedirectResponse(url="/", status_code=303)
    return render_template("login.html", request, {"error": error})

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
    
    return render_template("login.html", request, {"error": "Invalid username or password"})

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
    return render_template("screen1_brief.html", request, {"api_key_set": api_key_set})

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

    db_save_carousel_state(generation_id, state)

    return RedirectResponse(
        url=f"/generation/{generation_id}/outline",
        status_code=303
    )

@app.get("/generation/{generation_id}/outline", response_class=HTMLResponse, dependencies=[Depends(check_authenticated)])
async def screen2_outline(request: Request, generation_id: str):
    state = db_get_carousel_state(generation_id)
    if not state:
        raise HTTPException(status_code=404, detail="Generation data not found.")

    return render_template("screen2_outline.html", request, {
            "generation_id": generation_id,
            "facts_ledger": state["facts_ledger"],
            "humanizer_flags": state["humanizer_flags"],
            "outline": state["slides"],
            "stage2_model": state["stage2_model"],
            "design_system": state["brief"]["design_system"],
            "format": state["brief"]["format"]
        })

@app.post("/render-carousel", dependencies=[Depends(check_authenticated)])
async def handle_outline_approve(
    request: Request,
    generation_id: str = Form(...),
    stage2_model: str = Form(...),
    design_system: str = Form(...),
    format: str = Form(...),
):
    state = db_get_carousel_state(generation_id)
    if not state:
        raise HTTPException(status_code=404, detail="Generation data not found.")

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
    db_save_carousel_state(generation_id, state)

    return RedirectResponse(
        url=f"/generation/{generation_id}/render",
        status_code=303
    )

@app.get("/generation/{generation_id}/render", response_class=HTMLResponse, dependencies=[Depends(check_authenticated)])
async def screen3_render(request: Request, generation_id: str):
    state = db_get_carousel_state(generation_id)
    if not state:
        raise HTTPException(status_code=404, detail="Generation data not found.")

    # Stringify the slides content so we can parse it in client-side javascript
    slides_json = json.dumps({"slides": state["slides"]})

    return render_template("screen3_render.html", request, {
            "generation_id": generation_id,
            "slides": state["slides"],
            "slides_json": slides_json,
            "format": state["brief"]["format"],
            "urls": state["brief"]["urls"],
            "stage2_model": state["stage2_model"],
            "design_system": state["brief"]["design_system"],
            "logo_base64": LOGO_BASE64
        })

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
    state = db_get_carousel_state(req.generation_id)
    if not state:
        raise HTTPException(status_code=404, detail="State not found")

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
        db_save_carousel_state(req.generation_id, state)

        return new_slide

class SaveEditsRequest(BaseModel):
    generation_id: str
    slides: List[Dict[str, Any]]
    format: str

@app.post("/api/save-slide-edits", dependencies=[Depends(check_authenticated)])
async def api_save_slide_edits(req: SaveEditsRequest):
    state = db_get_carousel_state(req.generation_id)
    if not state:
        raise HTTPException(status_code=404, detail="State not found")

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
    state = db_get_carousel_state(req.generation_id)
    if not state:
        raise HTTPException(status_code=404, detail="State not found")

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

        db_save_carousel_state(req.generation_id, state)

        return new_copy

# -------------------------------------------------------------
# PRINT LAYOUT & PDF EXPORT
# -------------------------------------------------------------

@app.get("/generation/{generation_id}/print", response_class=HTMLResponse, dependencies=[Depends(check_authenticated)])
async def print_layout(request: Request, generation_id: str, format: str = "1080x1350"):
    state = db_get_carousel_state(generation_id)
    if not state:
        raise HTTPException(status_code=404, detail="Generation data not found.")

    return render_template("print.html", request, {
            "slides": state["slides"],
            "format": format,
            "urls": state["brief"]["urls"],
            "design_system": state["brief"]["design_system"],
            "logo_base64": LOGO_BASE64
        })

@app.get("/generation/{generation_id}/download", dependencies=[Depends(check_authenticated)])
async def download_pdf(generation_id: str, format: str = "1080x1350"):
    state = db_get_carousel_state(generation_id)
    if not state:
        raise HTTPException(status_code=404, detail="Generation data not found.")

    # Determine canvas aspect ratios
    if format == "1080x1440":
        width_px, height_px = (1080, 1440)
    elif format == "1080x1350":
        width_px, height_px = (1080, 1350)
    else:
        width_px, height_px = (1080, 1080)

    # Local print URL
    port = os.getenv("PORT", "8000")
    print_url = f"http://localhost:{port}/generation/{generation_id}/print?format={format}"
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
    return render_template("design_settings.html", request, {"content": content})

@app.post("/design", dependencies=[Depends(check_authenticated)])
async def post_design_settings(request: Request, content: str = Form(...)):
    design_path = os.path.join(BASE_DIR, "design.md")
    with open(design_path, "w", encoding="utf-8") as f:
        f.write(content)
    return RedirectResponse(url="/", status_code=303)

# Startup check script
@app.on_event("startup")
async def startup_event():
    from database import seed_default_data
    try:
        seed_default_data()
    except Exception as e:
        print(f"Error seeding database: {e}")
        
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
