import os
from playwright.async_api import async_playwright

async def render_html_to_pdf(
    url: str,
    output_pdf_path: str,
    width_px: int,
    height_px: int
):
    """
    Launches headless Chromium via Playwright, opens the given URL (local server route),
    waits for load state, and prints to a multi-page PDF matching the aspect ratio dimensions.
    """
    async with async_playwright() as p:
        # Launch browser with sandbox disabled for compatibility across platforms
        browser = await p.chromium.launch(
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-web-security"]
        )
        
        # Open page and emulate screen media to ensure CSS colors print as they look on screen
        page = await browser.new_page(
            viewport={"width": width_px, "height": height_px},
            device_scale_factor=1
        )
        
        await page.goto(url, wait_until="networkidle")
        await page.emulate_media(media="screen")
        
        # Ensure all images are fully loaded and decoded before printing to PDF
        await page.evaluate("() => Promise.all(Array.from(document.images).map(img => img.complete ? Promise.resolve() : new Promise(resolve => { img.onload = resolve; img.onerror = resolve; })))")
        
        # Add a short timeout to let rendering settle
        await page.wait_for_timeout(1000)
        
        # Configure output dimensions in pixels to preserve crispness
        # Note: Playwright takes print dimensions in px/in/mm. We pass string with px.
        await page.pdf(
            path=output_pdf_path,
            width=f"{width_px}px",
            height=f"{height_px}px",
            print_background=True,
            margin={"top": "0px", "right": "0px", "bottom": "0px", "left": "0px"},
            display_header_footer=False,
            prefer_css_page_size=True
        )
        
        await browser.close()
