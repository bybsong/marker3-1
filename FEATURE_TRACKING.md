# Marker Feature Tracking & Customization Log

**Project:** Marker PDF Conversion Pipeline  
**Date Started:** October 7, 2025  
**Goal:** Track custom features, local LLM integration, and pipeline modifications

---

## Current Status

### ✅ Built-In Features (Already Available)

#### Local LLM Support
- **Status:** ✅ ALREADY IMPLEMENTED
- **Service:** Ollama (`marker/services/ollama.py`)
- **Usage:** `--use_llm --llm_service=marker.services.ollama.OllamaService`
- **Default Model:** `llama3.2-vision`
- **Base URL:** `http://localhost:11434`

#### LLM Service Options
- [x] Ollama (Local) - `marker.services.ollama.OllamaService`
- [x] OpenAI - `marker.services.openai.OpenAIService`
- [x] Azure OpenAI - `marker.services.azure_openai.AzureOpenAIService`
- [x] Claude - `marker.services.claude.ClaudeService`
- [x] Gemini (default) - `marker.services.gemini.GoogleGeminiService`
- [x] Google Vertex - `marker.services.vertex.GoogleVertexService`

---

## LLM Feature Matrix

### LLM Processors (Incremental Control)

All processors respect the `--use_llm` flag. When disabled, they skip execution.

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

### Basic Local LLM Usage
```bash
marker input.pdf output/ \
  --use_llm \
  --llm_service=marker.services.ollama.OllamaService \
  --ollama_base_url=http://localhost:11434 \
  --ollama_model=qwen2-vl:7b
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
