"""PDF utility functions."""
import math
from pathlib import Path
from typing import List, Optional, Set, Tuple

from PIL import Image

from app.core import logger, FileProcessingError


def split_pdf_to_images(
    pdf_path: Path,
    output_dir: Path,
    dpi: int = 200,
    max_pixels: Optional[int] = None,
    preserve_page_numbers: Optional[Set[int]] = None,
) -> List[Tuple[Path, int, int]]:
    """Split a PDF into page images with an optional pixel budget.

    Args:
        pdf_path: Path to PDF file.
        output_dir: Directory to save page images.
        dpi: Preferred rendering resolution.
        max_pixels: Maximum rendered pixels per page; zero or None disables it.

    Returns:
        Ordered tuples of image path, width, and height.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        raise FileProcessingError("PyMuPDF (fitz) is required for PDF processing")

    output_dir.mkdir(parents=True, exist_ok=True)
    results = []

    try:
        doc = fitz.open(str(pdf_path))
        logger.info(f"Processing PDF with {len(doc)} pages: {pdf_path}")

        for page_num in range(len(doc)):
            page = doc[page_num]
            preferred_scale = dpi / 72
            render_scale = preferred_scale
            if max_pixels and max_pixels > 0:
                estimated_pixels = (
                    page.rect.width
                    * preferred_scale
                    * page.rect.height
                    * preferred_scale
                )
                if estimated_pixels > max_pixels:
                    render_scale *= math.sqrt(max_pixels / estimated_pixels) * 0.99
                    logger.debug(
                        "Limiting PDF page %s render from %.0f to %s pixels",
                        page_num + 1,
                        estimated_pixels,
                        max_pixels,
                    )
            mat = fitz.Matrix(render_scale, render_scale)
            pix = page.get_pixmap(matrix=mat)

            # Save as PNG
            image_filename = f"page_{page_num + 1:04d}.png"
            image_path = output_dir / image_filename
            pix.save(str(image_path))

            results.append((image_path, pix.width, pix.height))
            logger.debug(f"Saved page {page_num + 1}: {image_path}")

        doc.close()
        logger.info(f"Successfully split PDF into {len(results)} pages")
        return results

    except Exception as e:
        logger.error(f"Error splitting PDF: {e}")
        raise FileProcessingError(f"Failed to split PDF: {str(e)}")


def split_pdf_to_page_pdfs(
    pdf_path: Path,
    output_dir: Path,
) -> List[Path]:
    """Split a PDF into ordered single-page PDF files.

    Args:
        pdf_path: Source PDF path.
        output_dir: Directory for generated page PDFs.

    Returns:
        Ordered paths to one-page PDF files.

    Raises:
        FileProcessingError: If PyMuPDF is unavailable or splitting fails.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:
        raise FileProcessingError(
            "PyMuPDF (fitz) is required for PDF processing"
        ) from exc

    output_dir.mkdir(parents=True, exist_ok=True)
    page_paths: List[Path] = []
    try:
        with fitz.open(str(pdf_path)) as source:
            for page_index in range(len(source)):
                page_path = output_dir / f"page_{page_index + 1:04d}.pdf"
                with fitz.open() as single_page:
                    single_page.insert_pdf(
                        source, from_page=page_index, to_page=page_index
                    )
                    single_page.save(str(page_path), garbage=3, deflate=True)
                page_paths.append(page_path)
        logger.info("Successfully split PDF into %s single-page PDFs", len(page_paths))
        return page_paths
    except Exception as exc:
        logger.error("Error splitting PDF pages: %s", exc)
        raise FileProcessingError(
            f"Failed to split PDF pages: {str(exc)}"
        ) from exc


def get_image_dimensions(image_path: Path) -> Tuple[int, int]:
    """Get image dimensions (width, height)."""
    try:
        with Image.open(image_path) as img:
            return img.size
    except Exception as e:
        logger.error(f"Error getting image dimensions: {e}")
        raise FileProcessingError(f"Failed to get image dimensions: {str(e)}")


def image_to_base64(image_path: Path) -> str:
    """Convert image file to base64 string."""
    import base64

    try:
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    except Exception as e:
        logger.error(f"Error converting image to base64: {e}")
        raise FileProcessingError(f"Failed to convert image to base64: {str(e)}")


def pdf_to_base64(pdf_path: Path) -> str:
    """Convert PDF file to base64 string."""
    import base64

    try:
        with open(pdf_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    except Exception as e:
        logger.error(f"Error converting PDF to base64: {e}")
        raise FileProcessingError(f"Failed to convert PDF to base64: {str(e)}")
