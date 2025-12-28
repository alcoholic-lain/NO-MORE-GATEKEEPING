#!/usr/bin/env python3
"""
ESPRIT Blackboard Debugger - Shows course structure and downloads with detailed logging
"""

from blackboard import BlackBoardClient, BlackBoardCourse, BlackBoardContent
import json
import sys
import os
import getpass
from colorama import Fore, Style, init

init()


def print_content_tree(content, level=0, parent_path=""):
    """
    Recursively print the content tree structure
    """
    indent = "  " * level
    icon = "📁" if content.has_children else "📄"

    # Get content type
    content_type = content.content_handler.id if content.content_handler else "unknown"

    # Build current path
    current_path = f"{parent_path}/{content.title_safe}" if parent_path else content.title_safe

    # Print content info
    print(f"{indent}{icon} {content.title}")
    print(f"{indent}   └─ Type: {Fore.CYAN}{content_type}{Style.RESET_ALL}")
    print(f"{indent}   └─ ID: {content.id}")
    print(f"{indent}   └─ Has Children: {content.has_children}")

    # Check for attachments
    if content_type in ("resource/x-bb-file", "resource/x-bb-assignment"):
        try:
            attachments = content.attachments()
            if attachments:
                print(f"{indent}   └─ {Fore.GREEN}✓ Attachments: {len(attachments)}{Style.RESET_ALL}")
                for att in attachments:
                    print(f"{indent}      └─ 📎 {att.file_name}")
            else:
                print(f"{indent}   └─ {Fore.YELLOW}⚠ No attachments found{Style.RESET_ALL}")
        except Exception as e:
            print(f"{indent}   └─ {Fore.RED}✗ Error getting attachments: {str(e)}{Style.RESET_ALL}")
    else:
        print(f"{indent}   └─ {Fore.LIGHTBLACK_EX}(No attachments for this type){Style.RESET_ALL}")

    # Recursively process children
    if content.has_children:
        children = content.children()
        print(f"{indent}   └─ Children: {len(children)}")
        for child in children:
            print()
            print_content_tree(child, level + 1, current_path)


def download_with_logging(course, save_location='./ESPRIT_Downloads'):
    """
    Download course content with detailed logging
    """
    print(f"\n{Fore.CYAN}{'=' * 70}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}Starting download: {course.name}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'=' * 70}{Style.RESET_ALL}\n")

    # Get course contents
    contents = course.contents()
    print(f"📚 Found {len(contents)} top-level content items\n")

    # Statistics
    stats = {
        'folders': 0,
        'files': 0,
        'documents': 0,
        'assignments': 0,
        'other': 0,
        'downloaded': 0,
        'skipped': 0,
        'errors': 0
    }

    def process_content(content, path, level=0):
        """Recursively process content and download attachments"""
        indent = "  " * level
        content_type = content.content_handler.id if content.content_handler else "unknown"

        # Update stats
        if content.has_children:
            stats['folders'] += 1
        elif content_type == "resource/x-bb-file":
            stats['files'] += 1
        elif content_type == "resource/x-bb-document":
            stats['documents'] += 1
        elif content_type == "resource/x-bb-assignment":
            stats['assignments'] += 1
        else:
            stats['other'] += 1

        print(f"{indent}{'📁' if content.has_children else '📄'} {content.title}")
        print(f"{indent}   Type: {content_type}")

        # Try to get attachments if it's a file type
        if content_type in ("resource/x-bb-file", "resource/x-bb-assignment"):
            try:
                attachments = content.attachments()
                if attachments:
                    print(f"{indent}   {Fore.GREEN}✓ Found {len(attachments)} attachment(s){Style.RESET_ALL}")
                    for att in attachments:
                        try:
                            print(f"{indent}      Downloading: {att.file_name}")
                            att.download(path)
                            stats['downloaded'] += 1
                            print(f"{indent}      {Fore.GREEN}✓ Downloaded{Style.RESET_ALL}")
                        except Exception as e:
                            stats['errors'] += 1
                            print(f"{indent}      {Fore.RED}✗ Error: {str(e)}{Style.RESET_ALL}")
                else:
                    stats['skipped'] += 1
                    print(f"{indent}   {Fore.YELLOW}⚠ No attachments{Style.RESET_ALL}")
            except Exception as e:
                stats['errors'] += 1
                print(f"{indent}   {Fore.RED}✗ Error getting attachments: {str(e)}{Style.RESET_ALL}")
        else:
            stats['skipped'] += 1
            print(f"{indent}   {Fore.LIGHTBLACK_EX}(Skipped - not a file type){Style.RESET_ALL}")

        # Process children
        if content.has_children:
            children = content.children()
            child_path = os.path.join(path, content.title_safe)
            print(f"{indent}   Processing {len(children)} children...")
            for child in children:
                process_content(child, child_path, level + 1)

    # Process all top-level contents
    base_path = os.path.join(save_location, course.name_safe)
    for content in contents:
        process_content(content, base_path)
        print()

    # Print statistics
    print(f"\n{Fore.CYAN}{'=' * 70}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}Download Statistics{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'=' * 70}{Style.RESET_ALL}")
    print(f"📊 Content Types Found:")
    print(f"   Folders: {stats['folders']}")
    print(f"   Files: {stats['files']}")
    print(f"   Documents: {stats['documents']}")
    print(f"   Assignments: {stats['assignments']}")
    print(f"   Other: {stats['other']}")
    print(f"\n📥 Download Results:")
    print(f"   {Fore.GREEN}✓ Downloaded: {stats['downloaded']}{Style.RESET_ALL}")
    print(f"   {Fore.YELLOW}⚠ Skipped: {stats['skipped']}{Style.RESET_ALL}")
    print(f"   {Fore.RED}✗ Errors: {stats['errors']}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'=' * 70}{Style.RESET_ALL}\n")


