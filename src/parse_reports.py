# src/parse_reports.py
# Project LANTERN Part 2 - Professional Earnings Report Parser
# Extracts: Text, Tables, Images, Layout Structure, Multiple Formats

import os
import json
import yaml
from pathlib import Path
from datetime import datetime
import sys
import fitz  # PyMuPDF

# Import your Part 1 parsers
from extract_pdf_text import extract_pdf_pages
from hybrid_tables import extract_hybrid
from layout_detection import extract_layout_robust
from format_converter import CompletePDFConverter


def load_params():
    """Load parameters from params.yaml"""
    try:
        with open('params.yaml', 'r') as f:
            params = yaml.safe_load(f)
            return params.get('parse_reports', {})
    except FileNotFoundError:
        print("⚠ params.yaml not found, using defaults")
        return {
            'input_dir': 'data/raw/earnings_reports',
            'output_dir': 'data/processed/parsed_earnings',
            'model_dir': 'publaynet-model',
            'extract_text': True,
            'extract_tables': True,
            'extract_images': True,
            'extract_layout': True,
            'convert_formats': True,
            'table_threshold': 20
        }


def get_pdf_files(input_dir):
    """Find all PDF files organized by company"""
    pdf_files = []
    input_path = Path(input_dir)
    
    if not input_path.exists():
        print(f"❌ Input directory not found: {input_dir}")
        return []
    
    for company_dir in input_path.iterdir():
        if company_dir.is_dir():
            ticker = company_dir.name
            for pdf_file in company_dir.glob('*.pdf'):
                pdf_files.append((ticker, pdf_file))
    
    return pdf_files


def extract_images_with_pymupdf(pdf_path, output_dir):
    """
    Extract embedded images using PyMuPDF (fitz)
    Gets actual image files embedded in PDF
    """
    print(f"   🖼️  Extracting embedded images (PyMuPDF)...")
    
    images_dir = output_dir / 'images'
    images_dir.mkdir(exist_ok=True)
    
    doc = fitz.open(pdf_path)
    
    image_count = 0
    image_metadata = []
    
    for page_num in range(len(doc)):
        page = doc[page_num]
        
        # Get all images on this page
        image_list = page.get_images(full=True)
        
        for img_index, img in enumerate(image_list):
            try:
                xref = img[0]  # Image reference number
                
                # Extract image
                base_image = doc.extract_image(xref)
                
                if base_image:
                    image_bytes = base_image["image"]
                    image_ext = base_image["ext"]  # png, jpeg, etc.
                    
                    # Save image
                    img_filename = f"page{page_num + 1:03d}_img{img_index:02d}.{image_ext}"
                    img_path = images_dir / img_filename
                    
                    with open(img_path, "wb") as img_file:
                        img_file.write(image_bytes)
                    
                    # Store metadata
                    image_metadata.append({
                        'page': page_num + 1,
                        'image_index': img_index,
                        'filename': img_filename,
                        'format': image_ext,
                        'width': base_image.get("width"),
                        'height': base_image.get("height"),
                        'size_bytes': len(image_bytes)
                    })
                    
                    image_count += 1
                    
            except Exception as e:
                print(f"      ⚠ Error extracting image {img_index} from page {page_num + 1}: {e}")
                continue
    
    doc.close()
    
    # Save image metadata
    if image_metadata:
        metadata_path = images_dir / 'images_metadata.json'
        with open(metadata_path, 'w') as f:
            json.dump({
                'total_images': image_count,
                'images': image_metadata
            }, f, indent=2)
    
    print(f"      ✓ Extracted {image_count} embedded images")
    return image_count, image_metadata


