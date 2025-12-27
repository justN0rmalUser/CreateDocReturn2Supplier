def std(word: str) -> str:
    if isinstance(word, str):
        return word.upper().replace('-', '').replace(' ', '').replace('.', '').replace('/', '').replace(',', '').strip()

def a():    
    import pathlib
    sa = pathlib.Path()
