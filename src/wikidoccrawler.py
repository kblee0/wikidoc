import os
import sys
import urllib
import html
import requests
from bs4 import BeautifulSoup, Doctype, NavigableString
from urllib.parse import urljoin, urlparse
import re
import latex2mathml.converter
import pathlib
# from latex2mathml.converter import convert as latex_to_mathml

class WikidocCrawler:
    def __init__(self, url : str = None):
        self.book_url = ''
        self.basedir = ''
        self.image_basedir = ''
        self.css_basedir = ''

        if url is not None:
            self.set_url(url)

    def set_url(self, book_url):
        self.book_url = book_url
        self.basedir = urlparse(book_url).path[1:]
        self.image_basedir = 'image'
        self.css_basedir = 'css'

    def get_html_filepath(self, filename: str, is_file: bool = False) -> str:
        return str(pathlib.PureWindowsPath(f'{self.basedir}/{filename}')) if is_file else filename

    def get_image_filepath(self, page_subdir: str, filename: str, is_file: bool = False) -> str:
        return str(pathlib.PureWindowsPath(f'{self.basedir}/{self.image_basedir}/{page_subdir}/{filename}')) if is_file else f'{self.image_basedir}/{page_subdir}/{filename}'

    def get_css_filepath(self, filename: str, is_file: bool = False) -> str:
        return str(pathlib.PureWindowsPath(f'{self.basedir}/{self.css_basedir}/{filename}')) if is_file else f'{self.css_basedir}/{filename}'

    def _get_page_template(self):
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
<div class="page col-sm-12" id="page" style="">
    <div id="page-subject" style="">
    </div>
    <div id='page-content'>
    </div>
</div>
</body>
</html>''',
                                  'html5lib')
        return html_soup

    def _replace_latex_to_mathml(self, node: NavigableString):
        # [ ( pattern, inline or block ) ]
        latex_patterns = [
            (r'(?<!\\)\$\$(.+?)(?<!\\)\$\$', True),  # $$...$$
            (r'\\\[(.+?)\\\]', True),  # \[...\]
            (r'(?<!\\)\$(.+?)(?<!\\)\$', False),  # $...$
            (r'\\\((.+?)\\\)', False),  # \(...\)
        ]

        old_text = new_text = html.escape(node.text)

        for pattern, is_block in latex_patterns:
            regex = re.compile(pattern, re.DOTALL if is_block else 0)

            def replacer(match):
                latex = match.group(1).strip()
                try:
                    mathml = latex2mathml.converter.convert(latex)
                    return f"<math xmlns='http://www.w3.org/1998/Math/MathML' display='{'block' if is_block else 'inline'}'>{mathml}</math>"
                except Exception:
                    return f"<!-- Failed to convert LaTeX: {latex} -->"

            new_text = regex.sub(replacer, new_text)

        if old_text != new_text:
            node.replace_with(BeautifulSoup(new_text, 'html.parser'))

    def _replace_custom_markers(self, node: NavigableString):
        old_text = new_text = html.escape(node.text)
        new_text = re.sub(r'\[\[MARK]]', '<mark class="add">', new_text)
        new_text = re.sub(r'\[\[/MARK]]', '</mark>', new_text)
        new_text = re.sub(r'\[\[SMARK]]', '<mark class="del"><strike>', new_text)
        new_text = re.sub(r'\[\[/SMARK]]', '</strike></mark>', new_text)
        if old_text != new_text: node.replace_with(BeautifulSoup(new_text, 'html.parser'))

    def _download_css(self, node: BeautifulSoup, filename: str):
        # 저장용 CSS 문자열
        combined_css = ""

        # 1. 외부 CSS <link> 추출
        for link in node.find_all("link", rel="stylesheet"):
            href = link.get("href")
            if href:
                css_url = urljoin(self.book_url, href)
                try:
                    css_response = requests.get(css_url)
                    combined_css += f"\n/* From {css_url} */\n" + css_response.text
                except Exception as e:
                    print(f"❌ Failed to download {css_url}: {e}")

        # 2. 내부 <style> 태그 추출
        for style in node.find_all("style"):
            combined_css += "\n/* Inline <style> */\n" + style.text

        # 3. 결과를 CSS 파일로 저장
        os.makedirs(self.get_css_filepath('', True), exist_ok=True)
        css_filepath = self.get_css_filepath(filename, True)
        with open(css_filepath, "w", encoding="utf-8") as f:
            f.write(combined_css)

    def _download_image(self, page: BeautifulSoup, page_url: str, page_subdir: str):
        # Image download
        images = page.find_all("img")
        for img in images:
            img_url = urljoin(page_url, img.get("src"))  # 상대 URL을 절대 URL로 변환
            img_filename = urllib.parse.unquote(img_url.split("/")[-1])  # 이미지 파일 이름 설정
            try:
                img_data = requests.get(img_url).content
                img_filepath = self.get_image_filepath(page_subdir, img_filename, True)
                with open(img_filepath, "wb") as f:
                    f.write(img_data)
                print(f"다운로드 완료: {img_url} -> {img_filepath}")

                img["src"] = self.get_image_filepath(page_subdir, img_filename)
            except Exception as e:
                print(f"이미지 다운로드 실패 {img_url}: {e}")

    def _convert_tag(self, page: BeautifulSoup, is_mathjax: bool):
        # Tag convert
        for text_node in page.find_all(string=True):
            if isinstance(text_node, Doctype): continue

            is_pre_code_tag = False
            pre_code_tags = {'pre', 'code'}
            tag = text_node.parent
            while tag is not None:
                if tag.name in pre_code_tags:
                    is_pre_code_tag = True
                    break
                tag = tag.parent
            if is_pre_code_tag:
                self._replace_custom_markers(text_node)
            elif is_mathjax:
                self._replace_latex_to_mathml(text_node)

    def gen_topic(self, page_list):
        # 결과 nav 구조 초기화
        nav_html = '''<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>

