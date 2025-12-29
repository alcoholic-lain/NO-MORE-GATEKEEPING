"""
Blackboard Ultra Web Scraper for ESPRIT
Downloads all course content (PDFs, documents, and text pages)

Usage:
    python scraper.py
    python scraper.py --user YOUR_USERNAME --password YOUR_PASSWORD
    python scraper.py --browser firefox  # Use Firefox instead of Chrome
"""

import asyncio
import argparse
import os
import re
import sys
from pathlib import Path
from getpass import getpass
from urllib.parse import urljoin, urlparse

from playwright.async_api import async_playwright, Page, Browser, TimeoutError as PlaywrightTimeout
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.prompt import Prompt, Confirm
from rich.panel import Panel
from rich.table import Table

# Configuration
BLACKBOARD_URL = "https://esprit.blackboard.com"
DOWNLOAD_DIR = Path(__file__).parent / "downloads"
HEADLESS = True  # Must be True for PDF generation to work

console = Console()


def sanitize_filename(name: str) -> str:
    """Remove invalid characters from filename"""
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name[:100]


async def scroll_to_load_all(page: Page):
    """Scroll down to load all dynamically loaded content"""
    console.print("[dim]Scrolling to load all content...[/]")
    for _ in range(5):
        await page.mouse.wheel(0, 500)
        await asyncio.sleep(0.5)
    await asyncio.sleep(1)


async def login(page: Page, username: str, password: str) -> bool:
    """Login to Blackboard"""
    console.print("[bold blue]🔐 Logging in to Blackboard...[/]")
    
    try:
        await page.goto(f"{BLACKBOARD_URL}/ultra/course", timeout=60000)
        await page.wait_for_load_state("networkidle", timeout=30000)
        
        # Accept cookies if present
        try:
            agree_button = page.locator('#agree_button')
            if await agree_button.count() > 0 and await agree_button.is_visible():
                console.print("[dim]Accepting terms...[/]")
                await agree_button.click()
                await asyncio.sleep(1)
        except:
            pass
        
        # Wait for login form
        await page.wait_for_selector('input[name="user_id"]', timeout=15000)
        
        # Fill login form
        await page.fill('input[name="user_id"]', username)
        await page.fill('input[name="password"]', password)
        await page.click('#entry-login')
        
        await page.wait_for_load_state("networkidle", timeout=60000)
        await asyncio.sleep(3)
        
        if "ultra" in page.url:
            console.print("[bold green]✅ Login successful![/]")
            return True
        else:
            console.print("[bold red]❌ Login failed.[/]")
            return False
            
    except Exception as e:
        console.print(f"[bold red]❌ Login error: {e}[/]")
        return False


async def get_courses(page: Page) -> list[dict]:
    """Get all courses (with scrolling)"""
    console.print("[bold blue]📚 Fetching courses...[/]")
    
    try:
        await page.goto(f"{BLACKBOARD_URL}/ultra/course", timeout=60000)
        await page.wait_for_load_state("networkidle", timeout=30000)
        await asyncio.sleep(2)
        
        # Scroll to load all courses
        await scroll_to_load_all(page)
        
        courses = []
        course_links = page.locator('a[id^="course-link-"]')
        count = await course_links.count()
        
        for i in range(count):
            try:
                elem = course_links.nth(i)
                link_id = await elem.get_attribute("id")
                text = await elem.inner_text()
                
                if text.strip():
                    courses.append({
                        "name": text.strip(),
                        "selector": f'#{link_id}',
                        "id": link_id.replace("course-link-", "") if link_id else None
                    })
            except:
                continue
        
        console.print(f"[green]Found {len(courses)} courses[/]")
        return courses
        
    except Exception as e:
        console.print(f"[yellow]Warning: {e}[/]")
        return []


