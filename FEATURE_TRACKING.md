# Marker Feature Tracking & Customization Log

**Project:** Marker PDF Conversion Pipeline  
**Date Started:** October 7, 2025  
**Goal:** Track custom features, local LLM integration, and pipeline modifications

---

## Current Status

### ✅ Built-In Features (Already Available)

#### Local LLM Support
- **Status:** ✅ CONFIGURED & READY (October 8, 2025)
- **Service:** Ollama (`marker/services/ollama.py`)
- **Usage:** `--use_llm --llm_service=marker.services.ollama.OllamaService`
- **Default Model:** `qwen2.5vl:7b-32k` (custom 32K context, 6GB)
- **Available Models:**
  - `qwen2.5vl:7b-32k` ✅ **RECOMMENDED** - 32K context, fast inference
  - `qwen2.5vl:7b` - Original 4K context (limited)
  - `qwen2.5vl:32b` - Larger model, 4K context
- **Base URL:** `http://ollama:11434` (Docker container-to-container)
- **Network:** `postgresql_rag_network` (shared with Ollama container)

#### LLM Service Options
- [x] Ollama (Local) - `marker.services.ollama.OllamaService`
- [x] OpenAI - `marker.services.openai.OpenAIService`
- [x] Azure OpenAI - `marker.services.azure_openai.AzureOpenAIService`
- [x] Claude - `marker.services.claude.ClaudeService`
- [x] Gemini (default) - `marker.services.gemini.GoogleGeminiService`
- [x] Google Vertex - `marker.services.vertex.GoogleVertexService`

---

## 🎉 Implementation Completed: October 8, 2025

### Changes Made for Ollama Container Integration

#### 1. Fixed Ollama Service Defaults (`marker/services/ollama.py`)
- ✅ Changed default model: `llama3.2-vision` → `qwen2.5vl:7b`
  - Reason: `llama3.2-vision` doesn't exist; using actual downloaded model
  - Available models: `qwen2.5vl:7b` (6GB) and `qwen2.5vl:32b` (21GB)
- ✅ Changed default URL: `http://localhost:11434` → `http://ollama:11434`
  - Reason: Container-to-container communication uses container name as hostname
  - Works seamlessly within Docker network

#### 2. Fixed Server API (`marker/scripts/server.py`)
- ✅ Fixed `LLMService` enum to use actual service class paths
  - Before: `ollama_local = "ollama_local"` (invalid)
  - After: `ollama = "marker.services.ollama.OllamaService"` (valid import path)
- ✅ Added `llm_service` parameter passing in options builder
  - Now properly passes service selection from API to converter
  - Enables `/marker/upload` endpoint to use Ollama

#### 3. Network Configuration (`docker-compose.yml`)
- ✅ Connected all marker services to `postgresql_rag_network`
  - `marker-dev-open`: Added network + `OLLAMA_BASE_URL` env var
  - `marker-dev-secure`: Added network + `OLLAMA_BASE_URL` env var
  - `marker-secure-production-v1`: Added network + `OLLAMA_BASE_URL` env var
- ✅ Declared `postgresql_rag_network` as external
  - Reuses existing network from Ollama container setup
  - Enables seamless container-to-container communication

### Container Network Architecture

```
postgresql_rag_network (172.20.0.0/16)
├── ollama (172.20.0.5)           ← Already running
├── marker-dev-open               ← Now connected
├── marker-dev-secure             ← Now connected
├── marker-secure-production-v1   ← Now connected
├── rag_db (PostgreSQL)
├── llamaindex-rag
├── pgadmin_secure
└── open-webui
```

### Usage Examples

#### CLI Usage (from host):
```bash
marker input.pdf output/ \
  --use_llm \
  --llm_service=marker.services.ollama.OllamaService \
  --ollama_base_url=http://localhost:11434 \
  --ollama_model=qwen2.5vl:7b
```