<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="ko" xml:lang="ko">
<head>
  <title>ePub NAV</title>
  <meta charset="utf-8"/>
  <link href="../Styles/sgc-nav.css" rel="stylesheet" type="text/css"/>
</head>
<body epub:type="frontmatter">
  <nav epub:type="toc" id="toc" role="doc-toc">
    <h1>차례</h1>
    <ol>
'''
        current_li = None
        for a in page_list:
            title = html.escape(a['title'])
            filename = ''.join(ch if ord(ch) >= 256 else urllib.parse.quote(ch, safe="") for ch in a['filename'])
            # 레벨 1: padding이 0
            if a['padding'] == 0:
                if current_li:
                    nav_html += current_li + '</ol></li>\n'
                current_li = f'    <li><a href="{filename}">{title}</a>\n      <ol>\n'
            else:
                current_li += f'        <li><a href="{filename}">{title}</a></li>\n'

        # 마지막 항목 닫기
        if current_li:
            nav_html += current_li + '      </ol>\n    </li>\n'

        nav_html += '''    </ol>
  </nav>
</body>
</html>'''
        with open(self.get_html_filepath('nav.xhtml', True), "w", encoding="utf-8") as f:
            f.write(nav_html)


    def page_download_task(self, url: str, page_subdir: str = '000'):
        print(f'Page Download url: {url}')
        res = requests.get(url)
        orig_page = BeautifulSoup(res.text, "html5lib")

        is_mathjax = any('mathjax' in script.get('src', '') for script in orig_page.find_all('script'))
        title = orig_page.title.text
        page_filename = page_subdir + '_' + re.sub(r'[<>:"/\\|?*]', '', title) + '.html'
        page_filepath = self.get_html_filepath(page_filename, True)

        os.makedirs(self.get_html_filepath('', True), exist_ok=True)
        os.makedirs(self.get_image_filepath(page_subdir, '', True), exist_ok=True)

        page = self._get_page_template()
        page.title.string = title
        page.find(id="page-subject").insert(0, orig_page.find('h1', class_='page-subject'))
        page.find(id="page-content").insert(0, orig_page.find('div', class_='page-content'))

        self._download_image(orig_page, url, page_subdir)
        self._convert_tag(page, is_mathjax)

        with open(page_filepath, "w", encoding="utf-8") as f:
            out_html = str(page)
            f.write(out_html)

        print(f"수정된 HTML 파일 저장 완료: {page_filepath}")
        return page_filename

    def book_download_task(self):
        print(f'Book Download url: {self.book_url}')
        res = requests.get(self.book_url)
        html_soup = BeautifulSoup(res.text, "html5lib")

        self._download_css(html_soup, 'default.css')

        pages = html_soup.find_all("a", class_="list-group-item")

        purl = urlparse(self.book_url)
        pageno = 100
        page_list = []
        for page in pages:
            pageno = pageno + 1

            title = page.get('title') or page.get_text(strip=True)
            page_href = page.get('href')

            match = re.match(r'^javascript:page\((\s*.*?\s*)\).*$', page_href)
            if match:
                page_href = match.group(1)
                page_url = f'{purl.scheme}://{purl.netloc}/{page_href}'
            else:
                page_url = urljoin(purl.geturl(), page_href)

            padding_span = page.select_one('span[style*="padding-left"]')
            padding = int(padding_span['style'].replace('padding-left:', '').replace('px', '').strip()) if padding_span else 0

            filename = self.page_download_task(page_url, str(pageno))

            page_list.append({'padding': padding, 'title': title, 'filename': filename})
        self.gen_topic(page_list)

if __name__ == "__main__":
    if len(sys.argv) == 2:
        book = WikidocCrawler(sys.argv[1])
        book.book_download_task()
    elif len(sys.argv) == 3:
        book = WikidocCrawler(sys.argv[1])
        book.page_download_task(sys.argv[2])
    else:
        book = WikidocCrawler('https://wikidocs.net/book/2788')
        book.book_download_task()
        book.page_download_task('https://wikidocs.net/161302')
