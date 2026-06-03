// Main frontend logic for LinkedIn Carousel Creator

document.addEventListener("DOMContentLoaded", () => {
    // Determine which page/screen is currently active based on markup element IDs
    initBriefScreen();
    initOutlineScreen();
    initRenderScreen();
});

// Helper: Show and Hide Loading Overlay
function showLoading(text = "Processing...") {
    const overlay = document.getElementById("loading-overlay");
    if (overlay) {
        const textEl = overlay.querySelector(".loading-text");
        if (textEl) textEl.textContent = text;
        overlay.style.display = "flex";
    }
}

function hideLoading() {
    const overlay = document.getElementById("loading-overlay");
    if (overlay) {
        overlay.style.display = "none";
    }
}

// -------------------------------------------------------------
// SCREEN 1: BRIEF HANDLING
// -------------------------------------------------------------
function initBriefScreen() {
    const briefForm = document.getElementById("brief-form");
    if (!briefForm) return;

    // Add source block dynamic inputs
    const addBlockBtn = document.getElementById("add-source-block");
    const blocksContainer = document.getElementById("source-blocks-container");
    if (addBlockBtn && blocksContainer) {
        addBlockBtn.addEventListener("click", () => {
            const blockCount = blocksContainer.querySelectorAll("textarea").length;
            if (blockCount >= 5) {
                alert("Maximum of 5 source blocks allowed.");
                return;
            }
            const blockHtml = `
                <div class="form-group" style="position: relative;">
                    <label>Source Block ${blockCount + 1}</label>
                    <textarea name="sources" rows="4" placeholder="Paste source excerpts here..."></textarea>
                    <button type="button" class="btn btn-danger btn-remove-block" style="position: absolute; right: 0; top: 0; padding: 2px 8px; font-size: 11px;">Remove</button>
                </div>
            `;
            blocksContainer.insertAdjacentHTML("beforeend", blockHtml);
            bindRemoveButtons();
        });
    }

    function bindRemoveButtons() {
        document.querySelectorAll(".btn-remove-block").forEach(btn => {
            btn.onclick = (e) => {
                e.target.parentElement.remove();
                // Renumber labels
                document.querySelectorAll("#source-blocks-container label").forEach((lbl, idx) => {
                    lbl.textContent = `Source Block ${idx + 1}`;
                });
            };
        });
    }
    bindRemoveButtons();

    // Add dynamic source URL inputs
    const addUrlBtn = document.getElementById("add-source-url");
    const urlsContainer = document.getElementById("source-urls-container");
    if (addUrlBtn && urlsContainer) {
        addUrlBtn.addEventListener("click", () => {
            const urlCount = urlsContainer.querySelectorAll("input").length;
            if (urlCount >= 5) {
                alert("Maximum of 5 source URLs allowed.");
                return;
            }
            const urlHtml = `
                <div class="url-input-row">
                    <input type="text" name="urls" placeholder="https://example.com/article" />
                    <button type="button" class="btn btn-danger btn-remove-url" style="padding: 10px 16px;">X</button>
                </div>
            `;
            urlsContainer.insertAdjacentHTML("beforeend", urlHtml);
            bindUrlRemoveButtons();
        });
    }

    function bindUrlRemoveButtons() {
        document.querySelectorAll(".btn-remove-url").forEach(btn => {
            btn.onclick = (e) => {
                e.target.closest(".url-input-row").remove();
            };
        });
    }
    bindUrlRemoveButtons();

    // Design System Card Selector Interactivity
    const radioCards = document.querySelectorAll(".radio-card");
    radioCards.forEach(card => {
        card.addEventListener("click", () => {
            const groupName = card.dataset.group;
            document.querySelectorAll(`.radio-card[data-group="${groupName}"]`).forEach(c => {
                c.classList.remove("selected");
                const radio = c.querySelector('input[type="radio"]');
                if (radio) radio.checked = false;
            });
            card.classList.add("selected");
            const radio = card.querySelector('input[type="radio"]');
            if (radio) {
                radio.checked = true;
            }
        });
    });

    // Intercept form submit to show loader
    briefForm.addEventListener("submit", () => {
        showLoading("Extracting facts & generating outline (Stage 1)...");
    });
}

