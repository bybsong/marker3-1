import os

from marker.schema.document import Document

os.environ["TOKENIZERS_PARALLELISM"] = "false"  # disables a tokenizers warning

from collections import defaultdict
from typing import Annotated, Any, Dict, List, Optional, Type, Tuple, Union
import io
from contextlib import contextmanager
import tempfile

from marker.processors import BaseProcessor
from marker.services import BaseService
from marker.processors.llm.llm_table_merge import LLMTableMergeProcessor
from marker.providers.registry import provider_from_filepath
from marker.builders.document import DocumentBuilder
from marker.builders.layout import LayoutBuilder
from marker.builders.line import LineBuilder
from marker.builders.ocr import OcrBuilder
from marker.builders.structure import StructureBuilder
from marker.converters import BaseConverter
from marker.processors.blockquote import BlockquoteProcessor
from marker.processors.code import CodeProcessor
from marker.processors.debug import DebugProcessor
from marker.processors.document_toc import DocumentTOCProcessor
from marker.processors.equation import EquationProcessor
from marker.processors.footnote import FootnoteProcessor
from marker.processors.ignoretext import IgnoreTextProcessor
from marker.processors.line_numbers import LineNumbersProcessor
from marker.processors.list import ListProcessor
from marker.processors.llm.llm_complex import LLMComplexRegionProcessor
from marker.processors.llm.llm_form import LLMFormProcessor
from marker.processors.llm.llm_image_description import LLMImageDescriptionProcessor
from marker.processors.llm.llm_table import LLMTableProcessor
from marker.processors.page_header import PageHeaderProcessor
from marker.processors.reference import ReferenceProcessor
from marker.processors.sectionheader import SectionHeaderProcessor
from marker.processors.table import TableProcessor
from marker.processors.text import TextProcessor
from marker.processors.block_relabel import BlockRelabelProcessor
from marker.processors.blank_page import BlankPageProcessor
from marker.processors.llm.llm_equation import LLMEquationProcessor
from marker.renderers.markdown import MarkdownRenderer
from marker.schema import BlockTypes
from marker.schema.blocks import Block
from marker.schema.registry import register_block_class
from marker.util import strings_to_classes
from marker.processors.llm.llm_handwriting import LLMHandwritingProcessor
from marker.processors.order import OrderProcessor
from marker.services.gemini import GoogleGeminiService
from marker.processors.line_merge import LineMergeProcessor
from marker.processors.llm.llm_mathblock import LLMMathBlockProcessor
from marker.processors.llm.llm_page_correction import LLMPageCorrectionProcessor
from marker.processors.llm.llm_sectionheader import LLMSectionHeaderProcessor