def extract_figure_blocks_from_layout(pdf_path, layout_dir, output_dir):
    """
    Extract figure regions identified by layout detection
    Uses PyMuPDF to render high-quality images
    """
    print(f"   📊 Extracting figure blocks from layout detection...")
    
    figures_dir = output_dir / 'figures'
    figures_dir.mkdir(exist_ok=True)
    
    # Load layout data
    layout_files = sorted(layout_dir.glob('page_*_layout.json'))
    
    if not layout_files:
        print(f"      ⚠ No layout files found")
        return 0, []
    
    doc = fitz.open(pdf_path)
    
    figure_count = 0
    figure_metadata = []
    
    for layout_file in layout_files:
        with open(layout_file, 'r') as f:
            layout_data = json.load(f)
        
        page_num = layout_data['page_number'] - 1  # 0-indexed
        
        if page_num >= len(doc):
            continue
        
        page = doc[page_num]
        
        # Find Figure and Table blocks
        for block in layout_data.get('blocks', []):
            if block['type'] in ['Figure', 'Table']:
                bbox = block['bbox']
                
                try:
                    # Create rectangle for cropping
                    rect = fitz.Rect(bbox['x1'], bbox['y1'], bbox['x2'], bbox['y2'])
                    
                    # Render this region as high-res image
                    mat = fitz.Matrix(2, 2)  # 2x zoom for better quality
                    pix = page.get_pixmap(matrix=mat, clip=rect)
                    
                    # Save image
                    block_type = block['type'].lower()
                    img_filename = f"page{page_num + 1:03d}_{block_type}{block['block_id']:02d}.png"
                    img_path = figures_dir / img_filename
                    
                    pix.save(img_path)
                    
                    # Store metadata
                    figure_metadata.append({
                        'page': page_num + 1,
                        'block_id': block['block_id'],
                        'type': block['type'],
                        'filename': img_filename,
                        'confidence': block.get('confidence', 0),
                        'bbox': bbox,
                        'width': int(bbox['x2'] - bbox['x1']),
                        'height': int(bbox['y2'] - bbox['y1'])
                    })
                    
                    figure_count += 1
                    
                except Exception as e:
                    print(f"      ⚠ Error rendering block {block['block_id']} from page {page_num + 1}: {e}")
                    continue
    
    doc.close()
    
    # Save figure metadata
    if figure_metadata:
        metadata_path = figures_dir / 'figures_metadata.json'
        with open(metadata_path, 'w') as f:
            json.dump({
                'total_figures': figure_count,
                'figures': figure_metadata
            }, f, indent=2)
    
    print(f"      ✓ Rendered {figure_count} figure/table blocks")
    return figure_count, figure_metadata