#### API Usage (via FastAPI):
```bash
curl -X POST http://localhost:8000/marker/upload \
  -F "file=@input.pdf" \
  -F "use_llm=true" \
  -F "llm_service=ollama" \
  -F "output_format=markdown"
```

#### Docker Compose Startup:
```bash
# Dev mode with LLM access
docker compose --profile dev-secure up

# In another terminal, test the API
curl http://localhost:8000/docs
```

### Testing Checklist

- [ ] Start marker container: `docker compose --profile dev-secure up`
- [ ] Verify Ollama connectivity: `docker exec marker3-dev-secure curl http://ollama:11434/api/version`
- [ ] Test API with use_llm=true via Swagger UI at `http://localhost:8000/docs`
- [ ] Compare output quality: with LLM vs without
- [ ] Monitor VRAM usage during LLM processing
- [ ] Test all LLM processors (tables, images, equations, etc.)

---

## 🎉 Selective LLM Processor Configuration (October 8, 2025)

### New Feature: Per-Processor Control via JSON Config

**Problem Solved:** The 7B vision model (`qwen2.5vl:7b`) has a 4096 token limit, causing truncation with high-context processors like image descriptions and page correction.

**Solution:** JSON config files with boolean toggles for each LLM processor!

### Example Configurations

**1. Optimized for 7B Model with 32K Context** (`llm_config_optimized_7b.json`)
```json
{
  "use_llm": true,
  "ollama_model": "qwen2.5vl:7b-32k",  // Custom model with 32K context!
  
  "enable_llm_table": true,              // ✅ High value
  "enable_llm_table_merge": true,         // ✅ Lightweight
  "enable_llm_form": true,                // ✅ Useful for medical docs
  "enable_llm_equation": true,            // ✅ Moderate context
  "enable_llm_mathblock": true,           // ✅ Low context
  "enable_llm_section_header": true,      // ✅ Low context
  
  "enable_llm_image_description": false,  // ❌ Huge context (exceeds 4096)
  "enable_llm_page_correction": false,    // ❌ Huge context (exceeds 4096)
  "enable_llm_complex_region": false,     // ❌ Large context
  "enable_llm_handwriting": false         // ❌ Optional, save budget
}
```

**2. Full-Featured for 32B Model** (`llm_config_full_32b.json`)
- All processors enabled
- Uses `qwen2.5vl:32b` with larger context window
- Best quality, slower processing

**3. Baseline No-LLM** (`llm_config_disabled.json`)
- `use_llm: false`
- For speed comparison

### Usage

**Via CLI:**
```bash
marker input.pdf output/ --config_json=llm_config_optimized_7b.json
```

**Via API:**
```bash
curl -X POST http://localhost:1111/marker/upload \
  -F "file=@input.pdf" \
  -F "config_json=@llm_config_optimized_7b.json"
```

**Edit configs directly:**
```bash
# Copy and customize
cp llm_config_optimized_7b.json my_config.json
# Edit my_config.json with your preferences
# Restart container to pick up code changes
docker compose --profile secure-production-v1 restart
```

### Configuration Options

All LLM processor toggles (only apply when `use_llm=true`):

| Config Key | Processor | Context Usage | Recommended for 7B |
|-----------|-----------|---------------|-------------------|
| `enable_llm_table` | Table extraction | Medium | ✅ Yes |
| `enable_llm_table_merge` | Multi-page tables | Low | ✅ Yes |
| `enable_llm_form` | Form fields | Medium | ✅ Yes |
| `enable_llm_equation` | LaTeX equations | Medium | ✅ Yes |
| `enable_llm_mathblock` | Inline math | Low | ✅ Yes |
| `enable_llm_section_header` | Headers | Low | ✅ Yes |
| `enable_llm_image_description` | Alt-text | **Very High** | ❌ No (use 32B) |
| `enable_llm_page_correction` | Page layout | **Very High** | ❌ No (use 32B) |
| `enable_llm_complex_region` | Nested layouts | High | ❌ No (use 32B) |
| `enable_llm_handwriting` | Handwritten text | Medium | ⚠️ Optional |

