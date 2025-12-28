#!/usr/bin/env python3
"""
ESPRIT Deep Fetch - Directly query the API for folder contents
"""

from blackboard import BlackBoardClient, BlackBoardEndPoints
import json
import sys
import os
import getpass
from colorama import Fore, Style, init

init()


def deep_fetch_folder(client, course_id, content_id, title, level=0):
    """
    Directly fetch folder contents from the API
    """
    indent = "  " * level
    print(f"{indent}📁 {title} (ID: {content_id})")
    
    # Try multiple API endpoints to find content
    endpoints_to_try = [
        f"/learn/api/public/v1/courses/{course_id}/contents/{content_id}/children",
        f"/learn/api/public/v1/courses/{course_id}/contents/{content_id}/attachments",
        f"/learn/api/public/v1/courses/{course_id}/contents/{content_id}",
    ]
    
    for endpoint in endpoints_to_try:
        print(f"{indent}   Trying: {endpoint}")
        try:
            response = client.send_get_request(endpoint, silent_on_error=True)
            if response and response.status_code == 200:
                data = response.json()
                print(f"{indent}   {Fore.GREEN}✓ Response received!{Style.RESET_ALL}")
                print(f"{indent}   {Fore.CYAN}Raw JSON:{Style.RESET_ALL}")
                print(json.dumps(data, indent=2)[:1000])  # Print first 1000 chars
                
                # Look for files/attachments in the response
                if "results" in data:
                    for item in data["results"]:
                        item_type = item.get("contentHandler", {}).get("id", "unknown")
                        item_title = item.get("title", item.get("fileName", "unknown"))
                        print(f"{indent}      - {item_title} (type: {item_type})")
                        
                        # If it's a file, show details
                        if "fileName" in item:
                            print(f"{indent}         {Fore.GREEN}✓ FILE: {item.get('fileName')}{Style.RESET_ALL}")
                            print(f"{indent}            MIME: {item.get('mimeType', 'unknown')}")
                            print(f"{indent}            ID: {item.get('id', 'unknown')}")
            else:
                print(f"{indent}   Status: {response.status_code if response else 'None'}")
        except Exception as e:
            print(f"{indent}   Error: {str(e)}")
    
    print()


def main():
    print("=" * 70)
    print("ESPRIT Deep Fetch - Direct API Queries")
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

        # Get courses
        courses = client.courses()
        print(f"\n✓ Found {len(courses)} courses:\n")
        for i, course in enumerate(courses, 1):
            print(f"  [{i:2d}] {course.name}")

        # Select course
        course_num = input("\nEnter course number: ").strip()
        idx = int(course_num) - 1
        
        if 0 <= idx < len(courses):
            course = courses[idx]
            
            print(f"\n{Fore.CYAN}{'=' * 70}{Style.RESET_ALL}")
            print(f"{Fore.CYAN}Deep Fetching: {course.name}{Style.RESET_ALL}")
            print(f"{Fore.CYAN}{'=' * 70}{Style.RESET_ALL}\n")

            # Get all content
            contents = course.contents()
            
            # Focus on Chapter 2 -> Ressources -> Série d'exercices
            for content in contents:
                if "Chapitre 2" in content.title:
                    print(f"\n{Fore.YELLOW}Found: {content.title}{Style.RESET_ALL}\n")
                    
                    # Get children
                    if content.has_children:
                        children = content.children()
                        for child in children:
                            if "Ressources" in child.title:
                                print(f"{Fore.YELLOW}Found: {child.title}{Style.RESET_ALL}\n")
                                
                                # Get Ressources children
                                if child.has_children:
                                    ressources_children = child.children()
                                    for res_child in ressources_children:
                                        print(f"{Fore.YELLOW}Inspecting: {res_child.title}{Style.RESET_ALL}\n")
                                        deep_fetch_folder(client, course.id, res_child.id, res_child.title, 0)
                                        
                                        # Also check if THIS has children
                                        if res_child.has_children:
                                            print(f"   {Fore.CYAN}This folder has children, fetching them...{Style.RESET_ALL}")
                                            sub_children = res_child.children()
                                            for sub in sub_children:
                                                deep_fetch_folder(client, course.id, sub.id, sub.title, 1)

    except KeyboardInterrupt:
        print("\n\n⚠ Interrupted")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
