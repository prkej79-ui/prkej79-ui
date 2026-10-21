"""카카오내비 공식 SDK 연결. REST 키는 브라우저로 전달하지 않습니다."""

import json
import os
import re
from urllib.parse import quote

import streamlit as st
import streamlit.components.v1 as components

from distance_calc import valid_coordinates


SDK_URL = 'https://t1.kakaocdn.net/kakao_js_sdk/2.8.4/kakao.min.js'
SDK_INTEGRITY = 'sha384-BGX7Wb16GmRFagri4bLJV2DgipVZaU2AI812GZtHtHzzDQJnfHasDXN5houxv45w'


def directions_url(place):
    coords = valid_coordinates(place)
    if not coords or not place.get('name'):
        return None
    lat, lon = coords
    return f"https://map.kakao.com/link/to/{quote(place['name'], safe='')},{lat},{lon}"


def navi_html(place, javascript_key):
    coords = valid_coordinates(place)
    if not coords or not place.get('name') or not re.fullmatch(r'[a-fA-F0-9]{32}', javascript_key):
        return None
    lat, lon = coords
    payload = json.dumps({'name': place['name'], 'x': lon, 'y': lat, 'coordType': 'wgs84'}, ensure_ascii=True)
    payload = payload.replace('<', r'\u003c').replace('>', r'\u003e').replace('&', r'\u0026')
    # JSON 인코딩 + script 종료 문자 이스케이프로 장소명 기반 스크립트 삽입을 방지합니다.
    return '''<!doctype html><html lang="ko"><head><meta charset="utf-8">
    <style>body{margin:0;font-family:system-ui,sans-serif;color:#334155}button{background:#fee500;color:#222;border:0;border-radius:10px;padding:12px 18px;font-weight:700;cursor:pointer}button:disabled{opacity:.5;cursor:not-allowed}p{font-size:12px;line-height:1.5;margin:8px 0}</style></head><body>
    <button id="navi" disabled>카카오내비 길안내 시작</button>
    <p id="status" role="status" aria-live="polite">카카오내비 연결 준비 중…</p>
    <script>
    const destination=__DESTINATION__;
    const publicKey=__JSKEY__;
    const button=document.getElementById('navi');
    const status=document.getElementById('status');
    const mobile=/Android|iPhone|iPad|iPod/i.test(navigator.userAgent) || (navigator.platform==='MacIntel' && navigator.maxTouchPoints>1);
    if(!mobile){status.textContent='카카오내비 앱 길안내는 모바일에서 이용하세요. PC에서는 위 카카오맵 길찾기를 이용하세요.';}
    else{
      const sdk=document.createElement('script');
      sdk.src='__SDK_URL__'; sdk.integrity='__SDK_INTEGRITY__'; sdk.crossOrigin='anonymous';
      sdk.onerror=()=>{status.textContent='SDK를 불러오지 못했습니다. 네트워크를 확인하거나 카카오맵 길찾기를 이용하세요.';};
      sdk.onload=()=>{try{
        Kakao.init(publicKey);
        button.disabled=false;
        status.textContent='버튼을 누르면 목적지를 카카오내비로 전달합니다. 앱이 없으면 설치 페이지로 이동할 수 있습니다.';
      }catch(_){status.textContent='카카오내비 초기화에 실패했습니다. JavaScript 키와 등록 도메인을 확인하세요.';}};
      document.head.appendChild(sdk);
      button.addEventListener('click',()=>{try{Kakao.Navi.start(destination);}
        catch(_){status.textContent='길안내를 실행하지 못했습니다. 도메인 설정과 모바일 브라우저를 확인하세요.';}});
    }
    </script></body></html>'''.replace('__JSKEY__', json.dumps(javascript_key)).replace('__SDK_URL__', SDK_URL).replace('__SDK_INTEGRITY__', SDK_INTEGRITY).replace('__DESTINATION__', payload)


def render_navigation(place, *, key):
    url = directions_url(place)
    if not url:
        return
    st.link_button('카카오맵 길찾기 (PC·모바일)', url)
    js_key = os.getenv('KAKAO_JAVASCRIPT_KEY', '').strip()
    # 실수로 REST 키를 JavaScript 변수에 복사했어도 브라우저로 보내지 않습니다.
    if js_key and js_key != os.getenv('KAKAO_REST_API_KEY', '').strip():
        html = navi_html(place, js_key)
    else:
        html = None
    if html:
        components.html(html, height=130, scrolling=False)
    else:
        st.button('카카오내비 길안내 시작 · 설정 필요', disabled=True, key=f'{key}-navi-disabled')
        st.caption('카카오내비 앱 실행: .env의 KAKAO_JAVASCRIPT_KEY 설정과 카카오 개발자 콘솔의 JavaScript SDK 도메인 등록이 필요합니다. REST API 키를 대신 사용하지 마세요.')
    st.caption('선택한 목적지만 전달하며 현재 위치는 앱에서 확인합니다. 이 화면은 GPS를 수집하거나 실제 경로·도착 시간을 확정하지 않습니다.')