**Default:** All processors enabled (True) - you disable what you don't want

---

## LLM Feature Matrix

### LLM Processors (Incremental Control)

All processors respect the `--use_llm` flag. When disabled, they skip execution.
**NEW:** Individual processors can now be selectively disabled via JSON config!

| Processor | Enabled by Default | Block Types | Purpose | Status |
|-----------|-------------------|-------------|---------|--------|
| `LLMTableProcessor` | ✅ (if use_llm) | Table, TableOfContents, Form | Improves table cell detection & text extraction | ⚪ Not Modified |
| `LLMTableMergeProcessor` | ✅ (if use_llm) | Table, TableOfContents, Form | Merges split tables across pages | ⚪ Not Modified |
| `LLMFormProcessor` | ✅ (if use_llm) | Form | Enhances form structure & field detection | ⚪ Not Modified |
| `LLMComplexRegionProcessor` | ✅ (if use_llm) | ComplexRegion | Handles nested/complex layouts | ⚪ Not Modified |
| `LLMImageDescriptionProcessor` | ✅ (if use_llm) | Picture, Figure | Generates alt text for images | ⚪ Not Modified |
| `LLMEquationProcessor` | ✅ (if use_llm) | Equation | Improves equation LaTeX output | ⚪ Not Modified |
| `LLMHandwritingProcessor` | ✅ (if use_llm) | Handwriting | OCRs handwritten text | ⚪ Not Modified |
| `LLMMathBlockProcessor` | ✅ (if use_llm) | TextInlineMath | Corrects inline math expressions | ⚪ Not Modified |
| `LLMSectionHeaderProcessor` | ✅ (if use_llm) | SectionHeader | Improves header hierarchy | ⚪ Not Modified |
| `LLMPageCorrectionProcessor` | ✅ (if use_llm) | Page-level | Overall reading order & block type correction | ⚪ Not Modified |

**Concurrency:** `max_concurrency = 3` (configurable per processor)

---

## Non-LLM Core Processors

| Processor | Purpose | Status |
|-----------|---------|--------|
| `OrderProcessor` | Determines reading order | ⚪ Not Modified |
| `BlockRelabelProcessor` | Re-classifies blocks based on heuristics | ⚪ Not Modified |
| `LineMergeProcessor` | Merges fragmented lines (math equations) | ⚪ Not Modified |
| `BlockquoteProcessor` | Detects blockquotes | ⚪ Not Modified |
| `CodeProcessor` | Detects code blocks | ⚪ Not Modified |
| `DocumentTOCProcessor` | Generates table of contents | ⚪ Not Modified |
| `EquationProcessor` | Detects equations | ⚪ Not Modified |
| `FootnoteProcessor` | Handles footnotes | ⚪ Not Modified |
| `IgnoreTextProcessor` | Filters ignorable text | ⚪ Not Modified |
| `LineNumbersProcessor` | Removes line numbers | ⚪ Not Modified |
| `ListProcessor` | Detects lists | ⚪ Not Modified |
| `PageHeaderProcessor` | Removes headers/footers | ⚪ Not Modified |
| `SectionHeaderProcessor` | Detects section headers | ⚪ Not Modified |
| `TableProcessor` | Detects & extracts tables | ⚪ Not Modified |
| `TextProcessor` | Basic text processing | ⚪ Not Modified |
| `ReferenceProcessor` | Handles references | ⚪ Not Modified |
| `BlankPageProcessor` | Removes blank pages | ⚪ Not Modified |
| `DebugProcessor` | Debug output generation | ⚪ Not Modified |

---

## Custom Features To Add

### 🔧 Planned Modifications

#### 1. Custom Local LLM Service
- [ ] Create `marker/services/custom_local.py`
- [ ] Support for local API endpoint (non-Ollama)
- [ ] Custom prompt templates
- [ ] Model: TBD

