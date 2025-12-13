from pprint import pprint

from content_system import download_part, list_tree


def _print_tree(tree: dict) -> None:
    module = tree.get("module")
    if not module:
        print(f"Module unavailable: {tree.get('reason')}")
        return

    print(f"Module {module.get('module_id')}: {module.get('title')}")
    for section in module.get("sections", []):
        section_status = section.get("status")
        sec_note = f" [{section_status}]" if section_status else ""
        sec_reason = f" - {section.get('reason')}" if section.get("reason") else ""
        print(f"  Section {section.get('section_id')}: {section.get('title')}{sec_note}{sec_reason}")
        for package in section.get("packages", []):
            pkg_status = package.get("status")
            pkg_note = f" [{pkg_status}]" if pkg_status else ""
            pkg_reason = f" - {package.get('reason')}" if package.get("reason") else ""
            print(f"    Package {package.get('package_id')}: {package.get('title')}{pkg_note}{pkg_reason}")
            for part in package.get("parts", []):
                part_reason = f" - {part.get('reason')}" if part.get("reason") else ""
                print(f"      Part {part.get('part_id')} [{part.get('status')}]{part_reason}")


def main() -> None:
    print("Initial tree:")
    _print_tree(list_tree())

    print("\nDownloading part 'gravity_demo':")
    result = download_part("gravity_demo")
    pprint(result)

    print("\nTree after download:")
    _print_tree(list_tree())


if __name__ == "__main__":
    main()