async def get_course_contents(page: Page) -> list[dict]:
    """Get TOP-LEVEL content items from course page (not inside modules)"""
    await asyncio.sleep(2)
    
    # Scroll to load all content
    await scroll_to_load_all(page)
    
    contents = []
    
    # Get modules/chapters FIRST (these are the expandable containers)
    modules = page.locator('button[id^="learning-module-title-"]')
    module_count = await modules.count()
    
    for i in range(module_count):
        try:
            module = modules.nth(i)
            module_id = await module.get_attribute("id")
            controls_id = await module.get_attribute("aria-controls")
            text = await module.inner_text()
            
            if text.strip():
                contents.append({
                    "name": text.strip(),
                    "type": "module",
                    "id": module_id,
                    "controls": controls_id,  # The container ID for nested items
                    "selector": f'#{module_id}'
                })
        except:
            continue
    
    # Get standalone items that are NOT inside any module
    # These are direct children of the course outline, not nested in module containers
    # We check if item is NOT a descendant of any learning-module-contents-* container
    all_items = page.locator('a[href*="/outline/edit/"]')
    item_count = await all_items.count()
    
    for i in range(item_count):
        try:
            item = all_items.nth(i)
            text = await item.inner_text()
            href = await item.get_attribute("href")
            
            # Check if this item is inside a module container
            # by evaluating if it has a parent with learning-module-contents
            is_nested = await item.evaluate(
                "el => !!el.closest('[id^=\"learning-module-contents-\"]')"
            )
            
            if text.strip() and not is_nested:
                contents.append({
                    "name": text.strip(),
                    "type": "item",
                    "href": href,
                    "index": i
                })
        except:
            continue
    
    return contents


async def expand_module(page: Page, module: dict) -> tuple[list[dict], list[dict]]:
    """Expand a module/folder and get its contents - returns (items, subfolders)"""
    
    try:
        # Get fresh reference to the button
        btn = page.locator(module['selector'])
        
        # Check if already expanded
        is_expanded = await btn.get_attribute('aria-expanded')
        
        # Scroll to element first
        try:
            await btn.scroll_into_view_if_needed(timeout=5000)
            await asyncio.sleep(0.3)
        except:
            pass
        
        # Click to expand if not already expanded
        if is_expanded != 'true':
            try:
                await btn.click(timeout=10000)
                await asyncio.sleep(2)
            except Exception as e:
                # If click fails, try forcing it
                await page.evaluate(f"document.querySelector('{module['selector']}')?.click()")
                await asyncio.sleep(2)
        
        # Get the container ID
        controls_id = module.get('controls')
        if not controls_id:
            controls_id = await btn.get_attribute('aria-controls')
        
        if not controls_id:
            return [], []
        
        container = page.locator(f'#{controls_id}')
        
        items = []
        subfolders = []
        
        # Look for BOTH learning-module-title AND folder-title buttons as subfolders
        folder_selectors = [
            'button[id^="folder-title-"]',           # Subfolders like LDD, LMD
            'button[id^="learning-module-title-"]'   # Nested modules
        ]
        
        for selector in folder_selectors:
            sub_folders = container.locator(selector)
            sub_count = await sub_folders.count()
            
            for i in range(sub_count):
                try:
                    sub = sub_folders.nth(i)
                    sub_id = await sub.get_attribute("id")
                    sub_controls = await sub.get_attribute("aria-controls")
                    text = await sub.inner_text()
                    
                    if text.strip():
                        subfolders.append({
                            "name": text.strip(),
                            "type": "folder",
                            "id": sub_id,
                            "controls": sub_controls,
                            "selector": f'#{sub_id}'
                        })
                except:
                    continue
        
        # Look for content items using the correct selector
        content_items = container.locator('a.ax-focusable-title, a[href*="/outline/"], a[href*="/document/"], a[href*="/assessment/"]')
        item_count = await content_items.count()
        
        for i in range(item_count):
            try:
                item = content_items.nth(i)
                text = await item.inner_text()
                href = await item.get_attribute("href")
                
                if text.strip() and href:
                    items.append({
                        "name": text.strip(),
                        "type": "item",
                        "href": href,
                        "index": i
                    })
            except:
                continue
        
        return items, subfolders
        
    except Exception as e:
        return [], []


