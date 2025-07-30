#!/usr/bin/env python3
"""
Offer Knowledge Base Generator for GPT Training
Creates comprehensive knowledge files from your offers for GPT Q&A training
"""

import os
import json
import csv
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any
import re

class OfferKnowledgeGenerator:
    """
    Generate comprehensive knowledge base files from offer data
    """
    
    def __init__(self, output_folder: str = "gpt_knowledge_base"):
        self.output_folder = Path(output_folder)
        self.output_folder.mkdir(exist_ok=True)
        
    def load_processing_report(self, report_path: str = "processing_report.txt") -> List[Dict]:
        """Load and parse offers from processing report"""
        if not os.path.exists(report_path):
            print(f"❌ Processing report not found: {report_path}")
            return []
        
        print(f"📋 Loading offers from: {report_path}")
        
        offers = []
        
        try:
            with open(report_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Split into offer blocks
            blocks = content.split('-' * 30)
            
            for block in blocks:
                if 'Title:' not in block:
                    continue
                
                lines = [line.strip() for line in block.split('\n') if line.strip()]
                
                offer_data = {}
                current_images = []
                in_images_section = False
                
                for line in lines:
                    if line.startswith('Title:'):
                        offer_data['title'] = line.split(':', 1)[1].strip()
                    elif line.startswith('Category:'):
                        offer_data['category'] = line.split(':', 1)[1].strip()
                    elif line.startswith('Product:'):
                        offer_data['product'] = line.split(':', 1)[1].strip()
                    elif line.startswith('Price:'):
                        offer_data['price'] = line.split(':', 1)[1].strip()
                    elif line.startswith('FOB:'):
                        offer_data['fob'] = line.split(':', 1)[1].strip()
                    elif line.startswith('Source:'):
                        offer_data['source'] = line.split(':', 1)[1].strip()
                    elif line.startswith('Images:'):
                        in_images_section = True
                        # Extract image count
                        try:
                            count = int(line.split(':')[1].strip())
                            offer_data['image_count'] = count
                        except:
                            offer_data['image_count'] = 0
                    elif in_images_section and line.startswith('- '):
                        image_filename = line[2:].strip()
                        current_images.append(image_filename)
                
                if offer_data.get('title'):
                    offer_data['images'] = current_images
                    offers.append(offer_data)
            
            print(f"✅ Loaded {len(offers)} offers")
            return offers
            
        except Exception as e:
            print(f"❌ Failed to load processing report: {e}")
            return []
    
    def load_firebase_urls(self) -> Dict[str, str]:
        """Load Firebase URLs from the most recent file"""
        firebase_files = [f for f in os.listdir('.') if f.startswith('firebase_urls_') and f.endswith('.json')]
        
        if not firebase_files:
            print("⚠️ No Firebase URLs file found - images will not have URLs")
            return {}
        
        latest_file = max(firebase_files, key=lambda x: os.path.getctime(x))
        
        try:
            with open(latest_file, 'r') as f:
                firebase_urls = json.load(f)
            print(f"📋 Loaded {len(firebase_urls)} Firebase URLs from {latest_file}")
            return firebase_urls
        except Exception as e:
            print(f"⚠️ Failed to load Firebase URLs: {e}")
            return {}
    
    def enhance_offers_with_urls(self, offers: List[Dict], firebase_urls: Dict[str, str]) -> List[Dict]:
        """Add Firebase URLs to offers"""
        for offer in offers:
            offer_image_urls = []
            for image_filename in offer.get('images', []):
                if image_filename in firebase_urls:
                    offer_image_urls.append(firebase_urls[image_filename])
            
            offer['image_urls'] = offer_image_urls
            offer['primary_image_url'] = offer_image_urls[0] if offer_image_urls else None
        
        return offers
    
    def generate_structured_knowledge_base(self, offers: List[Dict]):
        """Generate structured JSON knowledge base"""
        
        knowledge_base = {
            "metadata": {
                "generated": datetime.now().isoformat(),
                "total_offers": len(offers),
                "categories": {},
                "source": "Shoreline Products Email Processing Pipeline"
            },
            "offers": offers,
            "categories": {
                "Flooring": [],
                "Roofing": [], 
                "Other": []
            },
            "search_index": {
                "by_category": {},
                "by_price_range": {},
                "by_fob_location": {},
                "by_keywords": {}
            }
        }
        
        # Organize by category
        for offer in offers:
            category = offer.get('category', 'Other')
            if category in knowledge_base["categories"]:
                knowledge_base["categories"][category].append(offer)
            else:
                knowledge_base["categories"]["Other"].append(offer)
        
        # Generate metadata
        for category, category_offers in knowledge_base["categories"].items():
            knowledge_base["metadata"]["categories"][category] = len(category_offers)
        
        # Build search indexes
        self._build_search_indexes(knowledge_base, offers)
        
        # Save structured knowledge base
        kb_path = self.output_folder / "structured_knowledge_base.json"
        with open(kb_path, 'w', encoding='utf-8') as f:
            json.dump(knowledge_base, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Generated structured knowledge base: {kb_path}")
        return knowledge_base
    
    def _build_search_indexes(self, knowledge_base: Dict, offers: List[Dict]):
        """Build search indexes for fast lookups"""
        
        # By category
        for offer in offers:
            category = offer.get('category', 'Other')
            if category not in knowledge_base["search_index"]["by_category"]:
                knowledge_base["search_index"]["by_category"][category] = []
            knowledge_base["search_index"]["by_category"][category].append(offer['title'])
        
        # By price range
        price_ranges = {
            "under_1": [],      # Under $1
            "1_to_5": [],       # $1-$5
            "5_to_20": [],      # $5-$20
            "20_to_50": [],     # $20-$50
            "over_50": []       # Over $50
        }
        
        for offer in offers:
            price_str = offer.get('price', '').replace('$', '').split('/')[0]
            try:
                price = float(price_str)
                if price < 1:
                    price_ranges["under_1"].append(offer['title'])
                elif price < 5:
                    price_ranges["1_to_5"].append(offer['title'])
                elif price < 20:
                    price_ranges["5_to_20"].append(offer['title'])
                elif price < 50:
                    price_ranges["20_to_50"].append(offer['title'])
                else:
                    price_ranges["over_50"].append(offer['title'])
            except:
                pass
        
        knowledge_base["search_index"]["by_price_range"] = price_ranges
        
        # By FOB location
        for offer in offers:
            fob = offer.get('fob', 'Unknown')
            if fob not in knowledge_base["search_index"]["by_fob_location"]:
                knowledge_base["search_index"]["by_fob_location"][fob] = []
            knowledge_base["search_index"]["by_fob_location"][fob].append(offer['title'])
        
        # By keywords
        keywords = {}
        for offer in offers:
            # Extract keywords from title and product
            text = f"{offer.get('title', '')} {offer.get('product', '')}".lower()
            
            # Common flooring/building keywords
            common_keywords = [
                'spc', 'hdpc', 'laminate', 'vinyl', 'plank', 'tile', 'flooring',
                'roofing', 'shingles', 'felt', 'underlayment', 'waterproof',
                'rigid', 'core', 'engineered', 'luxury', 'commercial', 'residential'
            ]
            
            for keyword in common_keywords:
                if keyword in text:
                    if keyword not in keywords:
                        keywords[keyword] = []
                    keywords[keyword].append(offer['title'])
        
        knowledge_base["search_index"]["by_keywords"] = keywords
    
    def generate_gpt_training_prompts(self, offers: List[Dict]):
        """Generate Q&A training prompts for GPT"""
        
        prompts = []
        
        # Generate different types of questions
        for offer in offers:
            title = offer.get('title', 'Unknown')
            category = offer.get('category', 'Other')
            product = offer.get('product', 'Unknown')
            price = offer.get('price', 'Contact for pricing')
            fob = offer.get('fob', 'Various locations')
            
            # Question type 1: Direct product inquiry
            q1 = f"What can you tell me about {title}?"
            a1 = f"{title} is a {category.lower()} product. It's {product} with pricing at {price}. The FOB location is {fob}."
            if offer.get('image_count', 0) > 0:
                a1 += f" We have {offer['image_count']} product images available."
            
            prompts.append({"question": q1, "answer": a1, "category": category, "offer_title": title})
            
            # Question type 2: Category-based inquiry
            if category != "Other":
                q2 = f"Do you have any {category.lower()} products available?"
                a2 = f"Yes, we have {category.lower()} products including {title}. This is {product} priced at {price} FOB {fob}."
                prompts.append({"question": q2, "answer": a2, "category": category, "offer_title": title})
            
            # Question type 3: Price inquiry
            q3 = f"What's the price for {title}?"
            a3 = f"The price for {title} is {price}. This is FOB {fob}."
            prompts.append({"question": q3, "answer": a3, "category": category, "offer_title": title})
            
            # Question type 4: Location/shipping inquiry
            q4 = f"Where does {title} ship from?"
            a4 = f"{title} ships FOB {fob}. This {category.lower()} product is {product}."
            prompts.append({"question": q4, "answer": a4, "category": category, "offer_title": title})
            
            # Question type 5: Product specification inquiry
            if 'SPC' in product or 'HDPC' in product:
                q5 = f"What are the specifications for {title}?"
                a5 = f"{title} is {product}. It's priced at {price} FOB {fob}."
                if offer.get('image_count', 0) > 0:
                    a5 += f" We have detailed product images available."
                prompts.append({"question": q5, "answer": a5, "category": category, "offer_title": title})
        
        # Save training prompts
        prompts_path = self.output_folder / "gpt_training_prompts.json"
        with open(prompts_path, 'w', encoding='utf-8') as f:
            json.dump(prompts, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Generated {len(prompts)} training prompts: {prompts_path}")
        
        # Also save as JSONL for GPT fine-tuning
        jsonl_path = self.output_folder / "gpt_training_prompts.jsonl"
        with open(jsonl_path, 'w', encoding='utf-8') as f:
            for prompt in prompts:
                training_example = {
                    "messages": [
                        {"role": "user", "content": prompt["question"]},
                        {"role": "assistant", "content": prompt["answer"]}
                    ]
                }
                f.write(json.dumps(training_example) + '\n')
        
        print(f"✅ Generated GPT fine-tuning file: {jsonl_path}")
        
        return prompts
    
    def generate_comprehensive_text_knowledge(self, offers: List[Dict]):
        """Generate comprehensive text-based knowledge file"""
        
        knowledge_text = []
        
        # Header
        knowledge_text.append("SHORELINE PRODUCTS OFFER KNOWLEDGE BASE")
        knowledge_text.append("=" * 50)
        knowledge_text.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        knowledge_text.append(f"Total Offers: {len(offers)}")
        knowledge_text.append("")
        
        # Category summaries
        categories = {}
        for offer in offers:
            cat = offer.get('category', 'Other')
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(offer)
        
        knowledge_text.append("CATEGORY OVERVIEW:")
        knowledge_text.append("-" * 20)
        for category, cat_offers in categories.items():
            knowledge_text.append(f"{category}: {len(cat_offers)} offers")
        knowledge_text.append("")
        
        # Detailed offers by category
        for category, cat_offers in categories.items():
            knowledge_text.append(f"{category.upper()} OFFERS:")
            knowledge_text.append("=" * 30)
            knowledge_text.append("")
            
            for offer in cat_offers:
                knowledge_text.append(f"PRODUCT: {offer.get('title', 'Unknown')}")
                knowledge_text.append(f"  Category: {offer.get('category', 'Unknown')}")
                knowledge_text.append(f"  Product Type: {offer.get('product', 'Unknown')}")
                knowledge_text.append(f"  Price: {offer.get('price', 'Contact for pricing')}")
                knowledge_text.append(f"  FOB Location: {offer.get('fob', 'Various locations')}")
                knowledge_text.append(f"  Source File: {offer.get('source', 'Unknown')}")
                knowledge_text.append(f"  Images Available: {offer.get('image_count', 0)}")
                
                if offer.get('primary_image_url'):
                    knowledge_text.append(f"  Primary Image: {offer['primary_image_url']}")
                
                knowledge_text.append("")
        
        # FAQ section
        knowledge_text.append("FREQUENTLY ASKED QUESTIONS:")
        knowledge_text.append("=" * 35)
        knowledge_text.append("")
        
        # Generate FAQ from data
        faq_data = self._generate_faq_from_offers(offers)
        for qa in faq_data:
            knowledge_text.append(f"Q: {qa['question']}")
            knowledge_text.append(f"A: {qa['answer']}")
            knowledge_text.append("")
        
        # Save comprehensive text
        text_path = self.output_folder / "comprehensive_knowledge_base.txt"
        with open(text_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(knowledge_text))
        
        print(f"✅ Generated comprehensive text knowledge: {text_path}")
    
    def _generate_faq_from_offers(self, offers: List[Dict]) -> List[Dict]:
        """Generate FAQ from offer data"""
        
        faqs = []
        
        # Category questions
        categories = set(offer.get('category', 'Other') for offer in offers)
        for category in categories:
            if category != 'Other':
                cat_offers = [o for o in offers if o.get('category') == category]
                faqs.append({
                    "question": f"What {category.lower()} products do you have available?",
                    "answer": f"We have {len(cat_offers)} {category.lower()} products available, including {', '.join([o.get('title', '') for o in cat_offers[:3]])}{'...' if len(cat_offers) > 3 else ''}."
                })
        
        # Price range questions
        faqs.append({
            "question": "What price ranges do you offer?",
            "answer": "Our products range from under $1 per square foot to premium options over $50 per unit, depending on the product type and specifications."
        })
        
        # FOB location questions
        fob_locations = set(offer.get('fob', 'Unknown') for offer in offers if offer.get('fob'))
        faqs.append({
            "question": "What are your shipping locations?",
            "answer": f"We ship FOB from multiple locations including {', '.join(list(fob_locations)[:5])}{'...' if len(fob_locations) > 5 else ''}."
        })
        
        # Product availability
        faqs.append({
            "question": "How many products do you have available?",
            "answer": f"We currently have {len(offers)} products available across flooring, roofing, and other building materials."
        })
        
        # Image availability
        offers_with_images = [o for o in offers if o.get('image_count', 0) > 0]
        faqs.append({
            "question": "Do you have product images available?",
            "answer": f"Yes, we have images for {len(offers_with_images)} of our products to help you make informed decisions."
        })
        
        return faqs
    
    def generate_csv_export(self, offers: List[Dict]):
        """Generate CSV export for easy spreadsheet analysis"""
        
        csv_path = self.output_folder / "offers_knowledge_export.csv"
        
        with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = [
                'title', 'category', 'product', 'price', 'fob', 'source', 
                'image_count', 'primary_image_url', 'all_image_urls'
            ]
            
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            for offer in offers:
                writer.writerow({
                    'title': offer.get('title', ''),
                    'category': offer.get('category', ''),
                    'product': offer.get('product', ''),
                    'price': offer.get('price', ''),
                    'fob': offer.get('fob', ''),
                    'source': offer.get('source', ''),
                    'image_count': offer.get('image_count', 0),
                    'primary_image_url': offer.get('primary_image_url', ''),
                    'all_image_urls': '; '.join(offer.get('image_urls', []))
                })
        
        print(f"✅ Generated CSV export: {csv_path}")

def main():
    """Generate comprehensive knowledge base"""
    print("🧠 Offer Knowledge Base Generator for GPT Training")
    print("=" * 60)
    print("🎯 This will create comprehensive knowledge files for GPT training")
    print()
    
    # Check for required files
    if not os.path.exists("processing_report.txt"):
        print("❌ processing_report.txt not found!")
        print("💡 Run the MSG processing pipeline first")
        return
    
    # Initialize generator
    generator = OfferKnowledgeGenerator()
    
    # Load offer data
    offers = generator.load_processing_report()
    
    if not offers:
        print("❌ No offers loaded. Cannot generate knowledge base.")
        return
    
    # Load Firebase URLs if available
    firebase_urls = generator.load_firebase_urls()
    
    # Enhance offers with image URLs
    if firebase_urls:
        offers = generator.enhance_offers_with_urls(offers, firebase_urls)
        print(f"✅ Enhanced offers with {len(firebase_urls)} Firebase image URLs")
    
    # Generate all knowledge base formats
    print("\n📚 Generating knowledge base files...")
    
    # 1. Structured JSON knowledge base
    knowledge_base = generator.generate_structured_knowledge_base(offers)
    
    # 2. GPT training prompts
    prompts = generator.generate_gpt_training_prompts(offers)
    
    # 3. Comprehensive text knowledge
    generator.generate_comprehensive_text_knowledge(offers)
    
    # 4. CSV export
    generator.generate_csv_export(offers)
    
    # Summary
    print(f"\n🎉 KNOWLEDGE BASE GENERATION COMPLETE!")
    print("=" * 50)
    print(f"✅ Processed {len(offers)} offers")
    print(f"✅ Generated {len(prompts)} training prompts")
    print(f"✅ Created 4 knowledge base formats")
    print()
    print("📁 Generated files:")
    print("   📄 structured_knowledge_base.json - Complete searchable database")
    print("   📄 gpt_training_prompts.json - Q&A training data")
    print("   📄 gpt_training_prompts.jsonl - GPT fine-tuning format")
    print("   📄 comprehensive_knowledge_base.txt - Human-readable text")
    print("   📄 offers_knowledge_export.csv - Spreadsheet format")
    print()
    print("🎯 Next steps:")
    print("   1. Use .jsonl file for GPT fine-tuning")
    print("   2. Use .json files for custom GPT knowledge")
    print("   3. Use .txt file for general AI training")
    print("   4. Use .csv for analysis and spreadsheet work")

if __name__ == "__main__":
    main()