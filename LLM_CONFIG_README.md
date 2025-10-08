# LLM Processor Configuration Guide

## Quick Start

Three pre-configured profiles are provided:

### 1. `llm_config_optimized_7b.json` (Recommended)
- **Model:** `qwen2.5vl:7b` (fast, 6GB)
- **Best for:** Medical documents, tables, forms
- **Disabled:** Image descriptions, page correction (high context usage)
- **Performance:** ~3-4 minutes per page with LLM
- **Memory:** ~7.4 GB VRAM

### 2. `llm_config_full_32b.json` (Maximum Quality)
- **Model:** `qwen2.5vl:32b` (slow, 21GB)
- **Best for:** Complex documents requiring perfect accuracy
- **Enabled:** All LLM processors
- **Performance:** ~5-10 minutes per page with LLM
- **Memory:** ~22 GB VRAM

### 3. `llm_config_disabled.json` (Baseline)
- **Model:** None (LLM disabled)
- **Best for:** Speed testing, simple documents
- **Performance:** ~30 seconds per page
- **Memory:** ~5-6 GB VRAM (just marker models)

## Usage

### Via Docker Compose + API

```bash
# 1. Start container
docker compose --profile secure-production-v1 up

# 2. Upload PDF with config via API (http://localhost:1111/docs)
# In the Swagger UI:
# - Upload your PDF file
# - Set config_json parameter to the config file path in container
# - Or paste JSON directly into a text field if API supports it

# 3. Via curl
curl -X POST http://localhost:1111/marker/upload \
  -F "file=@document.pdf" \
  -F "use_llm=true" \
  -F "enable_llm_table=true" \
  -F "enable_llm_image_description=false" \
  -F "ollama_model=qwen2.5vl:7b"
```

### Via CLI (if running marker directly)

```bash
marker document.pdf output/ --config_json=llm_config_optimized_7b.json
```

## Customization

### Create Your Own Config

```bash
# Copy a template
cp llm_config_optimized_7b.json my_custom_config.json

# Edit with your preferences
nano my_custom_config.json
```

### Configuration Options

#### LLM Processor Toggles

All toggles default to `true` when `use_llm=true`. Set to `false` to disable:

```json
{
  "use_llm": true,
  
  "enable_llm_table": true,              // Table extraction quality
  "enable_llm_table_merge": true,         // Multi-page table merging
  "enable_llm_form": true,                // Form field detection
  "enable_llm_equation": true,            // LaTeX equation improvement
  "enable_llm_mathblock": true,           // Inline math correction
  "enable_llm_section_header": true,      // Header hierarchy
  "enable_llm_image_description": false,  // Alt-text (HIGH CONTEXT)
  "enable_llm_page_correction": false,    // Page-level correction (HIGH CONTEXT)
  "enable_llm_complex_region": false,     // Complex nested layouts
  "enable_llm_handwriting": false         // Handwriting OCR
}
```

#### Model Selection

```json
{
  "ollama_model": "qwen2.5vl:7b",  // or "qwen2.5vl:32b"
  "ollama_base_url": "http://ollama:11434"
}
```

#### Other Common Options

```json
{
  "force_ocr": true,          // Recommended for quality
  "paginate_output": true,    // Page separators in output
  "extract_images": true,     // Extract images from PDF
  "debug": false              // Enable debug output
}
```

## Context Budget Guidelines

### Why Some Processors Are Disabled for 7B Model

The 7B model has a **4096 token context limit**. Image-heavy processors can exceed this:

| Processor | Typical Tokens | 7B Compatible? |
|-----------|---------------|----------------|
| Table | 500-2000 | ✅ Yes |
| Form | 300-1500 | ✅ Yes |
| Equation | 200-800 | ✅ Yes |
| Section Header | 100-400 | ✅ Yes |
| **Image Description** | **3000-6000** | ❌ No (use 32B) |
| **Page Correction** | **4000-8000** | ❌ No (use 32B) |
| Complex Region | 1500-4000 | ⚠️ Borderline |

### Optimization Strategy

For 7B model, prioritize **high-value, low-context** processors:
1. ✅ Keep: Tables, forms, equations (your main use case)
2. ❌ Disable: Image descriptions, page correction (exceed limit)
3. ⚠️ Test: Complex region, handwriting (optional features)

## Troubleshooting

### Ollama Errors: "truncating input prompt"

**Symptom:** Ollama logs show truncation warnings, JSON parse errors

**Solution:**
1. Use `llm_config_optimized_7b.json` (disables high-context processors)
2. OR upgrade to 32B model with `llm_config_full_32b.json`

### 500 Server Errors

**Check Ollama logs:**
```bash
docker logs ollama --tail 50
```

Common causes:
- Context overflow (use optimized config)
- Model not loaded (check `docker exec ollama ollama list`)
- Out of VRAM (reduce batch size or use smaller model)

### Container Restart Needed?

**Yes, restart when:**
- Changing code in production mode (read-only volumes)
- Changing default model in `ollama.py`

**No restart needed when:**
- Using JSON config files (passed per-request)
- Running in dev-secure mode with live volumes

```bash
docker compose --profile secure-production-v1 restart
```

## Performance Comparison

### Test Document: 10-page medical record with tables

| Config | Model | Time | Quality | VRAM |
|--------|-------|------|---------|------|
| Disabled | N/A | 5 min | Baseline | 5 GB |
| Optimized 7B | qwen2.5vl:7b | 35 min | Excellent tables | 7 GB |
| Full 32B | qwen2.5vl:32b | 80 min | Maximum | 22 GB |

**Recommendation:** Start with optimized 7B config for best balance of speed and quality.

## Questions?

See `FEATURE_TRACKING.md` for full documentation of the LLM integration.

