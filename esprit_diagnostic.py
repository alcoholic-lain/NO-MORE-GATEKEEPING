#!/usr/bin/env python3
"""
ESPRIT Diagnostic Script - Inspect ultraDocumentBody content to find PDFs
"""

from blackboard import BlackBoardClient
import json
import sys
import os
import getpass
from colorama import Fore, Style, init

init()


def inspect_content(content, level=0):
    """
    Deeply inspect content to see what's actually in it
    """
    indent = "  " * level
    content_type = content.content_handler.id if content.content_handler else "unknown"
    
    print(f"{indent}📄 {content.title}")
    print(f"{indent}   Type: {content_type}")
    print(f"{indent}   ID: {content.id}")
    
    # Check for body/description (HTML content)
    if content.body:
        print(f"{indent}   {Fore.YELLOW}⚠ Has body content (HTML):{Style.RESET_ALL}")
        # Look for links to PDFs in the HTML
        import re
        pdf_links = re.findall(r'href=["\']([^"\']*\.pdf[^"\']*)["\']', str(content.body), re.IGNORECASE)
        if pdf_links:
            print(f"{indent}      {Fore.GREEN}✓ Found PDF links in HTML:{Style.RESET_ALL}")
            for link in pdf_links:
                print(f"{indent}         - {link}")
        else:
            print(f"{indent}      No PDF links found in body")
    
    # Check content handler details
    if content.content_handler:
        handler = content.content_handler
        print(f"{indent}   Content Handler:")
        print(f"{indent}      ID: {handler.id}")
        if handler.url:
            print(f"{indent}      URL: {handler.url}")
        if handler.file and handler.file.file_name:
            print(f"{indent}      {Fore.GREEN}✓ File: {handler.file.file_name}{Style.RESET_ALL}")
    
    # Check for attachments (API endpoint)
    print(f"{indent}   {Fore.CYAN}Checking attachments endpoint...{Style.RESET_ALL}")
    try:
        attachments = content.attachments()
        if attachments:
            print(f"{indent}   {Fore.GREEN}✓ Found {len(attachments)} attachments via API:{Style.RESET_ALL}")
            for att in attachments:
                print(f"{indent}      - {att.file_name} ({att.mime_type})")
        else:
            print(f"{indent}   No attachments via API")
    except Exception as e:
        print(f"{indent}   {Fore.RED}Error checking attachments: {str(e)}{Style.RESET_ALL}")
    
    # Recursively check children
    if content.has_children:
        children = content.children()
        print(f"{indent}   Processing {len(children)} children...")
        for child in children:
            inspect_content(child, level + 1)
    
    print()


def main():
    print("=" * 70)
    print("ESPRIT Blackboard Diagnostic - PDF Detection")
    print("=" * 70)
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

    print(f"\nUser: {username}")
    print(f"Site: {site}")
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
            print(f"\n✗ Login failed! Status: {response.status_code}")
            sys.exit(1)

        print("✓ Login successful!")
        print(f"User ID: {client.user_id}")
        print(f"API Version: {client.api_version}")

        # Get courses
        print("\nFetching courses...")
        courses = client.courses()

        if not courses:
            print("✗ No courses found!")
            sys.exit(1)

        print(f"\n✓ Found {len(courses)} courses:\n")
        for i, course in enumerate(courses, 1):
            print(f"  [{i:2d}] {course.name}")

        # Select course
        course_num = input("\nEnter course number to inspect: ").strip()
        try:
            idx = int(course_num) - 1
            if 0 <= idx < len(courses):
                course = courses[idx]
                
                print(f"\n{Fore.CYAN}{'=' * 70}{Style.RESET_ALL}")
                print(f"{Fore.CYAN}Inspecting: {course.name}{Style.RESET_ALL}")
                print(f"{Fore.CYAN}{'=' * 70}{Style.RESET_ALL}\n")

                # Get and inspect all content
                contents = course.contents()
                print(f"Found {len(contents)} top-level content items\n")
                
                # Focus on Chapter 2 specifically
                for content in contents:
                    if "Chapitre 2" in content.title or "chapitre 2" in content.title.lower():
                        print(f"\n{Fore.YELLOW}{'=' * 70}{Style.RESET_ALL}")
                        print(f"{Fore.YELLOW}DEEP INSPECTION: {content.title}{Style.RESET_ALL}")
                        print(f"{Fore.YELLOW}{'=' * 70}{Style.RESET_ALL}\n")
                        inspect_content(content)
                        break
                
            else:
                print("✗ Invalid course number!")
        except ValueError:
            print("✗ Invalid input!")

    except KeyboardInterrupt:
        print("\n\n⚠ Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
