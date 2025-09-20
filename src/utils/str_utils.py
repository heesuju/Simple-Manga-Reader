import re

def find_number(text:str)->int:
    numbers = re.findall(r'\d+', text)
    return int(numbers[0]) if numbers else float('inf') 
