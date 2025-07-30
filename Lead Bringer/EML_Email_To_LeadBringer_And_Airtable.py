from __future__ import annotations
"""
EML_Email_To_Knowledge_JSON_dedupe.py
=====================================
Local-only pipeline that exports a deduplicated offers JSON for GPT.
- Keeps the most-recent email per normalized subject.
- Falls back to filename stem when `Subject:` is missing.
- Prioritizes HTML body for content extraction.
- Saves embedded images to a local folder.

Run:
```
cd "C:/Users/Jeff.Masingill/Desktop/Lead Bringer"
python ".\\EML_Email_To_Knowledge_JSON_dedupe.py"
```
"""

import os
import re
import json
import sys
import email
import hashlib
import logging
import mimetypes
import base64
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Tuple
from dataclasses import dataclass, asdict

from bs4 import BeautifulSoup  # pip install beautifulsoup4
import configparser

# --- Logging Configuration ---
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s | %(levelname)s | %(message)s",
                    handlers=[logging.FileHandler("email_pipeline.log", encoding="utf-8"),
                              logging.StreamHandler(stream=sys.stdout)])
log = logging.getLogger(__name__)

# --- Regular Expressions ---
PRICE_RGX = re.compile(r"\$\s?(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)", re.I)
QTY_RGX = re.compile(r"(\d{2,6}(?:,\d{3})?)\s*(?:sqft|sf|pcs|ctns?)", re.I)
FOB_RGX = re.compile(r"\bFOB[:\-]?\s*([A-Za-z ]{2,40})", re.I)
SUBJ_CLEAN_RGX = re.compile(r"^(re:|fw:|fwd:)\s*", re.I)

@dataclass
class ProductOffer:
    title: str
    category: str
    product_description: str
    price: str
    fob_location: str
    available_quantity: str
    primary_image: str
    more_images: List[str]
    source_email: str
    date_received: str
    message_id: str
    status: str = "Unreviewed"

