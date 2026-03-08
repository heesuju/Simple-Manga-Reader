import re

def find_number(text:str)->int:
    numbers = re.findall(r'\d+', text)
    return int(numbers[0]) if numbers else float('inf') 

def natural_sort_key(s: str):
    """Sort strings with numbers alphanumerically."""
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', str(s))]