def parse_single_report_comprehensive(ticker, pdf_path, output_dir, params):
    """
    Comprehensive parsing using all Part 1 tools + PyMuPDF
    
    Pipeline:
    1. Extract text (with OCR fallback)
    2. Extract tables (hybrid lattice + stream)
    3. Detect layout structure (PubLayNet)
    4. Extract images (embedded + figure blocks)
    5. Convert to multiple formats (Markdown, JSON, TXT)
    """
    print(f"\n{'='*60}")
    print(f"📄 Processing {ticker}: {pdf_path.name}")
    print(f"{'='*60}")
    
    result = {
        'ticker': ticker,
        'file_name': pdf_path.name,
        'file_path': str(pdf_path),
        'parsed_date': datetime.now().isoformat(),
        'success': False,
        'stages_completed': []
    }
    
    try:
        # Create company-specific output directory
        company_output_dir = Path(output_dir) / ticker / pdf_path.stem
        company_output_dir.mkdir(parents=True, exist_ok=True)
        
        print(f"Output directory: {company_output_dir}")
        
        # ============================================================
        # STAGE 1: TEXT EXTRACTION
        # ============================================================
        if params.get('extract_text', True):
            print(f"\n📝 STAGE 1: Extracting text (pdfplumber + OCR)...")
            try:
                extract_pdf_pages(
                    pdf_path=str(pdf_path),
                    output_dir=str(company_output_dir)
                )
                
                # Count extracted text
                page_files = list(company_output_dir.glob(f'{pdf_path.stem}/page_*.txt'))
                total_chars = sum(len(p.read_text(encoding='utf-8')) for p in page_files if p.exists())
                
                result['text_extraction'] = {
                    'success': True,
                    'pages': len(page_files),
                    'total_characters': total_chars
                }
                result['stages_completed'].append('text_extraction')
                print(f"   ✅ Extracted {len(page_files)} pages, {total_chars:,} characters")
                
            except Exception as e:
                print(f"   ❌ Text extraction failed: {e}")
                result['text_extraction'] = {'success': False, 'error': str(e)}
        
        # ============================================================
        # STAGE 2: TABLE EXTRACTION
        # ============================================================
        if params.get('extract_tables', True):
            print(f"\n📊 STAGE 2: Extracting tables (hybrid lattice + stream)...")
            try:
                tables_dir = company_output_dir / 'tables'
                tables_dir.mkdir(exist_ok=True)
                
                # Get total pages
                import pdfplumber
                with pdfplumber.open(pdf_path) as pdf:
                    total_pages = len(pdf.pages)
                
                # Extract tables from all pages
                pages = list(range(1, min(total_pages + 1, 61)))  # Limit to 60 pages
                extract_hybrid(
                    pdf=str(pdf_path),
                    pages=pages,
                    outdir=str(tables_dir),
                    thresh=params.get('table_threshold', 20)
                )
                
                # Count extracted tables
                table_files = list(tables_dir.glob('*.csv'))
                
                result['table_extraction'] = {
                    'success': True,
                    'tables_extracted': len(table_files)
                }
                result['stages_completed'].append('table_extraction')
                print(f"   ✅ Extracted {len(table_files)} tables")
                
            except Exception as e:
                print(f"   ❌ Table extraction failed: {e}")
                result['table_extraction'] = {'success': False, 'error': str(e)}
        
        # ============================================================
        # STAGE 3: LAYOUT DETECTION
        # ============================================================
        if params.get('extract_layout', True):
            print(f"\n🔍 STAGE 3: Detecting layout structure (PubLayNet)...")
            try:
                layout_summary = extract_layout_robust(
                    pdf_path=pdf_path,
                    output_base_dir=str(company_output_dir),
                    model_dir=params.get('model_dir', 'publaynet-model'),
                    save_viz=True
                )
                
                if layout_summary:
                    result['layout_detection'] = {
                        'success': True,
                        'total_blocks': layout_summary.get('total_blocks', 0),
                        'block_types': layout_summary.get('overall_block_counts', {})
                    }
                    result['stages_completed'].append('layout_detection')
                    print(f"   ✅ Detected {layout_summary.get('total_blocks', 0)} layout blocks")
                else:
                    result['layout_detection'] = {'success': False, 'error': 'No layout data returned'}
                    
            except Exception as e:
                print(f"   ❌ Layout detection failed: {e}")
                result['layout_detection'] = {'success': False, 'error': str(e)}
        
        # ============================================================
        # STAGE 4: IMAGE EXTRACTION (PyMuPDF)
        # ============================================================
        if params.get('extract_images', True):
            print(f"\n🖼️  STAGE 4: Extracting images (PyMuPDF)...")
            try:
                # Method 1: Extract embedded images
                embedded_count, embedded_metadata = extract_images_with_pymupdf(
                    pdf_path, 
                    company_output_dir
                )
                
                # Method 2: Extract figure blocks from layout detection
                figure_count = 0
                figure_metadata = []
                
                layout_dir = company_output_dir / 'layout' / pdf_path.stem
                if layout_dir.exists():
                    figure_count, figure_metadata = extract_figure_blocks_from_layout(
                        pdf_path,
                        layout_dir,
                        company_output_dir
                    )
                
                total_images = embedded_count + figure_count
                
                result['image_extraction'] = {
                    'success': True,
                    'embedded_images': embedded_count,
                    'figure_blocks': figure_count,
                    'total_images': total_images
                }
                result['stages_completed'].append('image_extraction')
                print(f"   ✅ Total images extracted: {total_images}")
                print(f"      - Embedded: {embedded_count}")
                print(f"      - Figures: {figure_count}")
                
            except Exception as e:
                print(f"   ❌ Image extraction failed: {e}")
                result['image_extraction'] = {'success': False, 'error': str(e)}
        
        # ============================================================
        # STAGE 5: FORMAT CONVERSION
        # ============================================================
        if params.get('convert_formats', True):
            print(f"\n🔄 STAGE 5: Converting to multiple formats (MD, JSON, TXT)...")
            try:
                layout_dir = company_output_dir / 'layout' / pdf_path.stem
                
                if layout_dir.exists():
                    converter = CompletePDFConverter(
                        raw_dir=str(pdf_path.parent),
                        layout_base_dir=str(company_output_dir / 'layout'),
                        output_dir=str(company_output_dir / 'converted')
                    )
                    
                    files = converter.convert_single_pdf(pdf_path, layout_dir)
                    
                    result['format_conversion'] = {
                        'success': True,
                        'formats': list(files.keys())
                    }
                    result['stages_completed'].append('format_conversion')
                    print(f"   ✅ Converted to {len(files)} formats")
                else:
                    print(f"   ⚠ Skipping format conversion - no layout data")
                    result['format_conversion'] = {
                        'success': False, 
                        'error': 'No layout data available'
                    }
                    
            except Exception as e:
                print(f"   ❌ Format conversion failed: {e}")
                result['format_conversion'] = {'success': False, 'error': str(e)}
        
        # ============================================================
        # SAVE COMPREHENSIVE SUMMARY
        # ============================================================
        summary = {
            'ticker': ticker,
            'file_name': pdf_path.name,
            'parsed_date': datetime.now().isoformat(),
            'stages_completed': result['stages_completed'],
            'extraction_methods': {
                'text': 'pdfplumber with OCR fallback (pytesseract)',
                'tables': 'Camelot hybrid (lattice + stream)',
                'layout': 'PubLayNet deep learning model',
                'images': 'PyMuPDF embedded + layout-based extraction',
                'formats': 'Markdown, JSON, Plain Text'
            },
            'results': {
                'text_extraction': result.get('text_extraction', {}),
                'table_extraction': result.get('table_extraction', {}),
                'layout_detection': result.get('layout_detection', {}),
                'image_extraction': result.get('image_extraction', {}),
                'format_conversion': result.get('format_conversion', {})
            }
        }
        
        summary_path = company_output_dir / 'parsing_summary.json'
        with open(summary_path, 'w') as f:
            json.dump(summary, f, indent=2)
        
        result['success'] = len(result['stages_completed']) > 0
        result['output_location'] = str(company_output_dir)
        
        # Print summary
        print(f"\n{'='*60}")
        print(f"✅ Completed {ticker}")
        print(f"{'='*60}")
        print(f"Stages completed: {', '.join(result['stages_completed'])}")
        if result.get('text_extraction', {}).get('success'):
            print(f"  📝 Text: {result['text_extraction']['pages']} pages, {result['text_extraction']['total_characters']:,} chars")
        if result.get('table_extraction', {}).get('success'):
            print(f"  📊 Tables: {result['table_extraction']['tables_extracted']} tables")
        if result.get('layout_detection', {}).get('success'):
            print(f"  🔍 Layout: {result['layout_detection']['total_blocks']} blocks")
        if result.get('image_extraction', {}).get('success'):
            print(f"  🖼️  Images: {result['image_extraction']['total_images']} total ({result['image_extraction']['embedded_images']} embedded + {result['image_extraction']['figure_blocks']} figures)")
        if result.get('format_conversion', {}).get('success'):
            print(f"  🔄 Formats: {', '.join(result['format_conversion']['formats'])}")
        
    except Exception as e:
        print(f"\n❌ Error parsing {ticker}: {e}")
        result['error'] = str(e)
        import traceback
        result['traceback'] = traceback.format_exc()
    
    return result


