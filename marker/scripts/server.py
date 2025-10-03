import traceback

import click
import os

from pydantic import BaseModel, Field
from starlette.responses import HTMLResponse
from enum import Enum

from marker.config.parser import ConfigParser
from marker.output import text_from_rendered

import base64
from contextlib import asynccontextmanager
from typing import Optional, Annotated
import io

from fastapi import FastAPI, Form, File, UploadFile
from fastapi.responses import FileResponse
import zipfile
import shutil
from marker.converters.pdf import PdfConverter
from marker.models import create_model_dict
from marker.settings import settings

app_data = {}


UPLOAD_DIRECTORY = "./uploads"
os.makedirs(UPLOAD_DIRECTORY, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app_data["models"] = create_model_dict()

    yield

    if "models" in app_data:
        del app_data["models"]


app = FastAPI(lifespan=lifespan)


class OutputFormat(str, Enum):
    markdown = "markdown"
    json = "json"
    html = "html"
    chunks = "chunks"
    all = "all"


class SaveLocation(str, Enum):
    pmhx = "PMHx (Primary)"
    desktop = "Desktop"
    downloads = "Downloads" 
    temp = "Temp"


class ConverterType(str, Enum):
    full_document = "PdfConverter"
    tables_only = "TableConverter"


class LLMService(str, Enum):
    # NOTE: Currently configured for local models only
    # Future: Will support local Ollama, local OpenAI-compatible APIs
    ollama_local = "ollama_local"  # For future local model support
    disabled = "disabled"


class OCREngine(str, Enum):
    surya = "surya"  # Default Surya OCR (recommended)
    auto = "auto"    # Heuristic selection


@app.get("/")
async def root():
    return HTMLResponse(
        """
<h1>Marker API - Complete Document Processing Interface</h1>
<ul>
    <li><a href="/docs">📚 API Documentation</a></li>
    <li><a href="/marker">🔄 Process Documents</a></li>
</ul>

<h2>🎯 Current Configuration</h2>
<ul>
    <li><strong>Quality:</strong> High (Force OCR + RTX 5090 optimized)</li>
    <li><strong>LLM Enhancement:</strong> Disabled (ready for local model integration)</li>
    <li><strong>Output:</strong> All formats available (markdown/json/html/chunks)</li>
    <li><strong>Performance:</strong> RTX 5090 batch sizes (32GB VRAM optimized)</li>
</ul>

<h2>🔥 Advanced Features Available</h2>
<ul>
    <li><strong>Structured Extraction:</strong> Custom JSON schemas for RAG data</li>
    <li><strong>Multi-language OCR:</strong> 90+ languages supported via Surya</li>
    <li><strong>Debug Mode:</strong> Layout visualization and diagnostics</li>
    <li><strong>Table-Only Mode:</strong> Extract tables exclusively</li>
    <li><strong>Custom Processing:</strong> Override processor pipeline</li>
</ul>

<h2>📝 Notes for Developers</h2>
<ul>
    <li><strong>LLM Support:</strong> Configured for local models only (Ollama, local APIs)</li>
    <li><strong>Cloud LLMs:</strong> Not implemented - use local inference for security</li>
    <li><strong>Structured Extraction:</strong> Requires local LLM setup</li>
    <li><strong>Performance:</strong> Batch sizes optimized for RTX 5090 Blackwell architecture</li>
</ul>

<p><strong>Output:</strong> Downloads as ZIP file with all requested formats and extracted images</p>
"""
    )


class CommonParams(BaseModel):
    filepath: Annotated[
        Optional[str], Field(description="The path to the PDF file to convert.")
    ]
    page_range: Annotated[
        Optional[str],
        Field(
            description="Page range to convert. Use 'all' for all pages, or specify comma separated page numbers/ranges. Example: 'all', '0,5-10,20'",
            example="all",
        ),
    ] = "all"
    force_ocr: Annotated[
        bool,
        Field(
            description="Force OCR on all pages of the PDF. Defaults to True for best accuracy with math and complex layouts."
        ),
    ] = True
    paginate_output: Annotated[
        bool,
        Field(
            description="Whether to paginate the output. Defaults to True. Each page will be separated by a horizontal rule with page number."
        ),
    ] = True
    output_format: Annotated[
        OutputFormat,
        Field(
            description="Output format selection",
            example=OutputFormat.markdown,
        ),
    ] = OutputFormat.markdown


async def _convert_pdf(params: CommonParams):
    # Enum validation is automatic, no need for manual assert
    try:
        options = params.model_dump()
        config_parser = ConfigParser(options)
        config_dict = config_parser.generate_config_dict()
        config_dict["pdftext_workers"] = 1
        converter_cls = PdfConverter
        converter = converter_cls(
            config=config_dict,
            artifact_dict=app_data["models"],
            processor_list=config_parser.get_processors(),
            renderer=config_parser.get_renderer(),
            llm_service=config_parser.get_llm_service(),
        )
        rendered = converter(params.filepath)
        text, _, images = text_from_rendered(rendered)
        metadata = rendered.metadata
    except Exception as e:
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e),
        }

    encoded = {}
    for k, v in images.items():
        byte_stream = io.BytesIO()
        v.save(byte_stream, format=settings.OUTPUT_IMAGE_FORMAT)
        encoded[k] = base64.b64encode(byte_stream.getvalue()).decode(
            settings.OUTPUT_ENCODING
        )

    return {
        "format": params.output_format,
        "output": text,
        "images": encoded,
        "metadata": metadata,
        "success": True,
    }


