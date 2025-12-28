#!/usr/bin/env python3
"""
ESPRIT Complete Downloader - Fixed Version
- Better PDF naming (uses content title instead of ultraDocumentBody)
- Improved formatting for PDFs (matches browser print output)
- Cleaner folder structure
- Embeds images as base64 for offline viewing

Requirements:
    pip install beautifulsoup4
"""

from blackboard import BlackBoardClient
import json
import sys
import os
import getpass
import re
import html as html_lib
from colorama import Fore, Style, init
from urllib.parse import unquote

init()

# Check for playwright
try:
    from playwright.sync_api import sync_playwright

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


def extract_pdf_links_from_body(body_html):
    """Extract PDF links from HTML body"""
    pdf_links = []

    if not body_html:
        return pdf_links

    # Look for data-bbfile attributes
    bbfile_pattern = r'data-bbfile="({[^"]+})"'
    bbfile_matches = re.findall(bbfile_pattern, str(body_html))

    for match in bbfile_matches:
        try:
            decoded = html_lib.unescape(match)
            import json as json_lib
            file_data = json_lib.loads(decoded)

            filename = file_data.get('fileName') or file_data.get('linkName')
            if filename and filename.lower().endswith('.pdf'):
                href_pattern = rf'data-bbfile="{re.escape(match)}"[^>]*href="([^"]+)"'
                href_match = re.search(href_pattern, str(body_html))

                if href_match:
                    url = html_lib.unescape(href_match.group(1))
                    pdf_links.append({
                        'url': url,
                        'filename': filename
                    })
        except:
            pass

    # Also look for direct PDF hrefs
    pdf_href_pattern = r'href="([^"]*\.pdf[^"]*)"'
    pdf_hrefs = re.findall(pdf_href_pattern, str(body_html), re.IGNORECASE)

    for url in pdf_hrefs:
        url = html_lib.unescape(url)
        filename = url.split('/')[-1].split('?')[0]
        if filename.lower().endswith('.pdf'):
            if not any(link['url'] == url for link in pdf_links):
                pdf_links.append({'url': url, 'filename': filename})

    return pdf_links


def download_pdf(client, url, filename, save_path):
    """Download a single PDF file"""
    if url.startswith('/'):
        url = client.site + url

    filename_safe = unquote(re.sub('[<>:"/\\\\|?*]', '', filename))
    download_location = os.path.abspath(os.path.join(save_path, filename_safe))
    download_directory = os.path.dirname(download_location)

    try:
        response = client.session.get(url, allow_redirects=True)

        if response.status_code == 200:
            if not os.path.exists(download_directory):
                os.makedirs(download_directory)

            if os.path.isfile(download_location):
                print(f"      {Fore.YELLOW}⚠ Exists: {filename_safe}{Style.RESET_ALL}")
                return False
            else:
                with open(download_location, 'wb') as f:
                    f.write(response.content)
                print(f"      {Fore.GREEN}✓ Downloaded: {filename_safe}{Style.RESET_ALL}")
                return True
        else:
            print(f"      {Fore.RED}✗ Failed ({response.status_code}): {filename_safe}{Style.RESET_ALL}")
            return False
    except Exception as e:
        print(f"      {Fore.RED}✗ Error: {filename_safe} - {str(e)}{Style.RESET_ALL}")
        return False


def save_html_page(content, save_path, display_name=None):
    """Save HTML content as a clean HTML file with embedded images"""
    if not content.body:
        return False

    # Use display_name if provided (for ultraDocumentBody cases), otherwise use content title
    title_to_use = display_name if display_name else content.title

    # Clean filename for filesystem
    filename_base = re.sub('[<>:"/\\\\|?*]', '', title_to_use)
    filename = filename_base + '.html'
    download_location = os.path.abspath(os.path.join(save_path, filename))

    download_directory = os.path.dirname(download_location)

    try:
        if not os.path.exists(download_directory):
            os.makedirs(download_directory)

        if os.path.isfile(download_location):
            print(f"      {Fore.YELLOW}⚠ Exists: {filename}{Style.RESET_ALL}")
            return False

        # Process HTML body to fix image URLs and embed them
        processed_body = process_html_content(content)

        # Create clean HTML document - exactly as it appears in Blackboard
        html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{html_lib.escape(title_to_use)}</title>
    <style>
        body {{
            font-family: Arial, Helvetica, sans-serif;
            margin: 40px;
            line-height: 1.6;
            color: #333;
        }}
        img {{
            max-width: 100%;
            height: auto;
        }}
        a {{
            color: #0066cc;
        }}
        table {{
            border-collapse: collapse;
        }}
        th, td {{
            border: 1px solid #ddd;
            padding: 8px;
        }}
    </style>