class PdfConverter(BaseConverter):
    """
    A converter for processing and rendering PDF files into Markdown, JSON, HTML and other formats.
    """

    override_map: Annotated[
        Dict[BlockTypes, Type[Block]],
        "A mapping to override the default block classes for specific block types.",
        "The keys are `BlockTypes` enum values, representing the types of blocks,",
        "and the values are corresponding `Block` class implementations to use",
        "instead of the defaults.",
    ] = defaultdict()
    use_llm: Annotated[
        bool,
        "Enable higher quality processing with LLMs.",
    ] = False
    # Selective LLM processor toggles (only apply when use_llm=True)
    enable_llm_table: Annotated[
        bool,
        "Enable LLM table processor for improved table extraction.",
    ] = True
    enable_llm_table_merge: Annotated[
        bool,
        "Enable LLM table merge processor for multi-page tables.",
    ] = True
    enable_llm_form: Annotated[
        bool,
        "Enable LLM form processor for form field detection.",
    ] = True
    enable_llm_complex_region: Annotated[
        bool,
        "Enable LLM complex region processor for nested layouts.",
    ] = True
    enable_llm_image_description: Annotated[
        bool,
        "Enable LLM image description processor for alt-text generation.",
    ] = True
    enable_llm_equation: Annotated[
        bool,
        "Enable LLM equation processor for LaTeX improvement.",
    ] = True
    enable_llm_handwriting: Annotated[
        bool,
        "Enable LLM handwriting processor for handwritten text OCR.",
    ] = True
    enable_llm_mathblock: Annotated[
        bool,
        "Enable LLM math block processor for inline math correction.",
    ] = True
    enable_llm_section_header: Annotated[
        bool,
        "Enable LLM section header processor for header hierarchy.",
    ] = True
    enable_llm_page_correction: Annotated[
        bool,
        "Enable LLM page correction processor for overall accuracy.",
    ] = True
    default_processors: Tuple[BaseProcessor, ...] = (
        OrderProcessor,
        BlockRelabelProcessor,
        LineMergeProcessor,
        BlockquoteProcessor,
        CodeProcessor,
        DocumentTOCProcessor,
        EquationProcessor,
        FootnoteProcessor,
        IgnoreTextProcessor,
        LineNumbersProcessor,
        ListProcessor,
        PageHeaderProcessor,
        SectionHeaderProcessor,
        TableProcessor,
        LLMTableProcessor,
        LLMTableMergeProcessor,
        LLMFormProcessor,
        TextProcessor,
        LLMComplexRegionProcessor,
        LLMImageDescriptionProcessor,
        LLMEquationProcessor,
        LLMHandwritingProcessor,
        LLMMathBlockProcessor,
        LLMSectionHeaderProcessor,
        LLMPageCorrectionProcessor,
        ReferenceProcessor,
        BlankPageProcessor,
        DebugProcessor,
    )
    default_llm_service: BaseService = GoogleGeminiService

    def _filter_processors_by_config(self, processors: Tuple[BaseProcessor, ...]) -> Tuple[BaseProcessor, ...]:
        """
        Filter LLM processors based on config toggles.
        Only applies when use_llm=True. If a specific LLM processor is disabled,
        it will be excluded from the processor list.
        """
        # Mapping of processor classes to their config toggle attributes
        llm_processor_toggles = {
            LLMTableProcessor: 'enable_llm_table',
            LLMTableMergeProcessor: 'enable_llm_table_merge',
            LLMFormProcessor: 'enable_llm_form',
            LLMComplexRegionProcessor: 'enable_llm_complex_region',
            LLMImageDescriptionProcessor: 'enable_llm_image_description',
            LLMEquationProcessor: 'enable_llm_equation',
            LLMHandwritingProcessor: 'enable_llm_handwriting',
            LLMMathBlockProcessor: 'enable_llm_mathblock',
            LLMSectionHeaderProcessor: 'enable_llm_section_header',
            LLMPageCorrectionProcessor: 'enable_llm_page_correction',
        }
        
        filtered = []
        for processor_cls in processors:
            # Check if this is an LLM processor with a toggle
            if processor_cls in llm_processor_toggles:
                toggle_attr = llm_processor_toggles[processor_cls]
                # Only include if the toggle is enabled (default is True)
                if getattr(self, toggle_attr, True):
                    filtered.append(processor_cls)
            else:
                # Always include non-LLM processors
                filtered.append(processor_cls)
        
        return tuple(filtered)

    def __init__(
        self,
        artifact_dict: Dict[str, Any],
        processor_list: Optional[List[str]] = None,
        renderer: str | None = None,
        llm_service: str | None = None,
        config=None,
    ):
        super().__init__(config)

        if config is None:
            config = {}

        for block_type, override_block_type in self.override_map.items():
            register_block_class(block_type, override_block_type)

        if processor_list is not None:
            processor_list = strings_to_classes(processor_list)
        else:
            # Filter default processors based on LLM processor toggles
            processor_list = self._filter_processors_by_config(self.default_processors)

        if renderer:
            renderer = strings_to_classes([renderer])[0]
        else:
            renderer = MarkdownRenderer

        # Put here so that resolve_dependencies can access it
        self.artifact_dict = artifact_dict

        if llm_service:
            llm_service_cls = strings_to_classes([llm_service])[0]
            llm_service = self.resolve_dependencies(llm_service_cls)
        elif config.get("use_llm", False):
            llm_service = self.resolve_dependencies(self.default_llm_service)

        # Inject llm service into artifact_dict so it can be picked up by processors, etc.
        self.artifact_dict["llm_service"] = llm_service
        self.llm_service = llm_service

        self.renderer = renderer

        processor_list = self.initialize_processors(processor_list)
        self.processor_list = processor_list

        self.layout_builder_class = LayoutBuilder
        self.page_count = None  # Track how many pages were converted

    @contextmanager
    def filepath_to_str(self, file_input: Union[str, io.BytesIO]):
        temp_file = None
        try:
            if isinstance(file_input, str):
                yield file_input
            else:
                with tempfile.NamedTemporaryFile(
                    delete=False, suffix=".pdf"
                ) as temp_file:
                    if isinstance(file_input, io.BytesIO):
                        file_input.seek(0)
                        temp_file.write(file_input.getvalue())
                    else:
                        raise TypeError(
                            f"Expected str or BytesIO, got {type(file_input)}"
                        )

                yield temp_file.name
        finally:
            if temp_file is not None and os.path.exists(temp_file.name):
                os.unlink(temp_file.name)

    def build_document(self, filepath: str) -> Document:
        provider_cls = provider_from_filepath(filepath)
        layout_builder = self.resolve_dependencies(self.layout_builder_class)
        line_builder = self.resolve_dependencies(LineBuilder)
        ocr_builder = self.resolve_dependencies(OcrBuilder)
        provider = provider_cls(filepath, self.config)
        document = DocumentBuilder(self.config)(
            provider, layout_builder, line_builder, ocr_builder
        )
        structure_builder_cls = self.resolve_dependencies(StructureBuilder)
        structure_builder_cls(document)

        for processor in self.processor_list:
            processor(document)

        return document

    def __call__(self, filepath: str | io.BytesIO):
        with self.filepath_to_str(filepath) as temp_path:
            document = self.build_document(temp_path)
            self.page_count = len(document.pages)
            renderer = self.resolve_dependencies(self.renderer)
            rendered = renderer(document)
        return rendered