// -------------------------------------------------------------
// SCREEN 2: OUTLINE REVIEW
// -------------------------------------------------------------
function initOutlineScreen() {
    const outlineContainer = document.getElementById("outline-review-container");
    if (!outlineContainer) return;

    // Handle form submit of outline approval
    const approveBtn = document.getElementById("approve-outline-btn");
    const outlineForm = document.getElementById("outline-form");

    if (approveBtn && outlineForm) {
        approveBtn.addEventListener("click", (e) => {
            e.preventDefault();
            showLoading("Applying brand voice & humanizing copy (Stage 2)...");
            outlineForm.submit();
        });
    }

    // Bind individual slide level regenerations (OpenRouter calls)
    const regenButtons = document.querySelectorAll(".btn-regen-slide");
    regenButtons.forEach(btn => {
        btn.addEventListener("click", async (e) => {
            e.preventDefault();
            const slideNum = btn.dataset.slideNum;
            const generationId = document.getElementById("generation_id").value;
            const selectedModel = document.getElementById("stage2_model").value;

            // Prompt user for tweak instruction
            const instruction = prompt("Enter instructions to regenerate this slide (e.g. 'Make the headline more operational', 'Mention specific metrics'):");
            if (instruction === null) return; // User cancelled

            showLoading(`Regenerating Slide ${slideNum}...`);

            try {
                const response = await fetch("/api/regenerate-slide-outline", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify({
                        generation_id: generationId,
                        slide_number: parseInt(slideNum),
                        tweak_instruction: instruction,
                        model: selectedModel
                    })
                });

                if (!response.ok) {
                    throw new Error("Failed to regenerate slide copy.");
                }

                const data = await response.json();
                
                // Update inputs on the screen
                const row = document.querySelector(`.slide-row[data-slide-num="${slideNum}"]`);
                if (row) {
                    const headlineInput = row.querySelector(`input[name="slide_${slideNum}_headline"]`);
                    const bodyTextarea = row.querySelector(`textarea[name="slide_${slideNum}_body"]`);
                    const statInput = row.querySelector(`input[name="slide_${slideNum}_stat"]`);

                    if (headlineInput) headlineInput.value = data.headline;
                    if (bodyTextarea) bodyTextarea.value = data.body;
                    if (statInput && data.stat) statInput.value = data.stat;
                }
            } catch (err) {
                alert(`Error: ${err.message}`);
            } finally {
                hideLoading();
            }
        });
    });
}

// -------------------------------------------------------------
// SCREEN 3: RENDER & EXPORT
// -------------------------------------------------------------
let currentSlideIndex = 0;
let totalSlides = 0;
let carouselData = {};

