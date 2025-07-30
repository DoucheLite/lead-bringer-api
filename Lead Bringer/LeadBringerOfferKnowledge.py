#!/usr/bin/env python3
"""
HandleMultipleImages.py - Smart image filtering and multiple photo handling
"""

import os
import re
import time
import requests
import msal
import pandas as pd
import gspread
from datetime import datetime, timedelta, timezone
from pathlib import Path
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# ─── CONFIG (same as before) ───────────────────────────────────────────
CLIENT_ID         = "c3e0fb48-c048-4341-a496-9ba10f3e9854"
TENANT_ID         = "8985a392-aebd-4201-9885-257d3bc8579d"
AUTHORITY         = f"https://login.microsoftonline.com/{TENANT_ID}"
SCOPES            = ["Mail.Read"]
USERNAME          = "jeffm@shorelineus.com"
RSS_FOLDER_ID     = "AAMkAGNmOGY4MzRiLTVmZDUtNGEyOC04NjMyLWYxZGJiYzZjMzQ1ZgAuAAAAAADX08WiaDhtRor3ZdC7DQ0RAQDrVF3CfRACQowyZVjhJL9SAAAAAB2pAAA="
GOOGLE_SHEET_ID   = "1f8F_ceaHgB9cjiNSUbdipQHCRsq6pOaqYRzaDWhHqm8"
WORKSHEET_NAME    = "Sheet1"
GOOGLE_CLIENT_SECRETS = Path.home() / "brandt_data" / "client_secrets.json"
DRIVE_FOLDER_ID = "1RzQCxq9-oqM7zDJRYxAlefLadCPH_aXu"

# ─── IMAGE FILTERING RULES ─────────────────────────────────────────────
TRACKING_PIXEL_PATTERNS = [
    's.gif', 'spacer.gif', 'pixel.gif', 'blank.gif', 'track.gif',
    '1x1.gif', '1x1.png', 'beacon.gif', 'clear.gif', 'transparent.gif',
    'tracking', 'analytics', 'metric', 'mailtrack', 'emailtrack',
    'on.jsp', 'track.jsp', 'open.jsp', 'click.jsp',  # JSP trackers
    'track.php', 'open.php', 'click.php',  # PHP trackers
    'track.aspx', 'open.aspx',  # .NET trackers
    '/on/', '/track/', '/open/', '/click/'  # Common tracking paths
]

TRACKING_EXTENSIONS = ['.jsp', '.php', '.aspx', '.cgi', '.pl']

MINIMUM_IMAGE_SIZE = 50  # Ignore images smaller than 50x50 pixels

def is_tracking_pixel(img_url: str, img_tag=None) -> bool:
    """Detect if an image is likely a tracking pixel or tracking script"""
    url_lower = img_url.lower()
    
    # Check URL patterns
    for pattern in TRACKING_PIXEL_PATTERNS:
        if pattern in url_lower:
            return True
    
    # Check for tracking script extensions pretending to be images
    parsed_url = urlparse(img_url)
    path = parsed_url.path.lower()
    
    # Check if it's a script endpoint (like on.jsp)
    for ext in TRACKING_EXTENSIONS:
        if path.endswith(ext):
            print(f"      🚫 Blocked tracking script: {path}")
            return True
    
    # Check dimensions if available
    if img_tag:
        width = img_tag.get('width', '').replace('px', '')
        height = img_tag.get('height', '').replace('px', '')
        try:
            w = int(width) if width else 999
            h = int(height) if height else 999
            if w < MINIMUM_IMAGE_SIZE or h < MINIMUM_IMAGE_SIZE:
                return True
        except:
            pass
    
    # Check common tracking domains
    tracking_domains = ['doubleclick', 'googleadservices', 'google-analytics', 
                       'facebook.com/tr', 'amazon-adsystem', 'list-manage.com/track',
                       'constantcontact', 'mailchimp', 'sendgrid', 'hubspot',
                       'salesforce', 'marketo', 'eloqua']
    for domain in tracking_domains:
        if domain in url_lower:
            return True
    
    # Check if URL contains common tracking parameters
    if any(param in url_lower for param in ['utm_', 'mc_', 'ml_', 'et_', 'fbclid']):
        return True
    
    return False