def main():
    print("=" * 70)
    print("ESPRIT Blackboard Course Debugger & Downloader")
    print("=" * 70)
    print()

    # Try to load config.json if it exists
    config = {}
    if os.path.exists('config.json'):
        try:
            with open('config.json', 'r') as f:
                config = json.load(f)
            print("✓ Loaded credentials from config.json")
        except:
            print("⚠ Could not read config.json, will prompt for credentials")

    # Get credentials
    username = config.get('username') or input("Username: ").strip()
    password = config.get('password') or getpass.getpass("Password: ")
    site = config.get('site', 'https://esprit.blackboard.com')

    print(f"\n{Fore.CYAN}User:{Style.RESET_ALL} {username}")
    print(f"{Fore.CYAN}Site:{Style.RESET_ALL} {site}")
    print("\nConnecting...")

    try:
        # Create client
        client = BlackBoardClient(
            username=username,
            password=password,
            site=site,
            save_location='./ESPRIT_Downloads',
            thread_count=8,
            use_manifest=True,
            backup_files=False
        )

        # Login
        success, response = client.login()

        if not success:
            print(f"\n{Fore.RED}✗ Login failed!{Style.RESET_ALL}")
            print(f"Status Code: {response.status_code}")
            sys.exit(1)

        print(f"{Fore.GREEN}✓ Login successful!{Style.RESET_ALL}")
        print(f"User ID: {client.user_id}")
        print(f"API Version: {client.api_version}")

        # Fetch courses
        print("\nFetching courses...")
        courses = client.courses()

        if not courses:
            print(f"{Fore.RED}✗ No courses found!{Style.RESET_ALL}")
            sys.exit(1)

        print(f"\n{Fore.GREEN}✓ Found {len(courses)} courses:{Style.RESET_ALL}\n")

        for i, course in enumerate(courses, 1):
            print(f"  [{i:2d}] {course.name}")

        # Ask user what to do
        print("\n" + "=" * 70)
        print("Options:")
        print("  [t] Show content TREE for a course")
        print("  [d] DOWNLOAD a course with detailed logging")
        print("  [a] Download ALL courses")
        print("  [q] Quit")
        print("=" * 70)

        action = input("\nYour choice: ").strip().lower()

        if action == 'q':
            print("Goodbye!")
            sys.exit(0)

        elif action == 't':
            # Show tree
            course_num = input("Enter course number: ").strip()
            try:
                idx = int(course_num) - 1
                if 0 <= idx < len(courses):
                    course = courses[idx]
                    print(f"\n{Fore.CYAN}{'=' * 70}{Style.RESET_ALL}")
                    print(f"{Fore.CYAN}Content Tree: {course.name}{Style.RESET_ALL}")
                    print(f"{Fore.CYAN}{'=' * 70}{Style.RESET_ALL}\n")

                    contents = course.contents()
                    for content in contents:
                        print_content_tree(content)
                        print()
                else:
                    print(f"{Fore.RED}✗ Invalid course number!{Style.RESET_ALL}")
            except ValueError:
                print(f"{Fore.RED}✗ Invalid input!{Style.RESET_ALL}")

        elif action == 'd':
            # Download with logging
            course_num = input("Enter course number: ").strip()
            try:
                idx = int(course_num) - 1
                if 0 <= idx < len(courses):
                    course = courses[idx]
                    download_with_logging(course)
                    print(f"\n{Fore.GREEN}✅ Complete!{Style.RESET_ALL}")
                else:
                    print(f"{Fore.RED}✗ Invalid course number!{Style.RESET_ALL}")
            except ValueError:
                print(f"{Fore.RED}✗ Invalid input!{Style.RESET_ALL}")

        elif action == 'a':
            # Download all
            print(f"\n{Fore.CYAN}Downloading all {len(courses)} courses...{Style.RESET_ALL}\n")
            for course in courses:
                download_with_logging(course)
            print(f"\n{Fore.GREEN}✅ All courses downloaded!{Style.RESET_ALL}")

        else:
            print(f"{Fore.RED}✗ Invalid choice!{Style.RESET_ALL}")

    except KeyboardInterrupt:
        print(f"\n\n{Fore.YELLOW}⚠ Interrupted by user{Style.RESET_ALL}")
        sys.exit(1)
    except Exception as e:
        print(f"\n{Fore.RED}✗ Error: {str(e)}{Style.RESET_ALL}")
        print("\nFull error details:")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()