function initRenderScreen() {
    const renderContainer = document.getElementById("render-export-container");
    if (!renderContainer) return;

    totalSlides = document.querySelectorAll(".preview-slide-wrapper").length;
    
    // Parse the slide content JSON if present
    const dataEl = document.getElementById("carousel-json-data");
    if (dataEl) {
        carouselData = JSON.parse(dataEl.textContent);
    }

    // Toggle aspect ratio (Square vs Portrait)
    const formatSelect = document.getElementById("format-selector");
    const previewContainer = document.getElementById("carousel-preview-canvas");
    if (formatSelect && previewContainer) {
        formatSelect.addEventListener("change", (e) => {
            const format = e.target.value;
            if (format === "1080x1350") {
                previewContainer.classList.remove("canvas-square");
                previewContainer.classList.add("canvas-portrait");
            } else {
                previewContainer.classList.remove("canvas-portrait");
                previewContainer.classList.add("canvas-square");
            }
            updateCarouselPosition();
        });
    }

    // Navigation Buttons
    const prevBtn = document.getElementById("prev-slide");
    const nextBtn = document.getElementById("next-slide");
    if (prevBtn && nextBtn) {
        prevBtn.addEventListener("click", () => {
            if (currentSlideIndex > 0) {
                currentSlideIndex--;
                updateCarouselPosition();
            }
        });
        nextBtn.addEventListener("click", () => {
            if (currentSlideIndex < totalSlides - 1) {
                currentSlideIndex++;
                updateCarouselPosition();
            }
        });
    }

    // Direct editing in place (Screen 3)
    const headlineInputs = document.querySelectorAll(".direct-edit-headline");
    const bodyInputs = document.querySelectorAll(".direct-edit-body");
    const statInputs = document.querySelectorAll(".direct-edit-stat");

    const formHeadline = document.getElementById("editor-headline");
    const formBody = document.getElementById("editor-body");
    const formStat = document.getElementById("editor-stat");
    const formStatContainer = document.getElementById("editor-stat-container");

    function updateEditorPane() {
        if (!formHeadline || !formBody) return;
        const currentSlide = carouselData.slides[currentSlideIndex];
        
        formHeadline.value = currentSlide.headline;
        formBody.value = currentSlide.body;
        
        if (formStatContainer) {
            if (currentSlide.stat !== undefined && currentSlide.stat !== null) {
                formStatContainer.style.display = "block";
                formStat.value = currentSlide.stat;
            } else {
                formStatContainer.style.display = "none";
                formStat.value = "";
            }
        }
    }

    // Sync from sidebar editor inputs to preview slides
    if (formHeadline) {
        formHeadline.addEventListener("input", (e) => {
            const val = e.target.value;
            carouselData.slides[currentSlideIndex].headline = val;
            const slideEl = document.querySelector(`.preview-slide-wrapper[data-index="${currentSlideIndex}"]`);
            if (slideEl) {
                const hl = slideEl.querySelector(".headline");
                if (hl) hl.textContent = val;
            }
        });
    }

    if (formBody) {
        formBody.addEventListener("input", (e) => {
            const val = e.target.value;
            carouselData.slides[currentSlideIndex].body = val;
            const slideEl = document.querySelector(`.preview-slide-wrapper[data-index="${currentSlideIndex}"]`);
            if (slideEl) {
                const bdy = slideEl.querySelector(".body-text");
                if (bdy) bdy.textContent = val;
            }
        });
    }

    if (formStat) {
        formStat.addEventListener("input", (e) => {
            const val = e.target.value;
            carouselData.slides[currentSlideIndex].stat = val;
            const slideEl = document.querySelector(`.preview-slide-wrapper[data-index="${currentSlideIndex}"]`);
            if (slideEl) {
                const statVal = slideEl.querySelector(".stat-value");
                if (statVal) statVal.textContent = val;
            }
        });
    }

    // Save/Update Slide Copy via API call to maintain persistence in filesystem
    const saveChangesBtn = document.getElementById("save-changes-btn");
    if (saveChangesBtn) {
        saveChangesBtn.addEventListener("click", async () => {
            const generationId = document.getElementById("generation_id").value;
            const format = document.getElementById("format-selector").value;
            showLoading("Saving slide updates...");

            try {
                const response = await fetch("/api/save-slide-edits", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify({
                        generation_id: generationId,
                        slides: carouselData.slides,
                        format: format
                    })
                });

                if (!response.ok) throw new Error("Failed to save changes.");
                alert("Slide edits saved successfully!");
            } catch (err) {
                alert(`Error: ${err.message}`);
            } finally {
                hideLoading();
            }
        });
    }

    // Playwright PDF Export Trigger
    const exportPdfBtn = document.getElementById("export-pdf-btn");
    if (exportPdfBtn) {
        exportPdfBtn.addEventListener("click", async () => {
            const generationId = document.getElementById("generation_id").value;
            const format = document.getElementById("format-selector").value;

            // Trigger save first to ensure PDF renders the current screen inputs
            showLoading("Rendering and generating PDF document (Stage 4)...");

            try {
                // 1. Save state
                await fetch("/api/save-slide-edits", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify({
                        generation_id: generationId,
                        slides: carouselData.slides,
                        format: format
                    })
                });

                // 2. Request PDF download URL
                window.location.href = `/generation/${generationId}/download?format=${format}`;
            } catch (err) {
                alert(`PDF export error: ${err.message}`);
            } finally {
                // The browser download will happen asynchronously, hide loader after a short timeout
                setTimeout(hideLoading, 3000);
            }
        });
    }

    // Parallel Slide Copy Regeneration (OpenRouter slide-level copy update)
    const regenSlideBtn = document.getElementById("regen-slide-copy-btn");
    if (regenSlideBtn) {
        regenSlideBtn.addEventListener("click", async () => {
            const generationId = document.getElementById("generation_id").value;
            const model = document.getElementById("stage2_model").value;
            const currentSlide = carouselData.slides[currentSlideIndex];

            const instruction = prompt(`Enter instructions to rewrite Slide ${currentSlideIndex + 1} (${currentSlide.job}):`);
            if (instruction === null) return;

            showLoading(`Regenerating copy for Slide ${currentSlideIndex + 1}...`);

            try {
                const response = await fetch("/api/regenerate-slide-copy", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify({
                        generation_id: generationId,
                        slide_index: currentSlideIndex,
                        tweak_instruction: instruction,
                        model: model
                    })
                });

                if (!response.ok) throw new Error("Failed to regenerate slide copy.");

                const data = await response.json();
                
                // Update local dataset
                carouselData.slides[currentSlideIndex].headline = data.headline;
                carouselData.slides[currentSlideIndex].body = data.body;
                if (data.stat !== undefined) {
                    carouselData.slides[currentSlideIndex].stat = data.stat;
                }

                // Update UI preview card elements
                const slideEl = document.querySelector(`.preview-slide-wrapper[data-index="${currentSlideIndex}"]`);
                if (slideEl) {
                    const hl = slideEl.querySelector(".headline");
                    const bdy = slideEl.querySelector(".body-text");
                    const statVal = slideEl.querySelector(".stat-value");

                    if (hl) hl.textContent = data.headline;
                    if (bdy) bdy.textContent = data.body;
                    if (statVal && data.stat) statVal.textContent = data.stat;
                }

                // Update active sidebar text fields
                updateEditorPane();
            } catch (err) {
                alert(`Error: ${err.message}`);
            } finally {
                hideLoading();
            }
        });
    }

    // Set initial position
    updateCarouselPosition();
}