def extract_quality_images(html: str) -> list:
    """Extract images, filtering out tracking pixels"""
    if not html:
        return []
    
    soup = BeautifulSoup(html, 'html.parser')
    found_images = []
    
    print("  🔍 Analyzing images in email...")
    
    # Check all img tags
    for img in soup.find_all('img'):
        src = img.get('src', '')
        if not src or not src.startswith('http'):
            continue
        
        # Check if it's a tracking pixel
        if is_tracking_pixel(src, img):
            print(f"    ❌ Filtered tracking pixel: {src[:50]}...")
            continue
        
        # Check alt text for product indicators
        alt = img.get('alt', '').lower()
        if any(word in alt for word in ['product', 'floor', 'tile', 'carpet', 'stone']):
            print(f"    ✅ Product image found (alt: {alt[:30]}...)")
            found_images.insert(0, src)  # Prioritize images with product alt text
        else:
            found_images.append(src)
    
    # Remove duplicates while preserving order
    unique = list(dict.fromkeys(found_images))
    
    print(f"  📸 Found {len(unique)} quality images (filtered {len(soup.find_all('img')) - len(unique)} tracking/small images)")
    
    return unique

# ─── MULTIPLE IMAGE HANDLING OPTIONS ───────────────────────────────────

def handle_multiple_images_single(images: list, creds, title: str) -> str:
    """Option 1: Upload only the best/first image"""
    if not images:
        return ''
    
    # Try to upload the first valid image
    for img_url in images[:3]:  # Try up to 3
        drive_url = upload_image_to_drive(img_url, creds, title)
        if drive_url:
            return drive_url
    
    return images[0]  # Fallback to original URL

def handle_multiple_images_collage(images: list, creds, title: str) -> str:
    """Option 2: Create a collage (advanced - requires PIL)"""
    # This would create a single image from multiple images
    # Requires: pip install Pillow
    pass

def handle_multiple_images_album(images: list, creds, title: str) -> list:
    """Option 3: Upload all images and return multiple URLs"""
    uploaded_urls = []
    
    for i, img_url in enumerate(images[:4]):  # Limit to 4 images
        print(f"    Uploading image {i+1}/{min(len(images), 4)}...")
        drive_url = upload_image_to_drive(img_url, creds, f"{title}_img{i+1}")
        if drive_url:
            uploaded_urls.append(drive_url)
        time.sleep(1)  # Prevent rate limiting
    
    return uploaded_urls

# ─── SIMPLIFIED UPLOAD FUNCTION ────────────────────────────────────────
def upload_image_to_drive(image_url: str, creds, title: str) -> str:
    """Upload single image to Drive"""
    try:
        # Download image
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(image_url, headers=headers, timeout=15)
        if response.status_code != 200:
            return ""
        
        # Check content type
        content_type = response.headers.get('content-type', '')
        if 'image' not in content_type:
            print(f"      ⚠️  Not an image: {content_type}")
            return ""
        
        # Save temporarily
        image_dir = Path.home() / "brandt_data" / "temp_images"
        image_dir.mkdir(parents=True, exist_ok=True)
        
        # Create filename from title
        safe_title = re.sub(r'[^\w\s-]', '', title)[:50]
        ext = '.jpg'
        if 'png' in content_type:
            ext = '.png'
        elif 'gif' in content_type:
            ext = '.gif'
        
        filename = f"{safe_title}_{int(time.time())}{ext}"
        filepath = image_dir / filename
        
        with open(filepath, 'wb') as f:
            f.write(response.content)
        
        # Upload to Drive
        service = build("drive", "v3", credentials=creds)
        file_metadata = {"name": filename, "parents": [DRIVE_FOLDER_ID]}
        media = MediaFileUpload(filepath, mimetype=content_type)
        file = service.files().create(body=file_metadata, media_body=media, fields="id").execute()
        
        # Make public
        service.permissions().create(
            fileId=file['id'], 
            body={"role": "reader", "type": "anyone"}
        ).execute()
        
        # Clean up
        try:
            os.remove(filepath)
        except:
            pass
        
        return f"https://drive.google.com/uc?id={file['id']}"
        
    except Exception as e:
        print(f"      ❌ Upload failed: {str(e)[:50]}")
        return ""

# ─── AUTH FUNCTIONS (same as before) ───────────────────────────────────
def ms_auth() -> str:
    app = msal.PublicClientApplication(CLIENT_ID, authority=AUTHORITY)
    accounts = app.get_accounts(username=USERNAME)
    token = app.acquire_token_silent(SCOPES, account=accounts[0]) if accounts else None
    if not token:
        flow = app.initiate_device_flow(scopes=SCOPES)
        print(flow["message"])
        token = app.acquire_token_by_device_flow(flow)
    if "access_token" not in token:
        raise RuntimeError("Microsoft authentication failed")
    return token["access_token"]

def google_auth():
    scopes = ["https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/spreadsheets"]
    flow = InstalledAppFlow.from_client_secrets_file(GOOGLE_CLIENT_SECRETS, scopes=scopes)
    creds = flow.run_local_server(port=0)
    return creds

