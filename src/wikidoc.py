import os
import sys
import urllib
import html
import requests
from bs4 import BeautifulSoup, Doctype
from urllib.parse import urljoin, urlparse
import re
import latex2mathml.converter
import pathlib
# from latex2mathml.converter import convert as latex_to_mathml

class wikidoc:
    def __init__(self, url : str = None):
        self.book_url = ''
        self.base_dir = ''
        self.image_base_path = ''
        self.css_base_path = ''
        self.page_list = []

        if url is not None:
            self.set_url(url)

    def set_url(self, book_url):
        self.book_url = book_url
        self.base_dir = urlparse(book_url).path[1:]
        self.image_base_path = 'image'
        self.css_base_path = 'css'

    def get_html_path(self, filename: str, is_file: bool = False) -> str:
        return str(pathlib.PureWindowsPath(f'{self.base_dir}/{filename}')) if is_file else filename

    def get_image_path(self, page_dir: str, filename: str, is_file: bool = False) -> str:
        return str(pathlib.PureWindowsPath(f'{self.base_dir}/{self.image_base_path}/{page_dir}/{filename}')) if is_file else f'{self.image_base_path}/{page_dir}/{filename}'

    def get_css_path(self, filename: str, is_file: bool = False) -> str:
        return str(pathlib.PureWindowsPath(f'{self.base_dir}/{self.css_base_path}/{filename}')) if is_file else f'{self.css_base_path}/{filename}'

    def _download_css(self, html_soup: BeautifulSoup, filename: str):
        # 저장용 CSS 문자열
        combined_css = ""

        # 1. 외부 CSS <link> 추출
        for link in html_soup.find_all("link", rel="stylesheet"):
            href = link.get("href")
            if href:
                css_url = urljoin(self.book_url, href)
                try:
                    css_response = requests.get(css_url)
                    combined_css += f"\n/* From {css_url} */\n" + css_response.text
                except Exception as e:
                    print(f"❌ Failed to download {css_url}: {e}")

        # 2. 내부 <style> 태그 추출
        for style in html_soup.find_all("style"):
            combined_css += "\n/* Inline <style> */\n" + style.text

        # 3. 결과를 CSS 파일로 저장
        os.makedirs(self.get_css_path('', True), exist_ok=True)
        output_path = self.get_css_path(filename, True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(combined_css)

    def book_download_task(self):
        res = requests.get(self.book_url)
        html_soup = BeautifulSoup(res.text, "html5lib")

        self._download_css(html_soup, 'default.css')

        # 모든 이미지 태그 찾기
        pages = html_soup.find_all("a", class_="list-group-item")

        # 이미지 다운로드 및 HTML 수정
        purl = urlparse(self.book_url)
        pageno = 100
        for page in pages:
            pageno = pageno + 1
            page_href = page.get('href')

            match = re.match(r'^javascript:page\((\s*.*?\s*)\).*$', page_href)
            if match:
                page_href = match.group(1)
                page_url = f'{purl.scheme}://{purl.netloc}/{page_href}'
            else:
                page_url = urljoin(purl.geturl(), page_href)

            # book_page_task({'url': page_url, 'no': pageno})


def latex_to_mathml(latex_expr: str, display: bool = False) -> str:
    try:
        mathml = latex2mathml.converter.convert(latex_expr)
        return f"<math xmlns='http://www.w3.org/1998/Math/MathML' display='{'block' if display else 'inline'}'>{mathml}</math>"
    except Exception:
        return f"<!-- Failed to convert LaTeX: {latex_expr} -->"

def is_inside_pre_code_tag(tag):
    pre_code_tags = {'pre', 'code'}

    while tag is not None:
        if tag.name in pre_code_tags:
            return True
        tag = tag.parent
    return False

def replace_custom_markers(html_text: str) -> str:
    html_text = re.sub(r'\[\[MARK]]', '<mark class="add">', html_text)
    html_text = re.sub(r'\[\[/MARK]]', '</mark>', html_text)
    html_text = re.sub(r'\[\[SMARK]]', '<mark class="del"><strike>', html_text)
    html_text = re.sub(r'\[\[/SMARK]]', '</strike></mark>', html_text)
    return html_text

def replace_custom_tag(html_soup: BeautifulSoup, is_mathjax: bool) -> BeautifulSoup:
    inline_patterns = [
        (r'(?<!\\)\$(.+?)(?<!\\)\$', False),       # $...$
        (r'\\\((.+?)\\\)', False),                 # \(...\)
    ]
    block_patterns = [
        (r'(?<!\\)\$\$(.+?)(?<!\\)\$\$', True),    # $$...$$
        (r'\\\[(.+?)\\\]', True),                  # \[...\]
    ]
    all_patterns = block_patterns + inline_patterns

    for text_node in html_soup.find_all(string=True):
        if isinstance(text_node, Doctype): continue

        new_text = text = html.escape(text_node)
        # <pre>와 <code> 태그 내부에서만 마커 변환을 적용
        if is_inside_pre_code_tag(text_node.parent):
            # text = text_node.parent.encode_contents().decode()
            new_text = replace_custom_markers(text)
            pass
        elif is_mathjax:
            # MathJax 수식 변환만 수행
            for pattern, is_display in all_patterns:
                regex = re.compile(pattern, re.DOTALL)

                def replacer(match):
                    latex = match.group(1).strip()
                    return latex_to_mathml(latex, display=is_display)
                new_text = regex.sub(replacer, new_text)

        if text != new_text:
            text_node.replace_with(BeautifulSoup(new_text, 'html.parser'))

    return html_soup

def book_page_template():
    html_soup = BeautifulSoup('''
<!DOCTYPE HTML>
<html lang="ko">
<head>
    <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="google-site-verification" content="mzkAy71X1qQFWihQN535LoiToXg34MUg9nuor7Og9E8" />
    <meta name="naver-site-verification" content="a7b53e9ea172d3cefcc05eaba6ebf7180eca08fa" />
    <title> </title>
    <link type="text/css" href="css/default.css" rel="stylesheet"/>
</head>
<body>
<div class="page col-sm-12" id="content" style="">
</div>
</body>
</html>''',
                              'html5lib')
    return html_soup

def book_page_task(page):
    res = requests.get(page['url'])
    html_soup = BeautifulSoup(res.text, "html5lib")

    is_mathjax = any('mathjax' in script.get('src', '') for script in html_soup.find_all('script'))

    page['title'] = html_soup.find('title').text.strip()
    page['filename'] = f'{page['no']:03}_' + re.sub(r'[<>:"/\\|?*]', '', page['title']) + '.html'
    page['html_dir'] = 'book'
    page['img_dir'] = f"image\\{page['no']}"

    os.makedirs(page['html_dir'], exist_ok=True)
    os.makedirs(f"{page['html_dir']}\\{page['img_dir']}", exist_ok=True)

    content = BeautifulSoup('', 'html5lib')
    content.append(html_soup.find('h1', class_='page-subject'))
    content.append(html_soup.find('div', class_='page-content'))

    images = content.find_all("img")
    for img in images:
        img_url = urljoin(page['url'], img.get("src"))  # 상대 URL을 절대 URL로 변환
        img_name = urllib.parse.unquote(img_url.split("/")[-1])  # 이미지 파일 이름 설정
        try:
            img_data = requests.get(img_url).content
            img_filename = os.path.join(page['html_dir'], page['img_dir'], img_name)
            with open(img_filename, "wb") as f:
                f.write(img_data)
            print(f"다운로드 완료: {img_name}")

            img_src = f'{page['img_dir']}/{img_name}'.replace("\\", "/")
            img["src"] = img_src
        except Exception as e:
            print(f"이미지 다운로드 실패 {img_url}: {e}")

    html_content = book_page_template()

    html_content.title.string = page['title']
    html_content.find(id="content").insert(0, content)

    html_content = replace_custom_tag(html_content, is_mathjax)

    with open(f'{page['html_dir']}/{page['filename']}', "w", encoding="utf-8") as f:
        out_html = str(html_content)
        f.write(out_html)

    print(f"수정된 HTML 파일 저장 완료: {page['filename']}")


def book_download_css(html_soup: BeautifulSoup, url: str):
    # 저장용 CSS 문자열
    combined_css = ""

    # 1. 외부 CSS <link> 추출
    for link in html_soup.find_all("link", rel="stylesheet"):
        href = link.get("href")
        if href:
            css_url = urljoin(url, href)
            try:
                css_response = requests.get(css_url)
                combined_css += f"\n/* From {css_url} */\n" + css_response.text
            except Exception as e:
                print(f"❌ Failed to download {css_url}: {e}")

    # 2. 내부 <style> 태그 추출
    for style in html_soup.find_all("style"):
        combined_css += "\n/* Inline <style> */\n" + style.text

    # 3. 결과를 CSS 파일로 저장
    os.makedirs("book\\css", exist_ok=True)
    output_path = "book\\css\\default.css"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(combined_css)

def book_download_task(url):
    print(f'url = {url}')
    res = requests.get(url)
    html_soup = BeautifulSoup(res.text, "html5lib")

    book_download_css(html_soup, url)

    # 모든 이미지 태그 찾기
    images = html_soup.find_all("a", class_="list-group-item")

    # 이미지 다운로드 및 HTML 수정
    purl = urlparse(url)
    pageno = 100
    for img in images:
        pageno = pageno + 1
        page_href = img.get('href')

        match = re.match(r'^javascript:page\((\s*.*?\s*)\).*$', page_href)
        if match:
            page_href = match.group(1)
            page_url = f'{purl.scheme}://{purl.netloc}/{page_href}'
        else:
            page_url = urljoin(purl.geturl(), page_href)

        book_page_task({'url':page_url, 'no': pageno})

if __name__ == "__main__":
    book = wikidoc('https://wikidocs.net/book/31')
    book.book_download_task()

    if len(sys.argv) > 1:
        book_download_task(sys.argv[1])
    else:
        response = requests.get('https://wikidocs.net/204')
        soup = BeautifulSoup(response.text, "html5lib")
        book_download_css(soup, 'https://wikidocs.net/book/31')
        book_page_task({'url':'https://wikidocs.net/204', 'no': 0})