def generate_overall_summary(all_results, output_dir):
    """Generate overall parsing summary"""
    summary = {
        'parse_date': datetime.now().isoformat(),
        'pipeline_stages': [
            'text_extraction',
            'table_extraction',
            'layout_detection',
            'image_extraction',
            'format_conversion'
        ],
        'total_files': len(all_results),
        'successful': sum(1 for r in all_results if r['success']),
        'failed': sum(1 for r in all_results if not r['success']),
        'aggregate_stats': {
            'total_pages': 0,
            'total_characters': 0,
            'total_tables': 0,
            'total_blocks': 0,
            'total_images': 0
        },
        'companies': {}
    }
    
    # Aggregate statistics
    for result in all_results:
        if result.get('text_extraction', {}).get('success'):
            summary['aggregate_stats']['total_pages'] += result['text_extraction'].get('pages', 0)
            summary['aggregate_stats']['total_characters'] += result['text_extraction'].get('total_characters', 0)
        
        if result.get('table_extraction', {}).get('success'):
            summary['aggregate_stats']['total_tables'] += result['table_extraction'].get('tables_extracted', 0)
        
        if result.get('layout_detection', {}).get('success'):
            summary['aggregate_stats']['total_blocks'] += result['layout_detection'].get('total_blocks', 0)
        
        if result.get('image_extraction', {}).get('success'):
            summary['aggregate_stats']['total_images'] += result['image_extraction'].get('total_images', 0)
        
        # Store per-company results
        ticker = result['ticker']
        if ticker not in summary['companies']:
            summary['companies'][ticker] = []
        
        summary['companies'][ticker].append({
            'file_name': result['file_name'],
            'success': result['success'],
            'stages_completed': result.get('stages_completed', []),
            'output_location': result.get('output_location')
        })
    
    # Save summary
    summary_path = Path(output_dir) / 'parsing_summary.json'
    with open(summary_path, 'w') as f:
        json.dump(summary, f, indent=2)
    
    print(f"\n📊 Overall summary saved to: {summary_path}")
    return summary


