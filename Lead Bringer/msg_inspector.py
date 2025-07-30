#!/usr/bin/env python3
"""
Email Image Inventory Scanner
Comprehensive analysis of MSG and EML files to catalog all image content
"""

import logging
import os
import re
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
import email
from email.message import EmailMessage

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("email_image_inventory.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("EmailImageInventory")

class ImageInfo:
    def __init__(self, filename="", size_bytes=0, content_type="", source_type="", 
                 cid="", base64_preview="", file_extension="", is_embedded=False):
        self.filename = filename
        self.size_bytes = size_bytes
        self.content_type = content_type
        self.source_type = source_type  # 'attachment', 'cid', 'base64', 'url'
        self.cid = cid
        self.base64_preview = base64_preview[:50] if base64_preview else ""  # First 50 chars
        self.file_extension = file_extension
        self.is_embedded = is_embedded

class EmailAnalysis:
    def __init__(self, filename="", email_format="", subject="", sender="", 
                 date="", has_html=False, has_attachments=False):
        self.filename = filename
        self.email_format = email_format  # 'MSG' or 'EML'
        self.subject = subject
        self.sender = sender
        self.date = date
        self.has_html = has_html
        self.has_attachments = has_attachments
        self.images: List[ImageInfo] = []
        self.total_images = 0
        self.total_image_size = 0
        self.error_message = ""

class MSGAnalyzer:
    def analyze_msg_file(self, file_path: Path) -> EmailAnalysis:
        """Analyze a MSG file for image content"""
        analysis = EmailAnalysis(
            filename=file_path.name,
            email_format="MSG"
        )
        
        try:
            import extract_msg
        except ImportError:
            analysis.error_message = "extract-msg library not found"
            return analysis
        
        try:
            # Open MSG file
            msg = extract_msg.Message(str(file_path))
            
            # Basic email info
            analysis.subject = msg.subject or "No Subject"
            analysis.sender = msg.sender or "Unknown"
            analysis.date = str(msg.date) if msg.date else "Unknown"
            analysis.has_html = bool(msg.htmlBody)
            analysis.has_attachments = len(msg.attachments) > 0
            
            # Analyze attachments for images
            for i, attachment in enumerate(msg.attachments):
                try:
                    filename = getattr(attachment, 'longFilename', '') or getattr(attachment, 'shortFilename', f"attachment_{i}")
                    content_type = getattr(attachment, 'contentType', 'unknown')
                    cid = getattr(attachment, 'cid', '')
                    data_size = len(attachment.data) if attachment.data else 0
                    
                    # Check if it's an image
                    is_image = False
                    file_ext = ""
                    
                    # Check by filename extension
                    if filename:
                        file_ext = Path(filename).suffix.lower()
                        if file_ext in ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.tiff']:
                            is_image = True
                    
                    # Check by content type
                    if content_type and 'image' in content_type.lower():
                        is_image = True
                    
                    # Check by CID (usually means embedded image)
                    if cid:
                        is_image = True
                    
                    # Check by data characteristics (reasonable size for image)
                    if data_size > 1000 and data_size < 50000000:  # 1KB to 50MB
                        if not filename or filename.startswith('image'):
                            is_image = True
                    
                    if is_image:
                        image_info = ImageInfo(
                            filename=filename,
                            size_bytes=data_size,
                            content_type=content_type,
                            source_type="cid" if cid else "attachment",
                            cid=cid,
                            file_extension=file_ext,
                            is_embedded=bool(cid)
                        )
                        analysis.images.append(image_info)
                        analysis.total_image_size += data_size
                
                except Exception as e:
                    logger.warning(f"Error analyzing attachment {i} in {file_path.name}: {e}")
            
            # Check HTML content for additional image references
            if analysis.has_html:
                try:
                    html_content = msg.htmlBody
                    if isinstance(html_content, bytes):
                        html_content = html_content.decode('utf-8', errors='ignore')
                    
                    # Look for base64 images
                    base64_pattern = r'data:image/([^;]+);base64,([^"\'>\s]{20,})'
                    base64_matches = re.findall(base64_pattern, html_content)
                    
                    for img_format, base64_data in base64_matches:
                        try:
                            # Estimate size (base64 is ~1.33x larger than binary)
                            estimated_size = int(len(base64_data) * 0.75)
                            
                            image_info = ImageInfo(
                                filename=f"inline_base64.{img_format}",
                                size_bytes=estimated_size,
                                content_type=f"image/{img_format}",
                                source_type="base64",
                                base64_preview=base64_data[:50],
                                file_extension=f".{img_format}",
                                is_embedded=True
                            )
                            analysis.images.append(image_info)
                            analysis.total_image_size += estimated_size
                        except:
                            pass
                    
                    # Look for external image URLs
                    url_pattern = r'src=["\']?(https?://[^"\'>\s]+\.(?:jpg|jpeg|png|gif|webp|bmp))["\']?'
                    url_matches = re.findall(url_pattern, html_content, re.IGNORECASE)
                    
                    for url in url_matches:
                        image_info = ImageInfo(
                            filename=Path(url).name,
                            size_bytes=0,  # Unknown for external URLs
                            content_type="image/unknown",
                            source_type="url",
                            file_extension=Path(url).suffix.lower(),
                            is_embedded=False
                        )
                        analysis.images.append(image_info)
                
                except Exception as e:
                    logger.warning(f"Error analyzing HTML in {file_path.name}: {e}")
            
            analysis.total_images = len(analysis.images)
            
        except Exception as e:
            analysis.error_message = str(e)
            logger.error(f"Error analyzing MSG file {file_path}: {e}")
        
        return analysis

class EMLAnalyzer:
    def analyze_eml_file(self, file_path: Path) -> EmailAnalysis:
        """Analyze an EML file for image content"""
        analysis = EmailAnalysis(
            filename=file_path.name,
            email_format="EML"
        )
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                eml_message = email.message_from_file(f)
            
            # Basic email info
            analysis.subject = eml_message.get('Subject', 'No Subject')
            analysis.sender = eml_message.get('From', 'Unknown')
            analysis.date = eml_message.get('Date', 'Unknown')
            
            # Check if multipart and has attachments
            analysis.has_attachments = eml_message.is_multipart()
            
            # Walk through all parts
            if eml_message.is_multipart():
                for part in eml_message.walk():
                    content_type = part.get_content_type()
                    
                    # Check for HTML content
                    if content_type == "text/html":
                        analysis.has_html = True
                        
                        # Analyze HTML for images
                        try:
                            html_content = part.get_payload(decode=True)
                            if html_content:
                                if isinstance(html_content, bytes):
                                    html_content = html_content.decode('utf-8', errors='ignore')
                                
                                # Look for base64 images
                                base64_pattern = r'data:image/([^;]+);base64,([^"\'>\s]{20,})'
                                base64_matches = re.findall(base64_pattern, html_content)
                                
                                for img_format, base64_data in base64_matches:
                                    estimated_size = int(len(base64_data) * 0.75)
                                    
                                    image_info = ImageInfo(
                                        filename=f"inline_base64.{img_format}",
                                        size_bytes=estimated_size,
                                        content_type=f"image/{img_format}",
                                        source_type="base64",
                                        base64_preview=base64_data[:50],
                                        file_extension=f".{img_format}",
                                        is_embedded=True
                                    )
                                    analysis.images.append(image_info)
                                    analysis.total_image_size += estimated_size
                                
                                # Look for CID references
                                cid_pattern = r'src=["\']cid:([^"\']+)["\']'
                                cid_matches = re.findall(cid_pattern, html_content)
                                
                                for cid in cid_matches:
                                    image_info = ImageInfo(
                                        filename=f"cid_{cid}",
                                        size_bytes=0,  # Will be updated if matching attachment found
                                        content_type="image/unknown",
                                        source_type="cid",
                                        cid=cid,
                                        is_embedded=True
                                    )
                                    analysis.images.append(image_info)
                                
                                # Look for external URLs
                                url_pattern = r'src=["\']?(https?://[^"\'>\s]+\.(?:jpg|jpeg|png|gif|webp|bmp))["\']?'
                                url_matches = re.findall(url_pattern, html_content, re.IGNORECASE)
                                
                                for url in url_matches:
                                    image_info = ImageInfo(
                                        filename=Path(url).name,
                                        size_bytes=0,
                                        content_type="image/unknown",
                                        source_type="url",
                                        file_extension=Path(url).suffix.lower()
                                    )
                                    analysis.images.append(image_info)
                        
                        except Exception as e:
                            logger.warning(f"Error analyzing HTML in EML {file_path.name}: {e}")
                    
                    # Check for image attachments
                    elif content_type.startswith('image/'):
                        filename = part.get_filename() or f"attachment_{len(analysis.images)}"
                        content_id = part.get('Content-ID', '').strip('<>')
                        
                        try:
                            payload = part.get_payload(decode=True)
                            size_bytes = len(payload) if payload else 0
                        except:
                            size_bytes = 0
                        
                        image_info = ImageInfo(
                            filename=filename,
                            size_bytes=size_bytes,
                            content_type=content_type,
                            source_type="cid" if content_id else "attachment",
                            cid=content_id,
                            file_extension=Path(filename).suffix.lower(),
                            is_embedded=bool(content_id)
                        )
                        analysis.images.append(image_info)
                        analysis.total_image_size += size_bytes
            
            else:
                # Single part message - check if it's HTML
                if eml_message.get_content_type() == "text/html":
                    analysis.has_html = True
            
            analysis.total_images = len(analysis.images)
            
        except Exception as e:
            analysis.error_message = str(e)
            logger.error(f"Error analyzing EML file {file_path}: {e}")
        
        return analysis

class EmailImageInventory:
    def __init__(self, output_folder: str = "image_inventory"):
        self.output_folder = Path(output_folder)
        self.output_folder.mkdir(exist_ok=True)
        self.msg_analyzer = MSGAnalyzer()
        self.eml_analyzer = EMLAnalyzer()
        
    def scan_folder(self, folder_path: str) -> List[EmailAnalysis]:
        """Scan a folder for MSG and EML files and analyze them"""
        folder = Path(folder_path)
        results = []
        
        # Find all email files
        msg_files = list(folder.glob("*.msg"))
        eml_files = list(folder.glob("*.eml"))
        
        total_files = len(msg_files) + len(eml_files)
        
        logger.info(f"🔍 Scanning folder: {folder}")
        logger.info(f"📁 Found {len(msg_files)} MSG files and {len(eml_files)} EML files")
        logger.info(f"📊 Total files to analyze: {total_files}")
        logger.info("")
        
        current_file = 0
        
        # Analyze MSG files
        for msg_file in msg_files:
            current_file += 1
            logger.info(f"[{current_file}/{total_files}] 📧 Analyzing MSG: {msg_file.name}")
            
            analysis = self.msg_analyzer.analyze_msg_file(msg_file)
            results.append(analysis)
            
            if analysis.total_images > 0:
                logger.info(f"   ✅ Found {analysis.total_images} images ({analysis.total_image_size:,} bytes)")
            else:
                logger.info(f"   ❌ No images found")
            
            if analysis.error_message:
                logger.warning(f"   ⚠️  Error: {analysis.error_message}")
        
        # Analyze EML files
        for eml_file in eml_files:
            current_file += 1
            logger.info(f"[{current_file}/{total_files}] 📧 Analyzing EML: {eml_file.name}")
            
            analysis = self.eml_analyzer.analyze_eml_file(eml_file)
            results.append(analysis)
            
            if analysis.total_images > 0:
                logger.info(f"   ✅ Found {analysis.total_images} images ({analysis.total_image_size:,} bytes)")
            else:
                logger.info(f"   ❌ No images found")
            
            if analysis.error_message:
                logger.warning(f"   ⚠️  Error: {analysis.error_message}")
        
        return results
    
    def generate_reports(self, analyses: List[EmailAnalysis], folder_path: str):
        """Generate comprehensive reports"""
        
        # Summary statistics
        total_emails = len(analyses)
        emails_with_images = len([a for a in analyses if a.total_images > 0])
        total_images = sum(a.total_images for a in analyses)
        total_size = sum(a.total_image_size for a in analyses)
        
        logger.info("")
        logger.info("📊 INVENTORY SUMMARY")
        logger.info("=" * 40)
        logger.info(f"Total emails analyzed: {total_emails}")
        logger.info(f"Emails with images: {emails_with_images}")
        logger.info(f"Total images found: {total_images}")
        logger.info(f"Total image size: {total_size:,} bytes ({total_size/1024/1024:.1f} MB)")
        
        # Generate CSV report
        csv_path = self.output_folder / "email_image_inventory.csv"
        with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = [
                'filename', 'format', 'subject', 'sender', 'date', 
                'has_html', 'has_attachments', 'total_images', 'total_image_size_bytes',
                'image_details', 'error_message'
            ]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            for analysis in analyses:
                # Create image details string
                image_details = []
                for img in analysis.images:
                    detail = f"{img.filename}({img.size_bytes}b,{img.source_type})"
                    if img.cid:
                        detail += f",cid:{img.cid}"
                    image_details.append(detail)
                
                writer.writerow({
                    'filename': analysis.filename,
                    'format': analysis.email_format,
                    'subject': analysis.subject,
                    'sender': analysis.sender,
                    'date': analysis.date,
                    'has_html': analysis.has_html,
                    'has_attachments': analysis.has_attachments,
                    'total_images': analysis.total_images,
                    'total_image_size_bytes': analysis.total_image_size,
                    'image_details': '; '.join(image_details),
                    'error_message': analysis.error_message
                })
        
        # Generate detailed JSON report
        json_path = self.output_folder / "detailed_image_inventory.json"
        json_data = []
        for analysis in analyses:
            email_data = {
                'filename': analysis.filename,
                'format': analysis.email_format,
                'subject': analysis.subject,
                'sender': analysis.sender,
                'date': analysis.date,
                'has_html': analysis.has_html,
                'has_attachments': analysis.has_attachments,
                'total_images': analysis.total_images,
                'total_image_size': analysis.total_image_size,
                'error_message': analysis.error_message,
                'images': []
            }
            
            for img in analysis.images:
                img_data = {
                    'filename': img.filename,
                    'size_bytes': img.size_bytes,
                    'content_type': img.content_type,
                    'source_type': img.source_type,
                    'cid': img.cid,
                    'file_extension': img.file_extension,
                    'is_embedded': img.is_embedded,
                    'base64_preview': img.base64_preview
                }
                email_data['images'].append(img_data)
            
            json_data.append(email_data)
        
        with open(json_path, 'w', encoding='utf-8') as jsonfile:
            json.dump(json_data, jsonfile, indent=2, ensure_ascii=False)
        
        # Generate human-readable summary
        summary_path = self.output_folder / "inventory_summary.txt"
        with open(summary_path, 'w', encoding='utf-8') as f:
            f.write("EMAIL IMAGE INVENTORY REPORT\n")
            f.write("=" * 50 + "\n\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Source folder: {folder_path}\n\n")
            
            f.write("SUMMARY STATISTICS:\n")
            f.write("-" * 20 + "\n")
            f.write(f"Total emails analyzed: {total_emails}\n")
            f.write(f"Emails with images: {emails_with_images}\n")
            f.write(f"Total images found: {total_images}\n")
            f.write(f"Total image size: {total_size:,} bytes ({total_size/1024/1024:.1f} MB)\n\n")
            
            # Image type breakdown
            image_types = {}
            source_types = {}
            for analysis in analyses:
                for img in analysis.images:
                    # Count by file extension
                    ext = img.file_extension or 'unknown'
                    image_types[ext] = image_types.get(ext, 0) + 1
                    
                    # Count by source type
                    source_types[img.source_type] = source_types.get(img.source_type, 0) + 1
            
            f.write("IMAGE TYPES:\n")
            f.write("-" * 15 + "\n")
            for img_type, count in sorted(image_types.items()):
                f.write(f"{img_type}: {count}\n")
            
            f.write("\nSOURCE TYPES:\n")
            f.write("-" * 15 + "\n")
            for source_type, count in sorted(source_types.items()):
                f.write(f"{source_type}: {count}\n")
            
            f.write("\nEMAILS WITH MOST IMAGES:\n")
            f.write("-" * 25 + "\n")
            top_emails = sorted(analyses, key=lambda x: x.total_images, reverse=True)[:10]
            for email in top_emails:
                if email.total_images > 0:
                    f.write(f"{email.filename}: {email.total_images} images\n")
        
        logger.info(f"\n📄 Reports generated:")
        logger.info(f"   CSV: {csv_path}")
        logger.info(f"   JSON: {json_path}")
        logger.info(f"   Summary: {summary_path}")

def main():
    """Main function"""
    print("🔍 Email Image Inventory Scanner")
    print("=" * 50)
    print("Analyzes MSG and EML files to catalog all image content")
    print()
    
    # Get folder path
    folder_path = input("Enter folder path containing MSG/EML files: ").strip().strip('"\'')
    
    if not folder_path:
        print("❌ No folder provided")
        return
    
    if not os.path.exists(folder_path):
        print(f"❌ Folder not found: {folder_path}")
        return
    
    # Run inventory
    inventory = EmailImageInventory()
    analyses = inventory.scan_folder(folder_path)
    inventory.generate_reports(analyses, folder_path)
    
    print("\n✅ Inventory complete! Check the 'image_inventory' folder for detailed reports.")

if __name__ == "__main__":
    main()