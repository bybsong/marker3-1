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


class SaveLocation(str, Enum):
    pmhx = "PMHx (Primary)"
    desktop = "Desktop"
    downloads = "Downloads" 
    temp = "Temp"


@app.get("/")
async def root():
    return HTMLResponse(
        """
<h1>Marker API</h1>
<ul>
    <li><a href="/docs">API Documentation</a></li>
    <li><a href="/marker">Run marker (post request only)</a></li>
</ul>
<p><strong>Default Settings:</strong></p>
<ul>
    <li>Page Range: All pages</li>
    <li>Force OCR: True (best accuracy)</li>
    <li>Paginate Output: True</li>
    <li>Output Format: Markdown (dropdown selection)</li>
    <li>Save Location: Organization label (for your reference)</li>
</ul>
<p><strong>Output:</strong> Downloads as ZIP file named filename_date_time_location.zip</p>
<p><strong>Example:</strong> TDTest_20250930_143022_PMHx.zip</p>
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
    page_range: Optional[str] = Form(default="all", description="Page range: 'all' for all pages, or '1,2-5,10' for specific pages"),
    force_ocr: Optional[bool] = Form(default=True, description="Force OCR for best accuracy with math and complex layouts"),
    paginate_output: Optional[bool] = Form(default=True, description="Add page separators in output"),
    output_format: OutputFormat = Form(default=OutputFormat.markdown, description="Select output format"),
    save_location: SaveLocation = Form(default=SaveLocation.pmhx, description="Choose output organization (for your reference)"),
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
        # Override the output directory in the config
        options = params.model_dump()
        options["output_dir"] = temp_output_dir
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
        
        # Save to temporary directory
        from marker.output import save_output
        save_output(rendered, temp_output_dir, filename_base)
        
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
        import shutil
        shutil.rmtree(temp_output_dir)
        
        # Return file for download
        return FileResponse(
            path=zip_path,
            filename=zip_filename,
            media_type="application/zip",
            background=lambda: os.remove(zip_path)  # Clean up after download
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