def main():
    print("="*60)
    print("Project LANTERN - Professional Earnings Report Parser")
    print("="*60)
    print("Pipeline stages:")
    print("  1. Text extraction (pdfplumber + OCR)")
    print("  2. Table extraction (Camelot hybrid)")
    print("  3. Layout detection (PubLayNet)")
    print("  4. Image extraction (PyMuPDF)")
    print("  5. Format conversion (MD, JSON, TXT)")
    print("="*60)
    
    # Load parameters
    params = load_params()
    print(f"\nParameters:")
    for key, value in params.items():
        print(f"  {key}: {value}")
    
    input_dir = params['input_dir']
    output_dir = params['output_dir']
    
    # Find all PDFs
    print(f"\n🔍 Searching for PDFs in {input_dir}...")
    pdf_files = get_pdf_files(input_dir)
    
    if not pdf_files:
        print(f"\n❌ No PDF files found in {input_dir}")
        print(f"\n💡 Expected structure:")
        print(f"   {input_dir}/")
        print(f"   ├── AAPL/")
        print(f"   │   └── earnings_report.pdf")
        print(f"   └── ...")
        return
    
    print(f"✓ Found {len(pdf_files)} PDF files across {len(set(t for t, _ in pdf_files))} companies")
    
    # Parse each PDF
    all_results = []
    for i, (ticker, pdf_path) in enumerate(pdf_files, 1):
        print(f"\n{'#'*60}")
        print(f"[{i}/{len(pdf_files)}] Processing {ticker}")
        print(f"{'#'*60}")
        
        result = parse_single_report_comprehensive(ticker, pdf_path, output_dir, params)
        all_results.append(result)
    
    # Generate overall summary
    print(f"\n{'='*60}")
    print("Generating Overall Summary")
    print(f"{'='*60}")
    summary = generate_overall_summary(all_results, output_dir)
    
    # Print final summary
    print(f"\n{'='*60}")
    print("📊 PARSING COMPLETE!")
    print(f"{'='*60}")
    print(f"Total files: {summary['total_files']}")
    print(f"✓ Successful: {summary['successful']}")
    print(f"❌ Failed: {summary['failed']}")
    print(f"\nAggregate statistics:")
    print(f"  📄 Pages: {summary['aggregate_stats']['total_pages']}")
    print(f"  📝 Characters: {summary['aggregate_stats']['total_characters']:,}")
    print(f"  📊 Tables: {summary['aggregate_stats']['total_tables']}")
    print(f"  🔍 Layout blocks: {summary['aggregate_stats']['total_blocks']}")
    print(f"  🖼️  Images: {summary['aggregate_stats']['total_images']}")
    print(f"\n📁 Parsed data saved to: {output_dir}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()