async def download_module_recursive(page: Page, module: dict, save_dir: Path, depth: int = 0, course_url: str = None):
    """Recursively download all content from a module and its subfolders"""
    indent = "  " * depth
    
    # Save current URL if not provided
    if course_url is None:
        course_url = page.url
    
    try:
        # Expand the module and get contents
        items, subfolders = await expand_module(page, module)
        
        # Download all direct items first
        for item in items:
            console.print(f"{indent}📄 {item['name']}")
            try:
                await scrape_content_item(page, item, save_dir)
            except:
                continue
        
        # Process each subfolder - go back to course page after each
        for i, folder in enumerate(subfolders):
            console.print(f"{indent}[bold]📁 {folder['name']}[/]")
            subdir = save_dir / sanitize_filename(folder['name'])
            subdir.mkdir(parents=True, exist_ok=True)
            
            try:
                await asyncio.wait_for(
                    download_module_recursive(page, folder, subdir, depth + 1, course_url),
                    timeout=120
                )
            except asyncio.TimeoutError:
                console.print(f"{indent}[yellow]⚠ Timeout, skipping[/]")
            except:
                pass
            
            # After processing a subfolder, go back to course page and re-expand parent
            if i < len(subfolders) - 1:  # Don't refresh after last folder
                await page.goto(course_url, timeout=30000)
                await asyncio.sleep(2)
                # Re-expand the parent module to access next subfolder
                await expand_module(page, module)
                
    except:
        pass


async def download_attachments(page: Page, save_dir: Path) -> int:
    """Download all attachments on the current page"""
    downloaded = 0
    
    # Find all "Plus d'options" buttons for attachments
    option_buttons = page.locator('button[aria-label*="Plus d\'options"]')
    count = await option_buttons.count()
    
    for i in range(count):
        try:
            btn = option_buttons.nth(i)
            await btn.click()
            await asyncio.sleep(0.5)
            
            # Find download option
            download_btn = page.locator('[role="menuitem"]:has-text("Télécharger"), li:has-text("Télécharger")')
            
            if await download_btn.count() > 0:
                async with page.expect_download(timeout=30000) as download_info:
                    await download_btn.first.click()
                download = await download_info.value
                
                filename = download.suggested_filename or f"file_{i+1}.pdf"
                filepath = save_dir / sanitize_filename(filename)
                await download.save_as(str(filepath))
                
                console.print(f"[green]  ✓ {filename}[/]")
                downloaded += 1
            else:
                await page.keyboard.press("Escape")
            
            await asyncio.sleep(0.5)
            
        except Exception as e:
            await page.keyboard.press("Escape")
            continue
    
    return downloaded


