from src.utils.img_utils import get_chapter_number
import os
from pathlib import Path
import argparse

# You already have this function.
# It should take a filename and return an integer (page number).
# Example:
# def get_chapter_number(filename: str) -> int:
#     ...

def find_missing_pages(directory: str) -> str:
    image_exts = {'.png', '.jpg', '.jpeg', '.webp'}
    numbers = []

    for file in Path(directory).iterdir():
        if file.is_file() and file.suffix.lower() in image_exts:
            num = get_chapter_number(file.name)
            if num is not None:
                numbers.append(num)

    if not numbers:
        return f"Directory: {directory}\nNo numbered image files found."

    numbers = sorted(set(numbers))
    start, end = numbers[0], numbers[-1]
    total_expected = end - start + 1
    missing = [n for n in range(start, end + 1) if n not in numbers]

    if len(missing) > 0:
        return (
            f"Directory: {directory}\n"
            f"Start page: {start}\n"
            f"End page: {end}\n"
            f"Total pages found: {len(numbers)}\n"
            f"Total expected: {total_expected}\n"
            f"Missing pages: {missing if missing else 'None'}"
        )
    else:
        return ""

# Example usage
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Validate pages in a directory.")
    parser.add_argument("path", help="Path to the directory to validate.")
    args = parser.parse_args()

    input_path = Path(args.path)
    missing = 0
    if input_path.is_dir():
        subfolders = [f for f in input_path.iterdir() if f.is_dir()]
        if subfolders:
            # Sort subfolders numerically based on their names
            subfolders.sort(key=lambda f: get_chapter_number(f.name) if get_chapter_number(f.name) is not None else float('inf'))
            
            results = []
            for folder in subfolders:
                result = find_missing_pages(str(folder))
                if result:
                    missing+=1
                results.append(result)
            print("\n\n---\n\n".join(results))
        else:
            print(find_missing_pages(str(input_path)))
    else:
        print(f"Error: {args.path} is not a valid directory.")


    print(len(results), "chapters found")
    print(missing, "chapters missing pages")
    