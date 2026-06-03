import zipfile
import xml.etree.ElementTree as ET
import sys

def extract_text(path):
    try:
        with zipfile.ZipFile(path, 'r') as z:
            xml_content = z.read('word/document.xml')
            tree = ET.XML(xml_content)
            ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
            
            text = []
            for p in tree.findall('.//w:p', ns):
                paragraph_text = "".join([t.text for t in p.findall('.//w:t', ns) if t.text])
                if paragraph_text:
                    text.append(paragraph_text)
            return "\n".join(text)
    except Exception as e:
        return f"Error: {e}"

print(extract_text(r"C:\Users\AKHILESHWAR\Downloads\ApplicationTracker_Restructuring_Plan_v2.docx"))