async def download_pdf_files(page: Page, save_dir: Path) -> int:
    """Download only PDF/document files (not images)"""
    downloaded = 0
    
    # Find all "Plus d'options" buttons for attachments
    option_buttons = page.locator('button[aria-label*="Plus d\'options"]')
    count = await option_buttons.count()
    
    for i in range(count):
        try:
            btn = option_buttons.nth(i)
            
            # Get the filename from the aria-label to check file type
            aria_label = await btn.get_attribute("aria-label") or ""
            
            # Skip images silently
            if any(ext in aria_label.lower() for ext in ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp']):
                continue
            
            await btn.click()
            await asyncio.sleep(0.5)
            
            # Find download option
            download_btn = page.locator('[role="menuitem"]:has-text("Télécharger"), li:has-text("Télécharger")')
            
            if await download_btn.count() > 0:
                try:
                    async with page.expect_download(timeout=30000) as download_info:
                        await download_btn.first.click()
                    download = await download_info.value
                    
                    filename = download.suggested_filename or f"file_{i+1}.pdf"
                    
                    # Skip images silently
                    if any(ext in filename.lower() for ext in ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp']):
                        await download.cancel()
                        continue
                    
                    filepath = save_dir / sanitize_filename(filename)
                    await download.save_as(str(filepath))
                    
                    console.print(f"[green]  ✓ {filename}[/]")
                    downloaded += 1
                except:
                    pass  # Continue silently on download error
            else:
                await page.keyboard.press("Escape")
            
            await asyncio.sleep(0.5)
            
        except Exception as e:
            await page.keyboard.press("Escape")
            continue
    
    return downloaded


async def print_page_as_pdf(page: Page, item_name: str, save_dir: Path) -> bool:
    """Save page content as PDF using Playwright's built-in PDF generation"""
    try:
        filename = f"{sanitize_filename(item_name)}.pdf"
        filepath = save_dir / filename
        
        # Skip if already exists
        if filepath.exists():
            console.print(f"[dim]  (PDF exists, skipping)[/]")
            return False
        
        # Use Playwright's PDF generation (works best in headless mode)
        # For non-headless, we can use the print-to-pdf approach
        await page.pdf(
            path=str(filepath),
            format="A4",
            print_background=True,
            margin={"top": "1cm", "bottom": "1cm", "left": "1cm", "right": "1cm"}
        )
        
        console.print(f"[green]  ✓ {filename}[/]")
        return True
        
    except Exception as e:
        # page.pdf() only works in headless Chromium - fallback message
        console.print(f"[yellow]  ⚠ PDF generation requires headless mode: {e}[/]")
        return False


async def scrape_content_item(page: Page, item: dict, save_dir: Path) -> bool:
    """Open and scrape a content item - downloads PDFs and prints page"""
    console.print(f"[cyan]📄 {item['name']}[/]")
    
    try:
        # Navigate to item
        if item.get("href"):
            url = item["href"]
            if not url.startswith("http"):
                url = urljoin(BLACKBOARD_URL, url)
            
            if url.startswith("javascript:"):
                console.print("[yellow]  ⚠ Skipping (JS link)[/]")
                return False
            
            await page.goto(url, timeout=60000)
            await page.wait_for_load_state("networkidle", timeout=30000)
            await asyncio.sleep(2)
        
        # Download PDF/document attachments (not images)
        pdf_count = await download_pdf_files(page, save_dir)
        
        # Also print the page content as PDF
        printed = await print_page_as_pdf(page, item['name'], save_dir)
        
        if pdf_count == 0 and not printed:
            console.print("[dim]  No downloadable content[/]")
        
        # Try to close panel - with short timeout, don't fail if it doesn't work
        try:
            close_btn = page.locator('button[aria-label="Fermer"]')
            if await close_btn.count() > 0:
                # Check if visible first
                if await close_btn.first.is_visible():
                    await close_btn.first.click(timeout=5000)
                    await asyncio.sleep(0.5)
        except:
            # If close fails, try pressing Escape or just continue
            await page.keyboard.press("Escape")
        
        return pdf_count > 0 or printed
        
    except Exception as e:
        console.print(f"[red]  Error: {e}[/]")
        return False


async def interactive_mode(page: Page, save_dir: Path):
    """Interactive mode - navigate manually, download on command"""
    console.print(Panel.fit(
        "[bold cyan]🎯 Interactive Mode[/]\n\n"
        "Navigate in the browser, then:\n"
        "  [Enter] - Download files (PDF, docx, sql...)\n"
        "  [p]     - Print page as PDF\n"
        "  [a]     - All (files + print)\n"
        "  [quit]  - Exit",
        title="Instructions"
    ))
    
    save_dir.mkdir(parents=True, exist_ok=True)
    
    while True:
        try:
            action = Prompt.ask("\n[bold]Command (Enter/p/a/quit)[/]")
            
            if action.lower() == 'quit':
                break
            
            title = await page.title()
            page_name = sanitize_filename(title) if title else "page"
            
            if action.lower() == 'p':
                # Print only
                printed = await print_page_as_pdf(page, page_name, save_dir)
                if printed:
                    console.print(f"[green]✓ Printed page as PDF[/]")
                else:
                    console.print("[yellow]No print option found[/]")
            elif action.lower() == 'a':
                # All - files + print
                pdf_count = await download_pdf_files(page, save_dir)
                printed = await print_page_as_pdf(page, page_name, save_dir)
                total = pdf_count + (1 if printed else 0)
                console.print(f"[green]✓ Saved {total} file(s)[/]")
            else:
                # Default (Enter) - files only
                pdf_count = await download_pdf_files(page, save_dir)
                if pdf_count > 0:
                    console.print(f"[green]✓ Downloaded {pdf_count} file(s)[/]")
                else:
                    console.print("[yellow]No files found[/]")
            
        except KeyboardInterrupt:
            break
        except Exception as e:
            console.print(f"[red]Error: {e}[/]")
    
    console.print(f"[green]Files saved to: {save_dir}[/]")


async def navigate_and_scrape(page: Page):
    """Main navigation loop with hierarchical menu"""
    
    # Get courses
    courses = await get_courses(page)
    
    if not courses:
        console.print("[yellow]No courses found[/]")
        return
    
    while True:
        # Display courses
        console.print("\n[bold]Available Courses:[/]")
        table = Table()
        table.add_column("#", style="cyan")
        table.add_column("Course Name", style="white")
        
        for i, course in enumerate(courses, 1):
            table.add_row(str(i), course["name"])
        
        console.print(table)
        console.print("\n  [cyan]1-N[/] Select course | [cyan]i[/] Interactive | [cyan]q[/] Quit")
        
        choice = Prompt.ask("Choice")
        
        if choice.lower() == 'q':
            break
        elif choice.lower() == 'i':
            save_dir = DOWNLOAD_DIR / "interactive"
            await interactive_mode(page, save_dir)
            continue
        
        try:
            idx = int(choice) - 1
            if idx < 0 or idx >= len(courses):
                console.print("[red]Invalid choice[/]")
                continue
        except ValueError:
            console.print("[red]Invalid input[/]")
            continue
        
        selected_course = courses[idx]
        
        # Navigate to course
        console.print(f"\n[bold blue]Opening: {selected_course['name']}[/]")
        
        await page.goto(f"{BLACKBOARD_URL}/ultra/course", timeout=60000)
        await page.wait_for_load_state("networkidle", timeout=30000)
        await asyncio.sleep(2)
        await scroll_to_load_all(page)
        
        # Click on course
        await page.click(selected_course['selector'])
        await page.wait_for_load_state("networkidle", timeout=30000)
        await asyncio.sleep(3)
        
        # Course content loop
        await browse_course_contents(page, selected_course['name'])


async def browse_course_contents(page: Page, course_name: str):
    """Browse contents of a course - auto-downloads when selecting modules"""
    course_dir = DOWNLOAD_DIR / sanitize_filename(course_name)
    course_dir.mkdir(parents=True, exist_ok=True)
    
    while True:
        # Get current contents
        contents = await get_course_contents(page)
        
        if not contents:
            console.print("[yellow]No content found[/]")
            break
        
        # Display contents
        console.print(f"\n[bold]Contents of: {course_name}[/]")
        table = Table()
        table.add_column("#", style="cyan")
        table.add_column("Name", style="white")
        table.add_column("Type", style="dim")
        
        for i, item in enumerate(contents, 1):
            type_str = "📁 Chapter" if item["type"] == "module" else "📄 Item"
            table.add_row(str(i), item["name"][:60], type_str)
        
        console.print(table)
        console.print("\n  [cyan]1-N[/] Auto-download | [cyan]all[/] Download all | [cyan]b[/] Back | [cyan]i[/] Interactive")
        
        choice = Prompt.ask("Choice")
        
        if choice.lower() == 'b':
            break
        elif choice.lower() == 'i':
            await interactive_mode(page, course_dir)
            continue
        elif choice.lower() == 'all':
            # Download EVERYTHING in order - fully automatic
            console.print(f"\n[bold blue]🚀 Auto-downloading entire course...[/]")
            
            total_items = 0
            for i, item in enumerate(contents, 1):
                if item["type"] == "item":
                    console.print(f"\n[{i}/{len(contents)}] 📄 {item['name']}")
                    await scrape_content_item(page, item, course_dir)
                    total_items += 1
                elif item["type"] == "module":
                    console.print(f"\n[{i}/{len(contents)}] 📁 {item['name']}")
                    subdir = course_dir / sanitize_filename(item['name'])
                    subdir.mkdir(parents=True, exist_ok=True)
                    await download_module_recursive(page, item, subdir)
                    total_items += 1
            
            console.print(f"\n[bold green]✅ Complete! {total_items} chapters/items downloaded[/]")
            console.print(f"[bold green]📁 Saved to: {course_dir}[/]")
            break  # Exit the course menu when done
        
        try:
            idx = int(choice) - 1
            if idx < 0 or idx >= len(contents):
                console.print("[red]Invalid choice[/]")
                continue
        except ValueError:
            console.print("[red]Invalid input[/]")
            continue
        
        selected = contents[idx]
        
        if selected["type"] == "module":
            # AUTO-DOWNLOAD: Recursively download all items including nested folders
            console.print(f"\n[bold blue]🚀 Auto-downloading: {selected['name']} (including nested folders)[/]")
            subdir = course_dir / sanitize_filename(selected['name'])
            subdir.mkdir(parents=True, exist_ok=True)
            
            await download_module_recursive(page, selected, subdir)
            
            console.print(f"\n[bold green]✅ Done! Files saved to: {subdir}[/]")
        else:
            # Single item - download it directly
            await scrape_content_item(page, selected, course_dir)


async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Blackboard Scraper for ESPRIT")
    parser.add_argument("--user", "-u", help="Username")
    parser.add_argument("--password", "-p", help="Password")
    parser.add_argument("--browser", "-b", default="chromium", 
                        choices=["chromium", "firefox", "webkit", "opera", "edge", "chrome"],
                        help="Browser to use (default: chromium)")
    args = parser.parse_args()
    
    console.print(Panel.fit(
        "[bold cyan]🎓 Blackboard Scraper for ESPRIT[/]",
        title="Welcome"
    ))
    
    # Get credentials
    username = args.user or Prompt.ask("\n[bold]Username[/]")
    password = args.password or getpass("Password: ")
    
    if not username or not password:
        console.print("[red]Credentials required![/]")
        return
    
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    
    async with async_playwright() as p:
        console.print(f"\n[bold blue]🌐 Launching {args.browser}...[/]")
        
        # Select browser
        if args.browser == "firefox":
            browser = await p.firefox.launch(headless=HEADLESS)
        elif args.browser == "webkit":
            browser = await p.webkit.launch(headless=HEADLESS)
        elif args.browser == "opera":
            # Opera GX is Chromium-based - find common install paths
            opera_paths = [
                os.path.expandvars(r"%LOCALAPPDATA%\Programs\Opera GX\opera.exe"),
                os.path.expandvars(r"%PROGRAMFILES%\Opera GX\opera.exe"),
                os.path.expandvars(r"%PROGRAMFILES(X86)%\Opera GX\opera.exe"),
                os.path.expandvars(r"%LOCALAPPDATA%\Programs\Opera\opera.exe"),
            ]
            opera_exe = None
            for path in opera_paths:
                if os.path.exists(path):
                    opera_exe = path
                    break
            
            if opera_exe:
                console.print(f"[dim]Using: {opera_exe}[/]")
                browser = await p.chromium.launch(
                    headless=HEADLESS,
                    executable_path=opera_exe,
                    args=["--disable-blink-features=AutomationControlled"]
                )
            else:
                console.print("[yellow]Opera GX not found, using Chromium[/]")
                browser = await p.chromium.launch(headless=HEADLESS)
        elif args.browser == "edge":
            browser = await p.chromium.launch(headless=HEADLESS, channel="msedge")
        elif args.browser == "chrome":
            browser = await p.chromium.launch(headless=HEADLESS, channel="chrome")
        else:
            browser = await p.chromium.launch(
                headless=HEADLESS,
                args=["--disable-blink-features=AutomationControlled"]
            )
        
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            accept_downloads=True
        )
        page = await context.new_page()
        
        try:
            if not await login(page, username, password):
                console.print("[yellow]Browser stays open for 60s...[/]")
                await asyncio.sleep(60)
                return
            
            await navigate_and_scrape(page)
            
        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted[/]")
        except Exception as e:
            console.print(f"[red]Error: {e}[/]")
            import traceback
            traceback.print_exc()
        finally:
            await browser.close()
    
    console.print(f"\n[bold green]📁 Downloads: {DOWNLOAD_DIR.absolute()}[/]")


if __name__ == "__main__":
    asyncio.run(main())