function updateCarouselPosition() {
    const track = document.getElementById("carousel-track");
    const indicatorText = document.getElementById("slide-indicator-text");
    const prevBtn = document.getElementById("prev-slide");
    const nextBtn = document.getElementById("next-slide");

    if (!track) return;

    // Show/hide correct slide wrapper using display or sliding transform
    const slides = document.querySelectorAll(".preview-slide-wrapper");
    slides.forEach((slide, idx) => {
        if (idx === currentSlideIndex) {
            slide.style.display = "flex";
        } else {
            slide.style.display = "none";
        }
    });

    // Update indicator dots and buttons
    if (indicatorText) {
        indicatorText.textContent = `Slide ${currentSlideIndex + 1} of ${totalSlides}`;
    }

    if (prevBtn) prevBtn.disabled = (currentSlideIndex === 0);
    if (nextBtn) nextBtn.disabled = (currentSlideIndex === totalSlides - 1);

    // Update dot active styling
    const dots = document.querySelectorAll(".dot");
    dots.forEach((dot, idx) => {
        if (idx === currentSlideIndex) {
            dot.classList.add("active");
        } else {
            dot.classList.remove("active");
        }
    });

    // Update the input editors for this slide
    const formHeadline = document.getElementById("editor-headline");
    const formBody = document.getElementById("editor-body");
    const formStat = document.getElementById("editor-stat");
    const formStatContainer = document.getElementById("editor-stat-container");

    if (formHeadline && carouselData.slides) {
        const slide = carouselData.slides[currentSlideIndex];
        formHeadline.value = slide.headline || "";
        formBody.value = slide.body || "";
        if (formStatContainer) {
            if (slide.stat !== undefined && slide.stat !== null) {
                formStatContainer.style.display = "block";
                formStat.value = slide.stat;
            } else {
                formStatContainer.style.display = "none";
                formStat.value = "";
            }
        }
    }
}