#### 2. Network Isolation
- [ ] Verify Ollama runs with `--network_mode=none` in Docker
- [ ] Test model pre-loading before network restrictions
- [ ] Document model download workflow
- [ ] Add offline marker/verification

#### 3. Selective LLM Usage
- [ ] Create config to enable specific LLM processors only
- [ ] Example: Use LLM for tables but not for images
- [ ] Fine-tune concurrency per processor for RTX 5090

#### 4. Performance Optimization (RTX 5090)
- [ ] Profile current performance with local models
- [ ] Optimize batch sizes for 32GB VRAM
- [ ] Test throughput with multiple concurrent documents

#### 5. Custom Processors
- [ ] List any domain-specific processors needed
- [ ] Document block types they should target
- [ ] Integration points in pipeline

---

## Configuration Examples

### Basic Local LLM Usage (from host)
```bash
marker input.pdf output/ \
  --use_llm \
  --llm_service=marker.services.ollama.OllamaService \
  --ollama_base_url=http://localhost:11434 \
  --ollama_model=qwen2.5vl:7b
```

### Container-to-Container (automatic with docker-compose)
```bash
# No need to specify URLs - defaults are now correct!
marker input.pdf output/ \
  --use_llm \
  --llm_service=marker.services.ollama.OllamaService
```

### Disable Specific Features
```bash
# Custom processor list (skip LLM image descriptions, for example)
marker input.pdf output/ \
  --use_llm \
  --processors="comma,separated,list,of,processor,classes"
```

### Current Pipeline (Modified Files)
- ✏️ `marker/config/parser.py` - Modified (git status shows)
- ✏️ `marker/scripts/server.py` - Modified (git status shows)

---

## Docker Considerations

### Model Management
- **Phase 1:** Download models WITH network enabled
- **Phase 2:** Apply network restrictions after verification
- Use volumes for model persistence: `/root/.ollama`

### RTX 5090 Requirements
- CUDA 12.8+
- PyTorch 2.7.0+
- Verify compute capability 12.0 support

---

## Testing Checklist

### Local LLM Integration
- [ ] Verify Ollama installation
- [ ] Test model download (qwen2-vl:7b or similar vision model)
- [ ] Run marker with `--use_llm` flag
- [ ] Compare output quality: with LLM vs without
- [ ] Measure throughput on sample PDFs

### Network Isolation
- [ ] Test with network enabled (baseline)
- [ ] Test with network disabled (models pre-loaded)
- [ ] Verify no external calls in logs

### Performance Benchmarks
- [ ] Single page throughput
- [ ] Multi-page document processing
- [ ] VRAM usage monitoring
- [ ] Optimal concurrency settings

---

## Notes & Observations

### System Architecture Insights
- **Layout Detection:** Single-pass, not recursive - layout blocks are flat
- **Nested Structure:** Created by processors AFTER layout (e.g., TableCells added to Tables)
- **Overlap Handling:** Uses intersection matrices, "max intersection wins" strategy
- **LLM Injection:** All via dependency injection in `BaseConverter.resolve_dependencies()`

### Known Limitations (from README)
- Very complex layouts with nested tables/forms may not work perfectly
- `--use_llm` + `--force_ocr` solves most issues

### Extensibility Points
1. **Services:** Add new LLM providers in `marker/services/`
2. **Processors:** Add custom processors, inject via `processor_list`
3. **Renderers:** Custom output formats in `marker/renderers/`
4. **Block Types:** Extend schema in `marker/schema/blocks/`

---

## Questions to Resolve

1. Which local model for vision tasks? (qwen2-vl:7b, llava, minicpm-v?)
2. Which LLM features are most valuable for your use case?
3. Network isolation strategy - Docker-level or application-level?
4. Need custom block types for domain-specific content?

---

**Legend:**
- ✅ Available/Implemented
- ⚪ Not Modified (default)
- ✏️ Modified
- 🔧 Planned
- ❌ Disabled
- 🚧 In Progress