# ─── PARSING FUNCTIONS ─────────────────────────────────────────────────
def clean_title(raw: str) -> str:
    t = raw.lower()
    t = re.sub(r'^(re:|fw:|fwd:)', '', t, flags=re.I).strip()
    t = re.sub(r'slp\s*-+', '', t, flags=re.I).strip()
    t = re.sub(r'\b(steal it|blowout|specials?|crazy|cheap|offer|deals?)\b', '', t, flags=re.I)
    t = re.sub(r'[-:;!?,]+$', '', t).strip()
    return ' '.join(word.capitalize() for word in t.split())

def fetch_full_email_with_attachments(msg_id: str, token: str) -> dict:
    """Fetch email with body AND attachments"""
    # Get email content
    url = f"https://graph.microsoft.com/v1.0/me/messages/{msg_id}"
    params = {"$select": "id,subject,body,receivedDateTime,hasAttachments"}
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(url, params=params, headers=headers, timeout=10)
    r.raise_for_status()
    email = r.json()
    
    # Get attachments if present
    email['attachmentImages'] = []
    if email.get('hasAttachments'):
        att_url = f"https://graph.microsoft.com/v1.0/me/messages/{msg_id}/attachments"
        att_response = requests.get(att_url, headers=headers)
        if att_response.status_code == 200:
            for attachment in att_response.json().get('value', []):
                # Check if it's an image attachment
                name = attachment.get('name', '').lower()
                if any(ext in name for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp']):
                    if attachment.get('@odata.type') == '#microsoft.graph.fileAttachment':
                        # Store attachment data
                        email['attachmentImages'].append({
                            'name': attachment['name'],
                            'contentBytes': attachment['contentBytes'],
                            'contentType': attachment.get('contentType', 'image/jpeg')
                        })
                        print(f"      📎 Found attachment: {attachment['name']}")
    
    return email

def upload_attachment_to_drive(attachment: dict, creds, title: str) -> str:
    """Upload email attachment to Drive"""
    try:
        # Decode base64 content
        image_content = base64.b64decode(attachment['contentBytes'])
        
        # Save temporarily
        image_dir = Path.home() / "brandt_data" / "temp_images"
        image_dir.mkdir(parents=True, exist_ok=True)
        
        filename = f"{title}_{attachment['name']}"
        filename = re.sub(r'[^\w\s.-]', '', filename)  # Clean filename
        filepath = image_dir / filename
        
        with open(filepath, 'wb') as f:
            f.write(image_content)
        
        # Upload to Drive
        service = build("drive", "v3", credentials=creds)
        file_metadata = {"name": filename, "parents": [DRIVE_FOLDER_ID]}
        media = MediaFileUpload(filepath, mimetype=attachment['contentType'])
        file = service.files().create(body=file_metadata, media_body=media, fields="id").execute()
        
        # Make public
        service.permissions().create(
            fileId=file['id'], 
            body={"role": "reader", "type": "anyone"}
        ).execute()
        
        # Clean up
        try:
            os.remove(filepath)
        except:
            pass
        
        return f"https://drive.google.com/uc?id={file['id']}"
        
    except Exception as e:
        print(f"      ❌ Attachment upload failed: {str(e)[:50]}")
        return ""

def clean_text(html: str) -> str:
    text = re.sub(r'<[^>]+>', ' ', html or '').replace('\n', ' ')
    return ' '.join(text.split())

# Regex patterns
PRICE_RX = r"\$(\d+(?:\.\d+)?)(?:\s*/\s*|\s+)([A-Za-z]{1,4})"
FOB_RX   = r"\bFOB\s*:?\s*([A-Za-z0-9\s,]+)"
THICK_RX = r"(\d+(?:\.\d+)?\s*mm)"
WL_RX    = r"(\d+(?:\.\d+)?\s*mil\s*WL)"
DIM_RX   = r'(\d+(?:\"|")??\s*[x×]\s*\d+(?:\"|")??|\d+\s*x\s*\d+)'

def parse_offer(email: dict, creds) -> dict:
    html = email.get('body', {}).get('content', '')
    text = clean_text(html).upper()
    
    # Extract fields
    m = re.search(PRICE_RX, text)
    price, unit = (m.group(1), m.group(2)) if m else ('', '')
    thickness  = '; '.join(re.findall(THICK_RX, text))
    wl         = '; '.join(re.findall(WL_RX, text))
    dimensions = '; '.join(re.findall(DIM_RX, text))
    f = re.search(FOB_RX, text)
    fob = f.group(1).strip() if f else ''
    
    raw_title = email.get('subject', '')
    clean_name = clean_title(raw_title)
    
    print(f"\n📦 Processing: {clean_name}")
    
    # Extract quality images from email body (filters out tracking pixels)
    inline_images = extract_quality_images(html)
    
    # Get attachment images
    attachment_images = []
    for att in email.get('attachmentImages', []):
        print(f"  📎 Processing attachment: {att['name']}")
        drive_url = upload_attachment_to_drive(att, creds, clean_name)
        if drive_url:
            attachment_images.append(drive_url)
    
    # Combine all images (attachments first, then inline)
    all_images = attachment_images + inline_images
    
    # Upload inline images that aren't already in Drive
    all_photo_urls = []
    
    for i, img_url in enumerate(all_images[:5]):  # Limit to 5 total
        if 'drive.google.com' in img_url:
            # Already uploaded (attachment)
            all_photo_urls.append(img_url)
        else:
            # Upload inline image
            print(f"    Image {i+1}/{min(len(all_images), 5)}...")
            drive_url = upload_image_to_drive(img_url, creds, f"{clean_name}_img{i+1}")
            if drive_url:
                all_photo_urls.append(drive_url)
            else:
                # Fallback to original URL if upload fails
                all_photo_urls.append(img_url)
        
        if i < len(all_images) - 1:  # Don't delay after last image
            time.sleep(1)  # Prevent rate limiting
    
    # For Glide array column: comma-separated URLs
    photos_array = ','.join(all_photo_urls) if all_photo_urls else ''
    
    # Also keep first photo separate for card view
    primary_photo = all_photo_urls[0] if all_photo_urls else ''
    
    print(f"  📸 Total images: {len(all_photo_urls)} (Attachments: {len(attachment_images)}, Inline: {len(inline_images)})")
    
    return {
        'photo': primary_photo,  # For card/swipe view
        'photos': photos_array,  # For image carousel (comma-separated)
        'photo_count': len(all_photo_urls),
        'name': clean_name,
        'price': price,
        'unit': unit,
        'fob': fob,
        'thickness': thickness,
        'wl': wl,
        'dimensions': dimensions,
        'saved': False,
        'had_attachments': len(attachment_images) > 0,
        'quality_images_found': len(all_images)
    }

def push_to_sheet(df: pd.DataFrame, creds):
    client = gspread.authorize(creds)
    ws = client.open_by_key(GOOGLE_SHEET_ID).worksheet(WORKSHEET_NAME)
    
    # Columns optimized for Glide
    cols = ['photo', 'photos', 'photo_count', 'name', 'price', 'unit', 'fob', 'thickness', 'wl', 'dimensions', 'saved', 'had_attachments']
    
    for c in cols:
        if c not in df.columns:
            df[c] = False if c in ['saved', 'had_attachments'] else 0 if c == 'photo_count' else ''
    
    df_export = df[cols]
    
    ws.clear()
    ws.update([df_export.columns.tolist()] + df_export.astype(str).values.tolist(), 'A1')
    ws.freeze(rows=1)
    ws.format('A1:M1', {'textFormat': {'bold': True}})
    ws.format('E2:E', {'numberFormat': {'type': 'NUMBER', 'pattern': '0.00'}})  # price column
    
    # Statistics
    print(f"\n📊 STATISTICS:")
    print(f"  Total offers: {len(df)}")
    print(f"  Offers with attachments: {(df['had_attachments']).sum()}")
    print(f"  Offers with quality images: {(df['quality_images_found'] > 0).sum()}")
    print(f"  Offers with uploaded photos: {(df['photo'].str.contains('drive.google.com', na=False)).sum()}")
    print(f"  Average images per offer: {df['photo_count'].mean():.1f}")
    
    print(f"\n✅ Updated {len(df)} rows on Glide sheet.")

def main():
    token = ms_auth()
    creds = google_auth()
    
    since = (datetime.now(timezone.utc) - timedelta(days=7)).strftime('%Y-%m-%dT%H:%M:%SZ')
    url = f"https://graph.microsoft.com/v1.0/me/mailFolders/{RSS_FOLDER_ID}/messages"
    params = {'$top': 250, '$filter': f'receivedDateTime ge {since}'}
    headers = {'Authorization': f'Bearer {token}'}
    
    offers = []
    page = 1
    
    while url:
        print(f"\n📄 Fetching page {page}...")
        r = requests.get(url, headers=headers, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        
        for i, m in enumerate(data.get('value', [])):
            full_email = fetch_full_email_with_attachments(m['id'], token)
            offer = parse_offer(full_email, creds)
            offers.append(offer)
            
            # Rate limit prevention
            if (i + 1) % 5 == 0:
                print("  ⏳ Rate limit pause...")
                time.sleep(3)
        
        url = data.get('@odata.nextLink')
        params = None
        page += 1
    
    if offers:
        df = pd.DataFrame(offers).drop_duplicates('name', keep='first')
        push_to_sheet(df, creds)
    else:
        print("❌ No offers found.")

if __name__ == '__main__':
    main()