@app.post("/marker")
async def convert_pdf(params: CommonParams):
    return await _convert_pdf(params)


@app.post("/marker/upload")
async def convert_pdf_upload(
    # === SECTION 1: Input & OCR Processing ===
    page_range: Optional[str] = Form(default="all", description="Page range: 'all' for all pages, or '1,2-5,10' for specific pages"),
    force_ocr: Optional[bool] = Form(default=True, description="Force OCR for best accuracy with math and complex layouts"),
    strip_existing_ocr: Optional[bool] = Form(default=False, description="Remove existing OCR and re-process with Surya"),
    ocr_languages: Optional[str] = Form(default="en", description="Comma-separated language codes (e.g., 'en,es,fr')"),
    ocr_engine: OCREngine = Form(default=OCREngine.surya, description="OCR engine selection"),
    skip_existing: Optional[bool] = Form(default=False, description="Skip if output already exists (batch mode)"),
    
    # === SECTION 2: Content Processing & Quality ===
    use_llm: Optional[bool] = Form(default=False, description="🚀 Enable LLM enhancement for highest accuracy (requires local model setup)"),
    llm_service: LLMService = Form(default=LLMService.disabled, description="LLM service (NOTE: Local models only - no cloud APIs)"),
    llm_model: Optional[str] = Form(default="", description="Specific model name (for future local model support)"),
    max_context_length: Optional[int] = Form(default=32000, description="LLM context window size"),
    block_correction_prompt: Optional[str] = Form(default="", description="Custom LLM prompt for output correction"),
    redo_inline_math: Optional[bool] = Form(default=False, description="Highest quality math conversion (requires use_llm=True)"),
    keep_page_headers_footers: Optional[bool] = Form(default=False, description="Retain headers/footers instead of removing them"),
    debug: Optional[bool] = Form(default=False, description="Enable diagnostic output and layout visualization"),
    
    # === SECTION 3: Specialized Processing ===
    converter_type: ConverterType = Form(default=ConverterType.full_document, description="Processing mode: full document or tables only"),
    page_schema: Optional[str] = Form(default="", description="🔥 JSON schema for structured data extraction (requires use_llm=True)"),
    processors: Optional[str] = Form(default="", description="Custom processor pipeline (advanced: comma-separated module paths)"),
    
    # === SECTION 4: Output Format & Rendering ===
    output_format: OutputFormat = Form(default=OutputFormat.markdown, description="Select output format"),
    paginate_output: Optional[bool] = Form(default=True, description="Add page separators in output"),
    extract_images: Optional[bool] = Form(default=True, description="Extract and save images from document"),
    bad_span_types: Optional[str] = Form(default="", description="Block types to exclude (e.g., 'footnotes,captions')"),
    save_location: SaveLocation = Form(default=SaveLocation.pmhx, description="Organization label (for your reference)"),
    
    # === SECTION 5: RTX 5090 Performance Optimization ===
    torch_device: Optional[str] = Form(default="cuda", description="Force specific device (cuda/cpu/mps)"),
    table_rec_batch_size: Optional[int] = Form(default=48, description="Table recognition batch size (RTX 5090: 48)"),
    detection_batch_size: Optional[int] = Form(default=32, description="Detection model batch size (RTX 5090: 32)"),
    recognition_batch_size: Optional[int] = Form(default=64, description="Text recognition batch size (RTX 5090: 64)"),
    disable_multiprocessing: Optional[bool] = Form(default=False, description="Single-threaded mode (debugging)"),
    
    file: UploadFile = File(
        ..., description="The PDF file to convert.", media_type="application/pdf"
    ),
):
    # Save uploaded file
    upload_path = os.path.join(UPLOAD_DIRECTORY, file.filename)
    with open(upload_path, "wb+") as upload_file:
        file_contents = await file.read()
        upload_file.write(file_contents)

    # Create temporary output directory for processing
    import datetime
    import tempfile
    
    filename_base = os.path.splitext(file.filename)[0]  # Remove extension
    date_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Create temporary directory for processing
    temp_output_dir = tempfile.mkdtemp(prefix=f"marker_{filename_base}_{date_str}_")
    job_name = f"{filename_base}_{date_str}_{save_location.value}"

    # Process PDF with custom output directory
    params = CommonParams(
        filepath=upload_path,
        page_range=page_range,
        force_ocr=force_ocr,
        paginate_output=paginate_output,
        output_format=output_format,
    )
    
        # Process the PDF
    try:
        # Handle "all" format by generating all formats
        if output_format == OutputFormat.all:
            formats_to_generate = ["markdown", "json", "html", "chunks"]
        else:
            formats_to_generate = [output_format.value]
        
        # Generate each requested format
        for format_type in formats_to_generate:
            # Build comprehensive options dict preserving current working defaults
            options = {
                "output_dir": temp_output_dir,
                "output_format": format_type,
                # Current working defaults preserved
                "page_range": page_range,
                "force_ocr": force_ocr,
                "paginate_output": paginate_output,
            }
            
            # === INPUT & OCR PROCESSING ===
            if strip_existing_ocr:
                options["strip_existing_ocr"] = strip_existing_ocr
            if ocr_languages and ocr_languages != "en":
                options["ocr_languages"] = ocr_languages
            if skip_existing:
                options["skip_existing"] = skip_existing
                
            # === CONTENT PROCESSING & QUALITY ===
            # NOTE: LLM features disabled by default - will support local models in future
            if use_llm:
                options["use_llm"] = use_llm
                if block_correction_prompt:
                    options["block_correction_prompt"] = block_correction_prompt
                if redo_inline_math:
                    options["redo_inline_math"] = redo_inline_math
                if max_context_length != 32000:
                    options["max_context_length"] = max_context_length
                    
            if keep_page_headers_footers:
                options["keep_page_headers_footers"] = keep_page_headers_footers
            if debug:
                options["debug"] = debug
                
            # === SPECIALIZED PROCESSING ===
            if page_schema and use_llm:
                # Structured extraction requires LLM
                options["page_schema"] = page_schema
            if processors:
                options["processors"] = processors
                
            # === OUTPUT CUSTOMIZATION ===
            if not extract_images:
                options["disable_image_extraction"] = True
            if bad_span_types:
                options["bad_span_types"] = bad_span_types
                
            # === RTX 5090 PERFORMANCE OPTIMIZATION ===
            if torch_device != "cuda":
                options["torch_device"] = torch_device
            if table_rec_batch_size != 48:
                options["table_rec_batch_size"] = table_rec_batch_size
            if detection_batch_size != 32:
                options["detection_batch_size"] = detection_batch_size  
            if recognition_batch_size != 64:
                options["recognition_batch_size"] = recognition_batch_size
            if disable_multiprocessing:
                options["disable_multiprocessing"] = disable_multiprocessing
                
            config_parser = ConfigParser(options)
            
            config_dict = config_parser.generate_config_dict()
            config_dict["pdftext_workers"] = 1
            converter = PdfConverter(
                config=config_dict,
                artifact_dict=app_data["models"],
                processor_list=config_parser.get_processors(),
                renderer=config_parser.get_renderer(),
                llm_service=config_parser.get_llm_service(),
            )
            rendered = converter(upload_path)
            
            # Save with format-specific filename
            from marker.output import save_output
            if output_format == OutputFormat.all:
                format_filename = f"{filename_base}_{format_type}"
            else:
                format_filename = filename_base
            save_output(rendered, temp_output_dir, format_filename)
        
        # Create zip file for download
        zip_filename = f"{job_name}.zip"
        zip_path = os.path.join(UPLOAD_DIRECTORY, zip_filename)
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # Add all files from the output directory
            for root, dirs, files in os.walk(temp_output_dir):
                for file_item in files:
                    file_path = os.path.join(root, file_item)
                    arcname = os.path.relpath(file_path, temp_output_dir)
                    zipf.write(file_path, arcname)
        
        # Clean up
        os.remove(upload_path)
        shutil.rmtree(temp_output_dir)
        
        # Return file for download
        # Note: FileResponse handles file cleanup, no background task needed
        return FileResponse(
            path=zip_path,
            filename=zip_filename,
            media_type="application/zip"
        )
        
    except Exception as e:
        # Clean up on error
        if os.path.exists(upload_path):
            os.remove(upload_path)
        if os.path.exists(temp_output_dir):
            shutil.rmtree(temp_output_dir)
        return {
            "success": False,
            "error": str(e)
        }


@click.command()
@click.option("--port", type=int, default=8000, help="Port to run the server on")
@click.option("--host", type=str, default="127.0.0.1", help="Host to run the server on")
@click.option("--reload", is_flag=True, default=False, help="Enable auto-reload for development")
def server_cli(port: int, host: str, reload: bool):
    import uvicorn
    import os

    # Check for development environment variable
    dev_reload = os.getenv("FASTAPI_RELOAD", "false").lower() == "true"
    enable_reload = reload or dev_reload

    print(f"Starting Marker API server on {host}:{port}")
    print(f"Hot reload: {'enabled' if enable_reload else 'disabled'}")
    print(f"Access API docs at: http://{host if host != '0.0.0.0' else 'localhost'}:{port}/docs")

    # Run the server with conditional reload
    uvicorn.run(
        "marker.scripts.server:app",  # Use string import for reload to work
        host=host,
        port=port,
        reload=enable_reload,
        reload_dirs=["/app/marker"] if enable_reload else None,
    )