class EmailOfferPipeline:
    def __init__(self, cfg_path: str = "config.ini") -> None:
        self.cfg = self._load_cfg(cfg_path)
        self.email_dir = Path(self.cfg['PATHS']['EMAIL_FOLDER'])
        self.image_dir = Path(self.cfg['PATHS']['IMAGE_OUTPUT_FOLDER'])
        self.hash_file = Path(self.cfg['PATHS']['PROCESSED_HASHES_FILE'])
        self.image_dir.mkdir(parents=True, exist_ok=True)
        self.seen = self._load_hashes()

    def _load_cfg(self, p: str) -> configparser.ConfigParser:
        cfg = configparser.ConfigParser()
        if not Path(p).exists():
            desktop = Path.home() / 'Desktop'
            cfg['PATHS'] = {
                'EMAIL_FOLDER': str(desktop / 'Lead Bringer Email Offers'),
                'IMAGE_OUTPUT_FOLDER': str(desktop / 'Lead Bringer' / 'extracted_images'),
                'PROCESSED_HASHES_FILE': str(desktop / 'Lead Bringer' / 'processed_ids.json'),
            }
            with open(p, 'w', encoding='utf-8') as f:
                cfg.write(f)
        cfg.read(p, encoding='utf-8')
        return cfg

    def _load_hashes(self) -> set[str]:
        return set(json.loads(self.hash_file.read_text(encoding='utf-8'))) if self.hash_file.exists() else set()

    def _save_hash(self, mid: str):
        self.seen.add(mid)
        self.hash_file.write_text(json.dumps(list(self.seen), indent=2), encoding='utf-8')

    @staticmethod
    def _msg_id(msg: email.message.Message, filepath: Path) -> str:
        """Generate a unique ID, falling back to a hash of the file content."""
        msg_id = msg.get('Message-ID')
        if msg_id:
            return msg_id
        # Fallback for emails missing a Message-ID header
        return f"<{hashlib.md5(filepath.read_bytes()).hexdigest()}>"

    @staticmethod
    def _as_dt(ds: str):
        try:
            return email.utils.parsedate_to_datetime(ds).astimezone(timezone.utc)
        except (TypeError, ValueError):
            return datetime.min.replace(tzinfo=timezone.utc)

    @staticmethod
    def _clean_subj(s: str) -> str:
        return SUBJ_CLEAN_RGX.sub('', s).casefold().strip()

    @staticmethod
    def _body(msg: email.message.Message) -> str:
        """Extracts the best-quality text body, prioritizing HTML."""
        html_body, plain_body = '', ''
        for part in msg.walk():
            ctype = part.get_content_type()
            cdispo = str(part.get('Content-Disposition'))
            if "attachment" in cdispo:
                continue

            if ctype == 'text/html' and not html_body:
                try:
                    html_body = part.get_payload(decode=True).decode(errors='ignore')
                except Exception:
                    continue
            elif ctype == 'text/plain' and not plain_body:
                try:
                    plain_body = part.get_payload(decode=True).decode(errors='ignore')
                except Exception:
                    continue
        
        if html_body:
            soup = BeautifulSoup(html_body, 'html.parser')
            return soup.get_text(' ', strip=True)
        return plain_body

    def _save_imgs(self, msg: email.message.Message) -> List[str]:
        """Saves embedded images and returns their new filenames."""
        saved_images = []
        for part in msg.walk():
            if part.get_content_maintype() == 'image':
                img_data = part.get_payload(decode=True)
                if not img_data:
                    continue
                
                cid = part.get('Content-ID', '').strip('<>')
                ext = mimetypes.guess_extension(part.get_content_type()) or '.bin'
                
                # Create a unique filename from CID or a hash of the image data
                if cid:
                    filename = f"{cid}{ext}"
                else:
                    filename = f"img_{hashlib.md5(img_data).hexdigest()}{ext}"
                
                filepath = self.image_dir / filename
                try:
                    filepath.write_bytes(img_data)
                    saved_images.append(filename)
                except OSError as e:
                    log.error(f"Could not write image {filename}: {e}")
        return saved_images

    @staticmethod
    def _cat(sub: str, body: str) -> str:
        t = f"{sub} {body}".lower()
        if 'spc' in t: return 'SPC Flooring'
        if 'lvt' in t: return 'LVT Flooring'
        if 'laminate' in t: return 'Laminate Flooring'
        if 'tile' in t: return 'Tile'
        if 'solid' in t and 'hardwood' in t: return 'Solid Hardwood'
        return 'Other'

    @staticmethod
    def _m(rgx: re.Pattern, txt: str) -> str:
        match = rgx.search(txt)
        return match.group(1).strip() if match and match.groups() else (match.group(0).strip() if match else '')

    def process(self):
        files = list(self.email_dir.glob('*.eml'))
        log.info(f"{len(files)} eml files found in {self.email_dir}")

        latest: Dict[str, Dict] = {}
        new_offers_count = 0
        for f in files:
            try:
                with f.open('rb') as fp:
                    msg = email.message_from_binary_file(fp)
                
                mid = self._msg_id(msg, f)
                if mid in self.seen:
                    continue

                subj = msg.get('Subject') or f.stem
                key = self._clean_subj(subj)
                dt_raw = msg.get('Date', '')
                dt = self._as_dt(dt_raw)
                body = self._body(msg)
                imgs = self._save_imgs(msg)

                offer = ProductOffer(
                    title=subj,
                    category=self._cat(subj, body),
                    product_description=body,
                    price=self._m(PRICE_RGX, body),
                    fob_location=self._m(FOB_RGX, body),
                    available_quantity=self._m(QTY_RGX, body),
                    primary_image=imgs[0] if imgs else '',
                    more_images=imgs[1:] if len(imgs) > 1 else [],
                    source_email=email.utils.parseaddr(msg.get('From', ''))[1],
                    date_received=dt_raw,
                    message_id=mid,
                )

                prev = latest.get(key)
                if prev is None or dt > self._as_dt(prev['date_received']):
                    latest[key] = asdict(offer)
                
                self._save_hash(mid)
                log.info(f"Parsed {subj[:50]}…")
                new_offers_count += 1

            except Exception as e:
                log.error(f"Failed to process file {f.name}: {e}", exc_info=True)

        if not latest:
            log.info('No new offers – all up to date.')
            return

        out_path = self.email_dir / f"offers_{datetime.now():%Y%m%d_%H%M%S}.json"
        out_path.write_text(json.dumps(list(latest.values()), indent=2, ensure_ascii=False), encoding='utf-8')
        log.info(f"Processed {new_offers_count} new emails. Wrote {len(latest)} unique offers -> {out_path}")

if __name__ == '__main__':
    try:
        EmailOfferPipeline().process()
    except Exception as e:
        log.error(f"Pipeline failed critically: {e}", exc_info=True)
        sys.exit(1)
