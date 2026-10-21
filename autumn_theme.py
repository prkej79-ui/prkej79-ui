"""프로젝트에 포함된 가을 배경과 CSS 전용 단풍 애니메이션."""

from base64 import b64encode
from functools import lru_cache
from pathlib import Path

import streamlit as st


@lru_cache(maxsize=1)
def background_css():
    asset = Path(__file__).with_name('assets') / 'deoksugung-autumn.jpg'
    if not asset.exists():
        return ''  # 이미지 누락 시 CSS의 단색 가을 배경으로 폴백합니다.
    encoded = b64encode(asset.read_bytes()).decode('ascii')
    return ':root { --autumn-background: url("data:image/jpeg;base64,' + encoded + '"); }'


def falling_leaves_html():
    # SVG·JS 없이 장식용 CSS 모양만 사용하며 외부 입력은 삽입하지 않습니다.
    leaves = ''.join(
        f'<span class="autumn-leaf" style="--x:{(i * 17 + 3) % 100}vw;'
        f'--duration:{14 + i % 7}s;--delay:-{i * 1.7:.1f}s;'
        f'--size:{14 + i % 4 * 4}px;--drift:{40 + i % 5 * 22}px;'
        f'--leaf-color:{("#b54c24", "#d78c22", "#a33120")[i % 3]}"></span>'
        for i in range(16)
    )
    return '<div class="autumn-leaves" aria-hidden="true">' + leaves + '</div>'


def render_autumn_theme():
    st.html('<style>' + background_css() + '</style>')
    st.html(falling_leaves_html())
    st.html('''<section class="autumn-banner" aria-label="가을 정동길 배경">
        <span>SEOUL · AUTUMN WALK</span>
        <h2>덕수궁에서 예원학교로, 가을 산책</h2>
        <p>돌담을 따라 물든 단풍처럼, 여행의 순간을 차곡차곡.</p>
        <small>덕수궁·정동길을 모티브로 한 AI 생성 배경</small>
        </section>''')
