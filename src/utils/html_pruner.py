from bs4 import BeautifulSoup

def extract_interactive_elements(html_content: str) -> str:
    """
    Strips the HTML down to just structural and interactive elements to save LLM tokens.
    Keeps: forms, inputs, buttons, and navigation blocks.
    Removes: scripts, styles, SVGs, images, and heavy text content.
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # 1. Remove completely useless tags
    for tag in soup(['script', 'style', 'svg', 'img', 'noscript', 'iframe', 'video', 'audio', 'path']):
        tag.decompose()
        
    # 2. Keep only important attributes
    allowed_attrs = ['id', 'class', 'name', 'type', 'href', 'placeholder', 'role', 'aria-label']
    for tag in soup.find_all(True):
        attrs_to_remove = [attr for attr in tag.attrs if attr not in allowed_attrs]
        for attr in attrs_to_remove:
            del tag[attr]
            
    # 3. Extract interactive areas
    interactive_html = ""
    
    # Grab header/nav (usually contains search)
    header = soup.find('header')
    if header:
        interactive_html += f"<header>\n{header.prettify()}\n</header>\n"
        
    # Grab all forms 
    for form in soup.find_all('form'):
        if not header or form not in header.descendants:
            interactive_html += f"<form>\n{form.prettify()}\n</form>\n"
            
    # Grab any explicit search roles (e.g. <div role="search">)
    for search_div in soup.find_all(attrs={"role": "search"}):
        if not header or search_div not in header.descendants:
            interactive_html += f"<!-- Search Role Element -->\n{search_div.prettify()}\n"
            
    # Grab all stray inputs and buttons just in case!
    for element in soup.find_all(['input', 'button']):
        if not header or element not in header.descendants:
            in_extracted_form = False
            for form in soup.find_all('form'):
                if element in form.descendants:
                    in_extracted_form = True
                    break
            if not in_extracted_form:
                interactive_html += f"<!-- Stray {element.name} -->\n{element.prettify()}\n"
                
    return interactive_html

def extract_coupon_elements(html: str) -> str:
    """Agent 4 Pruner: Extracts buttons, links, and potential coupon boxes."""
    soup = BeautifulSoup(html, 'html.parser')
    
    # 1. Remove non-visible junk
    for tag in soup(['script', 'style', 'svg', 'img', 'noscript', 'iframe', 'meta', 'link']):
        tag.decompose()
        
    output = ""
    # 2. Grab all interactive links and buttons
    for el in soup.find_all(['a', 'button']):
        # Ignore empty links
        if el.get_text(strip=True):
            output += f"<!-- Clickable {el.name} -->\n{el.prettify()}\n"
            
    # 3. Grab elements that explicitly mention code/coupon in class or id
    import re
    coupon_regex = re.compile(r'code|coupon|deal|promo|voucher', re.I)
    for el in soup.find_all(class_=coupon_regex):
        if el.name not in ['a', 'button'] and not el.find(['a', 'button']):
            output += f"<!-- Potential Code Box -->\n{el.prettify()}\n"
            
    # Hard cap to prevent massive token explosion on huge directories
    return output[:15000]