</head>
<body>
{processed_body}
</body>
</html>"""

        # Save as HTML - simple and clean
        with open(download_location, 'w', encoding='utf-8') as f:
            f.write(html_content)
        print(f"      {Fore.CYAN}✓ Saved as HTML: {filename}{Style.RESET_ALL}")
        return True

    except Exception as e:
        print(f"      {Fore.RED}✗ Error: {str(e)}{Style.RESET_ALL}")
        return False


def process_html_content(content):
    """Process HTML content to convert images to base64 data URLs"""
    import base64
    from bs4 import BeautifulSoup

    try:
        soup = BeautifulSoup(content.body, 'html.parser')

        # Find all img tags
        for img in soup.find_all('img'):
            src = img.get('src')
            if not src:
                continue

            # Make URL absolute if needed
            if src.startswith('/'):
                img_url = content.client.site + src
            elif src.startswith('http'):
                img_url = src
            else:
                # Relative URL
                img_url = content.client.site + '/' + src

            try:
                # Download the image
                response = content.client.session.get(img_url, timeout=10)
                if response.status_code == 200:
                    # Determine mime type
                    content_type = response.headers.get('content-type', 'image/png')

                    # Convert to base64
                    img_base64 = base64.b64encode(response.content).decode('utf-8')

                    # Create data URL
                    data_url = f"data:{content_type};base64,{img_base64}"

                    # Update img src
                    img['src'] = data_url
                    print(f"        {Fore.CYAN}✓ Embedded image from: {src[:50]}...{Style.RESET_ALL}")
            except Exception as e:
                print(f"        {Fore.YELLOW}⚠ Could not load image: {src[:50]}... ({str(e)}){Style.RESET_ALL}")

        return str(soup)
    except Exception as e:
        print(f"        {Fore.YELLOW}⚠ Could not process HTML: {str(e)}{Style.RESET_ALL}")
        return content.body


def download_course_complete(course, save_location='./ESPRIT_Downloads', save_html_pages=False):
    """Download ALL files from a course"""
    print(f"\n{Fore.CYAN}{'=' * 70}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}Downloading: {course.name}{Style.RESET_ALL}")
    if save_html_pages:
        print(f"{Fore.CYAN}Mode: PDFs + HTML Pages{Style.RESET_ALL}")
    else:
        print(f"{Fore.CYAN}Mode: PDFs Only{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'=' * 70}{Style.RESET_ALL}\n")

    stats = {
        'api_attachments': 0,
        'embedded_pdfs': 0,
        'html_pages': 0,
    }

    def process_content(content, path, level=0, parent_has_single_child=False, parent_title=None):
        indent = "  " * level
        content_type = content.content_handler.id if content.content_handler else "unknown"

        print(f"{indent}{'📁' if content.has_children else '📄'} {content.title}")

        # Determine save path - skip creating folder if it's a single item
        if content.has_children:
            # Check if this folder will have only one child for optimization
            try:
                children = content.children()
                has_single_child = len(children) == 1
                child_path = os.path.join(path, content.title_safe)
            except:
                has_single_child = False
                child_path = os.path.join(path, content.title_safe)
        else:
            # For leaf nodes, don't create extra folder if parent only has this child
            if parent_has_single_child:
                child_path = path
            else:
                child_path = path

        # 1. API attachments
        try:
            attachments = content.attachments()
            if attachments:
                print(f"{indent}   {Fore.GREEN}API Attachments: {len(attachments)}{Style.RESET_ALL}")
                for att in attachments:
                    if download_pdf(content.client,
                                    f"/learn/api/public/v1/courses/{content.course.id}/contents/{content.id}/attachments/{att.id}/download",
                                    att.file_name, child_path):
                        stats['api_attachments'] += 1
        except:
            pass

        # 2. Embedded PDFs
        if content.body:
            pdf_links = extract_pdf_links_from_body(content.body)
            if pdf_links:
                print(f"{indent}   {Fore.CYAN}Embedded PDFs: {len(pdf_links)}{Style.RESET_ALL}")
                for pdf_info in pdf_links:
                    if download_pdf(content.client, pdf_info['url'], pdf_info['filename'], child_path):
                        stats['embedded_pdfs'] += 1

            # 3. Save HTML content
            if save_html_pages and content_type == "resource/x-bb-document":
                # Use parent folder name for better context if available
                save_name = parent_title if parent_title and content.title.lower() == "ultradocumentbody" else content.title
                if save_html_page(content, child_path, save_name):
                    stats['html_pages'] += 1

        # 4. Process children
        if content.has_children:
            try:
                children = content.children()
                has_single_child = len(children) == 1
                for child in children:
                    # Pass current content title as parent for better naming
                    process_content(child, child_path, level + 1, has_single_child, content.title)
            except:
                pass

    # Process all content
    base_path = os.path.join(save_location, course.name_safe)
    contents = course.contents()

    for content in contents:
        process_content(content, base_path)

    # Print stats
    print(f"\n{Fore.CYAN}{'=' * 70}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}Download Complete!{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'=' * 70}{Style.RESET_ALL}")
    print(f"📊 Results:")
    print(f"   {Fore.GREEN}✓ API Attachments: {stats['api_attachments']}{Style.RESET_ALL}")
    print(f"   {Fore.GREEN}✓ Embedded PDFs: {stats['embedded_pdfs']}{Style.RESET_ALL}")
    if save_html_pages:
        print(f"   {Fore.CYAN}✓ HTML Pages: {stats['html_pages']}{Style.RESET_ALL}")
    total = stats['api_attachments'] + stats['embedded_pdfs'] + stats['html_pages']
    print(f"   {Fore.CYAN}Total: {total} files{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'=' * 70}{Style.RESET_ALL}\n")


def main():
    print("=" * 70)
    print("ESPRIT Complete Course Downloader")
    print("=" * 70)
    print()

    print(f"{Fore.GREEN}✓ HTML pages will be saved (you can print them to PDF from your browser){Style.RESET_ALL}")
    print()

    # Load config
    config = {}
    if os.path.exists('config.json'):
        try:
            with open('config.json', 'r') as f:
                config = json.load(f)
            print("✓ Loaded credentials from config.json")
        except:
            pass

    username = config.get('username') or input("Username: ").strip()
    password = config.get('password') or getpass.getpass("Password: ")
    site = config.get('site', 'https://esprit.blackboard.com')

    print(f"\n{Fore.CYAN}User:{Style.RESET_ALL} {username}")
    print(f"\n{Fore.CYAN}Site:{Style.RESET_ALL} {site}")
    print("\nConnecting...")

    try:
        client = BlackBoardClient(
            username=username,
            password=password,
            site=site,
            save_location='./ESPRIT_Downloads',
            thread_count=8,
            use_manifest=True,
            backup_files=False
        )

        success, response = client.login()

        if not success:
            print(f"\n{Fore.RED}✗ Login failed!{Style.RESET_ALL}")
            sys.exit(1)

        print(f"{Fore.GREEN}✓ Login successful!{Style.RESET_ALL}")

        # Get courses
        courses = client.courses()
        print(f"\n{Fore.GREEN}✓ Found {len(courses)} courses:{Style.RESET_ALL}\n")

        for i, course in enumerate(courses, 1):
            print(f"  [{i:2d}] {course.name}")

        # Download options
        print(f"\n{Fore.YELLOW}{'=' * 70}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}Download Options:{Style.RESET_ALL}")
        print("  [1] PDFs only (embedded + attachments)")
        print("  [2] PDFs + HTML pages (complete backup)")
        print(f"{Fore.YELLOW}{'=' * 70}{Style.RESET_ALL}")

        download_option = input("\nChoice (default: 1): ").strip() or "1"
        save_html_pages = (download_option == "2")

        # Course selection
        print(f"\n{Fore.YELLOW}{'=' * 70}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}Course Selection:{Style.RESET_ALL}")
        print("  [a] Download ALL courses")
        print("  [#] Enter course number")
        print("  [q] Quit")
        print(f"{Fore.YELLOW}{'=' * 70}{Style.RESET_ALL}")

        choice = input("\nChoice: ").strip().lower()

        if choice == 'q':
            print("Goodbye!")
            sys.exit(0)
        elif choice == 'a':
            print(f"\n{Fore.CYAN}Downloading all courses...{Style.RESET_ALL}\n")
            for course in courses:
                download_course_complete(course, save_html_pages=save_html_pages)
        else:
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(courses):
                    download_course_complete(courses[idx], save_html_pages=save_html_pages)
                else:
                    print(f"{Fore.RED}✗ Invalid course number{Style.RESET_ALL}")
            except ValueError:
                print(f"{Fore.RED}✗ Invalid input{Style.RESET_ALL}")

        print(f"\n{Fore.GREEN}✅ All done! Files saved to: ./ESPRIT_Downloads/{Style.RESET_ALL}")

    except KeyboardInterrupt:
        print(f"\n\n{Fore.YELLOW}⚠ Interrupted{Style.RESET_ALL}")
        sys.exit(1)
    except Exception as e:
        print(f"\n{Fore.RED}✗ Error: {str(e)}{Style.RESET_ALL}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()